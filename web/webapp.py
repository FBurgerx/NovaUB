"""Веб-панель авторизации NovaUB.

Переписана с Pyrogram (нет в системе) на Telethon — теперь это тот же клиент,
что и сам юзербот, и 2FA-пароль работает (protection mode выставляется в safe).

Безопасность:
  • Панель закрыта паролем. Хранится в config-<...>.json -> web.password_hash
    (sha256), если пароль не задан — генерируется случайный и печатается в
    консоль при старте панели.
  • Rate-limit: максимум MAX_ATTEMPTS попыток на IP за WINDOW секунд,
    превышение — задержка до окна.
  • Сессия входа (token) живёт STATE_TTL_SECONDS и не переиспользуется.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from flask import Flask, redirect, render_template_string, request

# Корень проекта: web/ вложена в него, сессии создаются в корне.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from telethon import TelegramClient
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    FloodWaitError,
)

APP_TITLE = "NovaUB • Telegram Web Login"
STATE_TTL_SECONDS = 10 * 60

# Rate-limit: попыток на IP за окно
MAX_ATTEMPTS = 8
WINDOW_SECONDS = 10 * 60
# Сколько секунд ждать, когда лимит исчерпан (soft fail — не подсказываем злоумышленнику точное окно)
RATELIMIT_HOLD_SECONDS = 30


@dataclass
class LoginState:
    token: str
    created_at: float
    api_id: int
    api_hash: str
    phone: str
    session_name: str
    phone_code_hash: str


@dataclass
class _Attempts:
    count: int = 0
    window_start: float = field(default_factory=time.time)


_states: Dict[str, LoginState] = {}
_clients: Dict[str, TelegramClient] = {}
_attempts: Dict[str, _Attempts] = {}


# ---------------------------------------------------------------------------
# Пароль панели
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    """sha256 (быстро и достаточно для защиты веб-панели)."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _verify_password(password: str, stored_hash: Optional[str]) -> bool:
    if not stored_hash:
        return False
    return hmac.compare_digest(_hash_password(password or ""), stored_hash)


def _panel_password_hash() -> Tuple[Optional[str], Optional[str]]:
    """Возвращает (hash, plaintext-если-он-был-сгенерирован сейчас)."""
    from core import config as nova_config

    cfg = nova_config.load(0)
    stored = (cfg.web or {}).get("password_hash")
    if stored:
        return stored, None

    # Пароля нет — генерируем случайный и сохраняем, чтобы панель не торчала
    # в сеть без защиты (особенно при туннеле).
    plain = secrets.token_urlsafe(16)
    try:
        updated = dict(cfg)
        updated["web"] = {**(updated.get("web") or {}), "password_hash": _hash_password(plain)}
        nova_config.save(0, updated)
    except Exception:
        pass
    return _hash_password(plain), plain


# ---------------------------------------------------------------------------
# Rate-limit
# ---------------------------------------------------------------------------

def _client_ip() -> str:
    if request.headers.get("X-Forwarded-For"):
        return request.headers["X-Forwarded-For"].split(",")[0].strip()
    return request.remote_addr or "unknown"


def _rate_limit_hit() -> bool:
    """True — слишком много попыток, надо отклонить."""
    ip = _client_ip()
    now = time.time()
    state = _attempts.get(ip)
    if state is None:
        _attempts[ip] = _Attempts(count=1, window_start=now)
        return False
    if now - state.window_start > WINDOW_SECONDS:
        state.count = 1
        state.window_start = now
        return False
    state.count += 1
    return state.count > MAX_ATTEMPTS


def _rate_limit_error() -> str:
    """Сообщение при превышении (общее — не раскрываем устройство лимита)."""
    return "Слишком много попыток. Подождите немного и попробуйте снова."


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def _ensure_event_loop():
    """Telethon — async, Flask — нет. Клиенты крутятся в отдельном loop'е."""
    global _loop, _loop_thread
    if _loop is not None:
        return
    _loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(_loop)
        _loop.run_forever()

    import threading

    _loop_thread = threading.Thread(target=_run, daemon=True)
    _loop_thread.start()


_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_thread = None


def _run_async(coro):
    """Запускает корутину в фоновом loop'е и дожидается результата."""
    _ensure_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=120)


def _cleanup():
    now = time.time()
    expired = [k for k, v in _states.items() if (now - v.created_at) > STATE_TTL_SECONDS]
    for token in expired:
        _states.pop(token, None)
        c = _clients.pop(token, None)
        if c:
            _run_async(c.disconnect())
    # чистим и старые attempt-окна
    for ip in [k for k, v in _attempts.items() if now - v.window_start > 2 * WINDOW_SECONDS]:
        _attempts.pop(ip, None)


def _api_file_for_user(user_id: int) -> str:
    return f"telegram_api-{user_id}.json"


def _save_api(user_id: int, api_id: int, api_hash: str) -> None:
    path = _api_file_for_user(user_id)
    with open(path, "w", encoding="utf-8") as f:
        import json

        json.dump({"api_id": api_id, "api_hash": api_hash}, f, indent=2)


def _rename_session(temp_name: str, user_id: int) -> str:
    src = os.path.join(ROOT, f"{temp_name}.session")
    dst = os.path.join(ROOT, f"nova-{user_id}.session")
    if not os.path.exists(src):
        raise FileNotFoundError(f"Session file not found: {src}")
    if os.path.exists(dst):
        os.remove(dst)
    os.rename(src, dst)
    return dst


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

BASE_CSS = """
:root { color-scheme: dark; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 0; background: #0b0f17; color: #e7eefc; }
.wrap { max-width: 820px; margin: 0 auto; padding: 32px 16px; }
.card { background: #111a2b; border: 1px solid #1f2b44; border-radius: 16px; padding: 20px; }
h1 { margin: 0 0 8px; font-size: 22px; }
p { margin: 0 0 14px; color: #b7c7e6; line-height: 1.45; }
label { display: block; margin: 10px 0 6px; color: #cfe0ff; font-weight: 600; }
input { width: 100%; box-sizing: border-box; border-radius: 12px; border: 1px solid #263656; background: #0b1220; color: #e7eefc; padding: 12px 12px; }
button { margin-top: 14px; border: 0; border-radius: 12px; background: #4b7bff; color: white; padding: 12px 14px; font-weight: 700; cursor: pointer; }
button:hover { filter: brightness(1.05); }
.err { background: #2a1520; border: 1px solid #5a2136; color: #ffd6e6; padding: 12px; border-radius: 12px; margin: 12px 0; }
.ok { background: #13251c; border: 1px solid #254c36; color: #d9ffe9; padding: 12px; border-radius: 12px; margin: 12px 0; }
.muted { color: #98acd3; font-size: 13px; }
code { background: #0b1220; border: 1px solid #263656; padding: 2px 6px; border-radius: 8px; }
a { color: #9db7ff; }
.row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.steps { display: flex; gap: 8px; margin-bottom: 16px; }
.step { flex: 1; height: 4px; border-radius: 2px; background: #1f2b44; }
.step.done { background: #4b7bff; }
.step.active { background: #6b9bff; }
@media (max-width: 640px) { .row { grid-template-columns: 1fr; } }
"""

INDEX_HTML = """
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{ title }}</title>
    <style>""" + BASE_CSS + """</style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <div class="steps"><div class="step active"></div><div class="step"></div><div class="step"></div></div>
        <h1>NovaUB Authentication</h1>
        <p>Аутентификация сессии <code>nova-&lt;id&gt;.session</code> для вашего юзербота.</p>
        <p class="muted">API ID / API HASH берутся на <code>my.telegram.org</code>. Они нужны один раз.</p>

        {% if error %}<div class="err"><b>Ошибка:</b> {{ error }}</div>{% endif %}

        <form method="post" action="/start">
          <div class="row">
            <div>
              <label>API ID</label>
              <input name="api_id" inputmode="numeric" placeholder="123456" required autofocus />
            </div>
            <div>
              <label>API HASH</label>
              <input name="api_hash" placeholder="0123456789abcdef..." required />
            </div>
          </div>
          <label>Телефон</label>
          <input name="phone" inputmode="tel" placeholder="+799****4567" required />
          <button type="submit">Отправить код</button>
        </form>
      </div>
    </div>
  </body>
</html>
"""

PASSWORD_PANEL_HTML = """
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{ title }}</title>
    <style>""" + BASE_CSS + """</style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <h1>🔒 Доступ к панели</h1>
        <p>Эта панель управляет входом в Telegram-аккаунт. Введите пароль панели.</p>
        {% if error %}<div class="err"><b>Ошибка:</b> {{ error }}</div>{% endif %}
        {% if generated %}<div class="ok"><b>Сгенерирован случайный пароль:</b><br /><code>{{ generated }}</code><br />Сохраните его. Больше он показан не будет.</div>{% endif %}
        <form method="post" action="/panel-login">
          <label>Пароль панели</label>
          <input name="password" type="password" required autofocus />
          <button type="submit">Войти</button>
        </form>
      </div>
    </div>
  </body>
</html>
"""

CODE_HTML = """
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{ title }}</title>
    <style>""" + BASE_CSS + """</style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <div class="steps"><div class="step done"></div><div class="step active"></div><div class="step"></div></div>
        <h1>Введите код</h1>
        <p>Код отправлен на номер <code>{{ phone }}</code>. Если включена 2FA — после кода попросим пароль.</p>

        {% if error %}<div class="err"><b>Ошибка:</b> {{ error }}</div>{% endif %}

        <form method="post" action="/verify-code">
          <input type="hidden" name="token" value="{{ token }}" />
          <label>Код из Telegram</label>
          <input name="code" inputmode="numeric" placeholder="12345" required autofocus />
          <button type="submit">Подтвердить</button>
        </form>
      </div>
    </div>
  </body>
</html>
"""

PASSWORD_HTML = """
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{ title }}</title>
    <style>""" + BASE_CSS + """</style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <div class="steps"><div class="step done"></div><div class="step done"></div><div class="step active"></div></div>
        <h1>2FA пароль</h1>
        <p>Для аккаунта включена облачная парольная защита (2FA). Введите пароль, чтобы завершить авторизацию.</p>
        {% if error %}<div class="err"><b>Ошибка:</b> {{ error }}</div>{% endif %}
        <form method="post" action="/verify-password">
          <input type="hidden" name="token" value="{{ token }}" />
          <label>Пароль</label>
          <input name="password" type="password" required autofocus />
          <button type="submit">Завершить вход</button>
        </form>
      </div>
    </div>
  </body>
</html>
"""

SUCCESS_HTML = """
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{ title }}</title>
    <style>""" + BASE_CSS + """</style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <div class="steps"><div class="step done"></div><div class="step done"></div><div class="step done"></div></div>
        <h1>Готово</h1>
        <div class="ok"><b>Сессия создана:</b> <code>{{ session_file }}</code></div>
        <p>Юзербот готов к работе. Запустите: <code>python novaub.py</code></p>
        <p class="muted">API данные сохранены в <code>{{ api_file }}</code>.</p>
        <p><a href="/">Создать ещё одну сессию</a></p>
      </div>
    </div>
  </body>
</html>
"""


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    app = Flask(__name__)

    panel_hash, generated = _panel_password_hash()
    if generated:
        print("\n" + "=" * 60)
        print("🔒 Web panel password (сохраните, больше не покажется):")
        print(f"   {generated}")
        print("=" * 60 + "\n")

    @app.get("/")
    def index():
        _cleanup()
        return render_template_string(INDEX_HTML, title=APP_TITLE, error=request.args.get("error"))

    @app.post("/panel-login")
    def panel_login():
        password = request.form.get("password") or ""
        if _rate_limit_hit():
            return render_template_string(PASSWORD_PANEL_HTML, title=APP_TITLE, error=_rate_limit_error(), generated=None)
        if _verify_password(password, panel_hash):
            resp = redirect("/")
            # подписанная cookie на сессию панели
            resp.set_cookie("novaub_panel", _sign_cookie("ok"), httponly=True, max_age=STATE_TTL_SECONDS)
            return resp
        return render_template_string(PASSWORD_PANEL_HTML, title=APP_TITLE, error="Неверный пароль панели.", generated=None)

    @app.before_request
    def _require_panel_auth():
        # Разрешаем только страницу входа в саму панель и статику
        if request.path in ("/panel-login",):
            return None
        cookie = request.cookies.get("novaub_panel")
        if not cookie or not _verify_cookie(cookie):
            return render_template_string(
                PASSWORD_PANEL_HTML, title=APP_TITLE, error=None, generated=None
            ), 401
        return None

    @app.post("/start")
    def start():
        _cleanup()
        if _rate_limit_hit():
            return render_template_string(INDEX_HTML, title=APP_TITLE, error=_rate_limit_error())

        try:
            api_id = int((request.form.get("api_id") or "").strip())
            api_hash = (request.form.get("api_hash") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            if not api_hash or not phone:
                raise ValueError("Заполните все поля.")
        except Exception:
            return render_template_string(
                INDEX_HTML, title=APP_TITLE, error="Неверные данные (api_id/api_hash/phone)."
            )

        token = secrets.token_urlsafe(24)
        session_name = f"temp-web-{token}"

        async def _connect_and_send_code():
            from core import config as nova_config

            client = TelegramClient(session_name, api_id, api_hash)
            # protection mode safe — иначе 2FA-вход упадёт на GetPasswordRequest
            nova_config.apply_to_client(client, nova_config.load(0))
            await client.connect()
            sent = await client.send_code_request(phone)
            return client, sent.phone_code_hash

        try:
            client, phone_code_hash = _run_async(_connect_and_send_code())
        except PhoneNumberInvalidError:
            return render_template_string(INDEX_HTML, title=APP_TITLE, error="Неверный номер телефона.")
        except FloodWaitError as e:
            return render_template_string(
                INDEX_HTML, title=APP_TITLE, error=f"FloodWait: подождите {e.seconds}с."
            )
        except Exception as e:
            return render_template_string(
                INDEX_HTML, title=APP_TITLE, error=f"Telegram API error: {type(e).__name__}"
            )

        state = LoginState(
            token=token,
            created_at=time.time(),
            api_id=api_id,
            api_hash=api_hash,
            phone=phone,
            session_name=session_name,
            phone_code_hash=phone_code_hash,
        )
        _states[token] = state
        _clients[token] = client

        return render_template_string(CODE_HTML, title=APP_TITLE, token=token, phone=phone, error=None)

    def _get_state_and_client(token: str):
        _cleanup()
        st = _states.get(token)
        c = _clients.get(token)
        if not st or not c:
            return None, None
        return st, c

    @app.post("/verify-code")
    def verify_code():
        if _rate_limit_hit():
            return render_template_string(CODE_HTML, title=APP_TITLE, token="", phone="", error=_rate_limit_error())

        token = (request.form.get("token") or "").strip()
        code = (request.form.get("code") or "").strip().replace(" ", "")
        st, c = _get_state_and_client(token)
        if not st or not c:
            return redirect("/?error=" + "Сессия входа истекла, начните заново.")

        async def _sign_in():
            return await c.sign_in(phone=st.phone, code=code, phone_code_hash=st.phone_code_hash)

        try:
            _run_async(_sign_in())
        except SessionPasswordNeededError:
            return render_template_string(PASSWORD_HTML, title=APP_TITLE, token=token, error=None)
        except PhoneCodeInvalidError:
            return render_template_string(
                CODE_HTML, title=APP_TITLE, token=token, phone=st.phone, error="Неверный код."
            )
        except PhoneCodeExpiredError:
            return redirect("/?error=" + "Код истёк, начните заново.")
        except Exception as e:
            return render_template_string(
                CODE_HTML, title=APP_TITLE, token=token, phone=st.phone,
                error=f"Telegram API error: {type(e).__name__}",
            )

        return _finalize_login(token, st, c)

    @app.post("/verify-password")
    def verify_password():
        if _rate_limit_hit():
            return render_template_string(PASSWORD_HTML, title=APP_TITLE, token="", error=_rate_limit_error())

        token = (request.form.get("token") or "").strip()
        password = request.form.get("password") or ""
        st, c = _get_state_and_client(token)
        if not st or not c:
            return redirect("/?error=" + "Сессия входа истекла, начните заново.")

        async def _check_password():
            return await c.sign_in(password=password)

        try:
            _run_async(_check_password())
        except PasswordHashInvalidError:
            return render_template_string(
                PASSWORD_HTML, title=APP_TITLE, token=token, error="Неверный пароль."
            )
        except Exception as e:
            return render_template_string(
                PASSWORD_HTML, title=APP_TITLE, token=token,
                error=f"Telegram API error: {type(e).__name__}",
            )

        return _finalize_login(token, st, c)

    def _finalize_login(token: str, st: LoginState, c: TelegramClient):
        try:
            async def _get_me_and_disconnect():
                me = await c.get_me()
                await c.disconnect()
                return me

            me = _run_async(_get_me_and_disconnect())
            user_id = int(me.id)
            _save_api(user_id, st.api_id, st.api_hash)
            session_file = _rename_session(st.session_name, user_id)
        except Exception as e:
            try:
                _run_async(c.disconnect())
            except Exception:
                pass
            _states.pop(token, None)
            _clients.pop(token, None)
            return render_template_string(
                INDEX_HTML, title=APP_TITLE, error=f"Не удалось завершить вход: {type(e).__name__}"
            )
        finally:
            _states.pop(token, None)
            _clients.pop(token, None)

        return render_template_string(
            SUCCESS_HTML,
            title=APP_TITLE,
            session_file=session_file,
            api_file=_api_file_for_user(user_id),
        )

    return app


# ---------------------------------------------------------------------------
# Cookie-подпись для доступа к панели
# ---------------------------------------------------------------------------

def _cookie_secret() -> bytes:
    from core import config as nova_config

    cfg = nova_config.load(0)
    web = cfg.web or {}
    secret = web.get("cookie_secret")
    if not secret:
        secret = secrets.token_hex(32)
        try:
            updated = dict(cfg)
            updated["web"] = {**(updated.get("web") or {}), "cookie_secret": secret}
            nova_config.save(0, updated)
        except Exception:
            pass
    return secret.encode("utf-8")


def _sign_cookie(value: str) -> str:
    secret = _cookie_secret()
    sig = hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{sig}"


def _verify_cookie(cookie: str) -> bool:
    if not cookie or "." not in cookie:
        return False
    value, _, sig = cookie.rpartition(".")
    expected = hmac.new(_cookie_secret(), value.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


if __name__ == "__main__":
    host = os.environ.get("FORELKA_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("FORELKA_WEB_PORT", "8000"))
    app = create_app()
    app.run(host=host, port=port, debug=False, threaded=True)
