"""Модуль перевода текста.

Команды:
  .tr <текст>          — перевести на язык по умолчанию (ru)
  .tr <язык> <текст>   — перевести на указанный язык
  .tr                  — перевести сообщение в ответе

Примеры:
  .tr hello world
  .tr en привет мир

Инлайн:
  @бот tr <текст>
"""

__meta__ = {
    "name": "Translate",
    "version": "1.0.0",
    "author": "FBurgerx",
    "description": "Перевод текста на 90+ языков",
    "commands": ["tr"],
}

import asyncio
import json
import os

from telethon import events

# Сервис перевода — бесплатный, без ключа (лимит ~5000 слов/день).
# MyMemory сам определяет исходный язык через «Autodetect».
MYMEMORY_URL = "https://api.mymemory.translated.net/get"

# Язык по умолчанию, если не указан явно
DEFAULT_TARGET = "ru"

# Кэш: язык перевода, выбранный юзером (user_id → код языка)
_user_lang = {}


def is_owner(kernel, user_id):
    """Проверка, является ли пользователь владельцем."""
    config_path = f"config-{kernel.client._self_id}.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                owners = config.get("owners", [])
                if kernel.client._self_id not in owners:
                    owners.append(kernel.client._self_id)
                return user_id in owners
        except Exception:
            pass
    return user_id == kernel.client._self_id


# Исходные языки для фолбэка: MyMemory отказывается переводить на тот же
# язык, что определил сам, поэтому для автоопределения перебираем популярные.
_FALLBACK_SOURCES = (
    "ru", "en", "de", "fr", "es", "it", "pt", "nl", "pl", "uk",
    "ja", "ko", "zh", "ar", "tr", "hi", "sv", "da", "fi", "no",
)


async def _translate(text: str, target: str, source: str = "Autodetect"):
    """Переводит текст через MyMemory. Возвращает (перевод, определённый язык).

    При ошибке возвращает (None, сообщение_об_ошибке).
    """
    text = text.strip()
    if not text:
        return None, "Нет текста для перевода."

    target = (target or DEFAULT_TARGET).strip().lower() or DEFAULT_TARGET
    source = (source or "Autodetect").strip() or "Autodetect"

    params = {
        "q": text,
        "langpair": f"{source}|{target}",
    }

    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                MYMEMORY_URL, params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None, f"Сервис перевода недоступен (HTTP {resp.status})."
                data = await resp.json()
    except asyncio.TimeoutError:
        return None, "Сервис перевода не ответил (таймаут)."
    except Exception as e:
        return None, f"Не удалось перевести: {e}"

    resp_data = (data or {}).get("responseData") or {}
    translation = resp_data.get("translatedText")
    if not translation:
        return None, "Пустой ответ от сервиса перевода."

    # MyMemory иногда присылает технические сообщения об ошибках текстом
    upper = translation.upper()
    if upper.startswith("PLEASE SELECT") or "IS AN INVALID" in upper:
        return None, "Неверный код языка. Пример: .tr en привет"

    return translation, source if source != "Autodetect" else None


async def translate(text: str, target: str):
    """Переводит текст на target с автоопределением исходного языка.

    MyMemory отказывается переводить, если исходный язык совпадает с
    целевым («PLEASE SELECT TWO DISTINCT LANGUAGES»), а код языка в
    запросе при этом не указан. Поэтому при автоопределении перебираем
    популярные исходные языки, пока не найдём подходящий.

    Возвращает (перевод, определённый язык).
    """
    # 1. Пробуем автоопределение
    tr, detected = await _translate(text, target)
    if tr is not None and detected is None:
        # язык не определился — подсказываем эвристикой
        guess = _guess_language(text)
        return tr, guess or detected

    # 2. Если не вышло — перебираем исходные языки
    last_err = None
    for src in _FALLBACK_SOURCES:
        if src == target:
            continue
        tr, detected = await _translate(text, target, source=src)
        if tr is not None and tr.strip() and tr.strip().upper() != text.strip().upper():
            return tr, src
        if tr is None:
            last_err = detected

    return None, last_err or "Не удалось перевести."


# Диапазоны Юникода для эвристического определения языка
_SCRIPTS = [
    ("ru", 0x0400, 0x04FF),   # кириллица
    ("ar", 0x0600, 0x06FF),
    ("he", 0x0590, 0x05FF),
    ("el", 0x0370, 0x03FF),   # греческий
    ("ja", 0x3040, 0x30FF),   # хирагана/катакана
    ("ja", 0x4E00, 0x9FFF),   # кандзи
    ("ko", 0xAC00, 0xD7AF),   # хангыль
    ("zh", 0x4E00, 0x9FFF),   # иджэ (китайские иероглифы)
    ("th", 0x0E00, 0x0E7F),
    ("hi", 0x0900, 0x097F),
]


def _guess_language(text: str) -> str:
    """Эвристическое определение языка по письменности."""
    counts = {}
    for ch in text:
        cp = ord(ch)
        if cp < 0x0370:
            continue
        for code, lo, hi in _SCRIPTS:
            if lo <= cp <= hi:
                counts[code] = counts.get(code, 0) + 1
                break
    if counts:
        best = max(counts, key=counts.get)
        # кандзи/иджэ — различаем грубо: если есть хирагана — японский
        if best == "zh" and any(0x3040 <= ord(c) <= 0x30FF for c in text):
            return "ja"
        return best
    # латиница — не определяем, MyMemory справится сам
    return ""


# Распространённые коды языков — всё остальное считаем текстом.
# Иначе «Привет как дела» разбивается как target=«привет» (3 буквы).
_LANG_CODES = frozenset("""
aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch
co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga
gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja
jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv
mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or
os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr
ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi
vo wa wo xh yi yo za zh zu
""".split())


def _parse_target(text: str) -> tuple:
    """Разбирает '<язык> <текст>' или просто '<текст>'.

    Язык засчитывается только при точном совпадении с кодом из списка.
    Возвращает (target, text).
    """
    parts = text.split(" ", 1)
    first = parts[0].strip().lower()
    if (
        len(first) <= 3
        and first in _LANG_CODES
        and len(parts) > 1 and parts[1].strip()
    ):
        return first, parts[1].strip()
    return DEFAULT_TARGET, text.strip()


def _lang_label(code: str) -> str:
    """Короткая подпись для кода языка."""
    if not code:
        return "?"
    return code.lower()


async def tr_cmd(client, message, args):
    """Перевести текст"""

    # .tr в ответе на сообщение — переводим текст исходного
    if not args:
        reply = await message.get_reply_message()
        if not reply or not (reply.message or reply.raw_text):
            await message.edit(
                "<blockquote><b>Использование:</b>\n"
                "<code>.tr &lt;текст&gt;</code> — перевести текст\n"
                "<code>.tr &lt;язык&gt; &lt;текст&gt;</code> — на указанный язык\n"
                "Или ответь на сообщение: <code>.tr</code></blockquote>",
                parse_mode="html",
            )
            return
        text = reply.message or reply.raw_text
        target = DEFAULT_TARGET
    else:
        target, text = _parse_target(" ".join(args))

    result = await message.edit(
        "<blockquote><b>Перевожу…</b></blockquote>", parse_mode="html"
    )

    translation, detected = await translate(text, target)

    if translation is None:
        await result.edit(
            f"<blockquote><b>Ошибка перевода</b>\n{detected}</blockquote>",
            parse_mode="html",
        )
        return

    lang_from = _lang_label(detected)
    lang_to = _lang_label(target)

    await result.edit(
        f"<blockquote><b>Перевод</b> {lang_from} → {lang_to}\n"
        f"<code>{translation}</code></blockquote>",
        parse_mode="html",
    )


# ── Инлайн: @бот tr <текст> ──────────────────────────────────────────────

async def inline_tr_handler(event: events.InlineQuery.Event):
    kernel = event.client.kernel
    user_id = event.sender_id
    query = event.text.strip()
    # Инлайн: @бот tr <текст>
    if not query.startswith("tr "):
        return
    args = query[3:].strip()
    if not args:
        return

    if not is_owner(kernel, user_id):
        builder = event.builder
        no_access = builder.article(
            title="⛔️ Нет доступа",
            description="Эта функция доступна только владельцу.",
            text="<blockquote><tg-emoji emoji-id=5778527486270770928>⛔️</tg-emoji> <b>Нет доступа.</b></blockquote>",
            parse_mode="html",
        )
        await event.answer([no_access])
        return

    # Язык по умолчанию для инлайна — из кэша юзера
    target = _user_lang.get(user_id, DEFAULT_TARGET)
    target, text = _parse_target(args)
    _user_lang[user_id] = target

    translation, detected = await translate(text, target)
    builder = event.builder

    if translation is None:
        err = builder.article(
            title="⚠️ Ошибка перевода",
            description=str(detected)[:120],
            text=f"<blockquote><b>Ошибка перевода</b>\n{detected}</blockquote>",
            parse_mode="html",
        )
        await event.answer([err])
        return

    lang_from = _lang_label(detected)
    lang_to = _lang_label(target)

    result = builder.article(
        title=f"Перевод {lang_from} → {lang_to}",
        description=translation[:120],
        text=f"<blockquote><b>Перевод</b> {lang_from} → {lang_to}\n"
             f"<code>{translation}</code></blockquote>",
        parse_mode="html",
    )
    await event.answer([result])


# ── Инлайн-команда для бота: /tr ─────────────────────────────────────────

async def bot_tr_handler(event: events.NewMessage.Event):
    kernel = event.client.kernel
    user_id = event.sender_id

    if not is_owner(kernel, user_id):
        await event.reply(
            "<blockquote><tg-emoji emoji-id=5778527486270770928>⛔️</tg-emoji> "
            "<b>Нет доступа.</b></blockquote>",
            parse_mode="html",
        )
        return

    text = event.message.text or ""
    args = text.split(" ", 1)
    payload = args[1].strip() if len(args) > 1 else ""

    reply = await event.get_reply_message()
    if not payload and reply and (reply.message or reply.raw_text):
        payload = reply.message or reply.raw_text

    if not payload:
        await event.reply(
            "<blockquote><b>Использование:</b> <code>/tr &lt;текст&gt;</code></blockquote>",
            parse_mode="html",
        )
        return

    translation, detected = await translate(payload, DEFAULT_TARGET)
    if translation is None:
        await event.reply(
            f"<blockquote><b>Ошибка перевода</b>\n{detected}</blockquote>",
            parse_mode="html",
        )
        return

    lang_from = _lang_label(detected)
    lang_to = _lang_label(DEFAULT_TARGET)

    await event.reply(
        f"<blockquote><b>Перевод</b> {lang_from} → {lang_to}\n"
        f"<code>{translation}</code></blockquote>",
        parse_mode="html",
    )


def register(app, commands, module_name, kernel=None):
    commands["tr"] = {"func": tr_cmd, "module": module_name}

    if kernel is not None and hasattr(kernel, "register_bot_command") and hasattr(kernel, "register_inline_handler"):
        if hasattr(kernel, "inline_bot") and kernel.inline_bot and kernel.inline_bot.bot_client:
            kernel.inline_bot.bot_client.kernel = kernel

        kernel.register_bot_command("tr", bot_tr_handler)
        kernel.register_inline_handler(inline_tr_handler)
        print("[Translate] Инлайн-команды зарегистрированы.")
