"""Единый конфиг NovaUB.

До этого настройки были размазаны по трём файлам:
  config-<id>.json        — prefix, owners, aliases, management group (modules)
  kernel_config-<id>.json — api_id/api_hash и настройки ядра
  telegram_api-<id>.json  — api_id/api_hash (web login)

Теперь всё лежит в config-<id>.json. Старые ключи остаются на верхнем уровне
(модули читают их напрямую — это не ломается), новые_settings уходят в секции:

  {
    "prefix": ".",                 # совместимость
    "owners": [...],
    "aliases": {...},
    "management_group_id": -100...,
    "management_topics": {...},
    "api":     {"api_id": ..., "api_hash": "..."},
    "protection": {"mode": "safe", "allowed_requests": ["GetPasswordRequest"]},
    "web":    {"password_hash": "..."},
    "modules": {"...": {...}}
  }

Старые файлы при первом чтении сливаются в новый и больше не нужны.
"""

from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger("NovaUBConfig")

# Корень проекта: ядро лежит в core/, но все данные (конфиги, БД, логи,
# сессии) должны жить в корне, а не migrate вместе с кодом.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILE = "config-{user_id}.json"
LEGACY_KERNEL_FILE = "kernel_config-{user_id}.json"
LEGACY_API_FILE = "telegram_api-{user_id}.json"

# Значения по умолчанию. Любой отсутствующий ключ заполняется отсюда.
DEFAULTS = {
    "prefix": ".",
    "owners": [],
    "aliases": {},
    "management_group_id": None,
    "management_topics": {},
    "api": {"api_id": None, "api_hash": ""},
    # Telethon-MCUB protection. strict не даёт войти в аккаунты с 2FA,
    # поэтому безопасный дефолт — 'safe' (см. main.py / protection mode).
    "protection": {"mode": "safe", "allowed_requests": []},
    "web": {"password_hash": None},
    "modules": {},
}

# Типы для валидации: ключ -> (тип, обязательный ли)
SCHEMA = {
    "prefix": (str, False),
    "owners": (list, False),
    "aliases": (dict, False),
    "management_group_id": (int, False),
    "management_topics": (dict, False),
    "api": (dict, False),
    "protection": (dict, False),
    "web": (dict, False),
    "modules": (dict, False),
}

VALID_PROTECTION_MODES = ("off", "safe", "strict", "custom")

# Кэш: user_id -> (mtime, config). Чтобы не читать файл на каждое сообщение.
_cache: dict[int, tuple[float, "Config"]] = {}


def _config_path(user_id) -> str:
    return os.path.join(PROJECT_ROOT, CONFIG_FILE.format(user_id=user_id))


def _read_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("Не удалось прочитать %s: %s", path, e)
    return {}


def _write_json(path: str, data: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # атомарно — никогда не попортим конфиг


def _migrate_legacy(user_id) -> None:
    """Сливает kernel_config-<id>.json и telegram_api-<id>.json в config-<id>.json.

    Выполняется один раз — только если есть легаси-файл и в новом конфиге
    ещё нет секции api.
    """
    path = _config_path(user_id)
    cfg = _read_json(path)

    api = cfg.get("api") or {}
    changed = False

    for legacy in (
        os.path.join(PROJECT_ROOT, LEGACY_API_FILE.format(user_id=user_id)),
        os.path.join(PROJECT_ROOT, LEGACY_KERNEL_FILE.format(user_id=user_id)),
    ):
        if not os.path.exists(legacy):
            continue
        legacy_data = _read_json(legacy)
        legacy_api_id = legacy_data.get("api_id")
        legacy_api_hash = legacy_data.get("api_hash")
        if legacy_api_id and not api.get("api_id"):
            api["api_id"] = int(legacy_api_id)
            api["api_hash"] = str(legacy_api_hash or "")
            changed = True
        # Любые другие настройки ядра переносим как есть, не затирая новые.
        for k, v in legacy_data.items():
            if k in ("api_id", "api_hash"):
                continue
            cfg.setdefault(k, v)
            changed = True

    if not changed:
        return

    cfg["api"] = api
    _write_json(path, cfg)
    logger.info("Легаси-конфиги слиты в %s", path)


def _validate(cfg: dict) -> dict:
    """Принудительно приводит конфиг к схеме, не роняя приложение.

    Ключи из SCHEMA валидируются/коерсируются; остальные сохраняем как есть,
    чтобы не потерять настройки ядра и модулей, не описанные в схеме.
    """
    out = dict(cfg)
    for key, (expected_type, _) in SCHEMA.items():
        value = out.get(key, DEFAULTS.get(key))
        try:
            if value is None:
                value = DEFAULTS.get(key)
            elif not isinstance(value, expected_type):
                # Пытаемся coerce, иначе берём дефолт.
                if expected_type is int:
                    value = int(value)
                elif expected_type is str:
                    value = str(value)
                elif expected_type is list:
                    value = list(value) if isinstance(value, (tuple, set)) else DEFAULTS.get(key)
                elif expected_type is dict:
                    value = DEFAULTS.get(key)
        except Exception:
            value = DEFAULTS.get(key)
        out[key] = value if value is not None else DEFAULTS.get(key)

    # owners должны быть int-ами
    out["owners"] = [int(o) for o in out["owners"] if isinstance(o, (int, str)) and str(o).lstrip("-").isdigit()]

    # protection
    prot = out["protection"] or {}
    mode = str(prot.get("mode", "safe")).lower()
    if mode not in VALID_PROTECTION_MODES:
        logger.warning("Неизвестный protection mode %r, использую 'safe'", mode)
        mode = "safe"
    allowed = prot.get("allowed_requests") or []
    if not isinstance(allowed, list):
        allowed = []
    out["protection"] = {"mode": mode, "allowed_requests": [str(a) for a in allowed]}

    # api
    api = out["api"] or {}
    try:
        api_id = int(api.get("api_id")) if api.get("api_id") else None
    except Exception:
        api_id = None
    out["api"] = {"api_id": api_id, "api_hash": str(api.get("api_hash") or "")}

    return out


class Config(dict):
    """dict с доступом через атрибуты: cfg.protection['mode']."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(item)

    def get_protection_mode(self) -> str:
        return self.protection["mode"]

    def get_protection_allowed(self) -> list[str]:
        return self.protection["allowed_requests"]


def load(user_id, *, no_cache: bool = False) -> Config:
    """Читает единый конфиг аккаунта. Никогда не бросает исключений."""
    user_id = int(user_id)
    path = _config_path(user_id)

    if not no_cache:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        cached = _cache.get(user_id)
        if cached and cached[0] == mtime:
            return cached[1]

    try:
        _migrate_legacy(user_id)
    except Exception as e:
        logger.warning("Ошибка миграции конфига: %s", e)

    raw = _read_json(path)
    if not raw:
        # Нет конфига вообще — оставляем дефолты, сохранять не будем:
        # он создастся при первом реальном изменении.
        raw = {}

    cfg = Config(_validate(raw))

    # Кэшируем только если файл существует.
    try:
        _cache[user_id] = (os.path.getmtime(path), cfg)
    except OSError:
        pass

    return cfg


def save(user_id, cfg: dict) -> None:
    """Записывает конфиг и инвалидирует кэш."""
    user_id = int(user_id)
    path = _config_path(user_id)
    data = _validate(dict(cfg))
    _write_json(path, data)
    try:
        _cache[user_id] = (os.path.getmtime(path), Config(data))
    except OSError:
        _cache.pop(user_id, None)


def update(user_id, **kwargs) -> Config:
    """Меняет несколько ключей и сохраняет: update(uid, prefix='!')."""
    cfg = load(user_id, no_cache=True)
    cfg.update(kwargs)
    save(user_id, cfg)
    return cfg


def get(user_id, key, default=None):
    """Безопасное чтение одного ключа."""
    try:
        return load(user_id).get(key, default)
    except Exception:
        return default


def get_api_credentials(user_id):
    """Возвращает (api_id, api_hash) или (None, None)."""
    api = get(user_id, "api") or {}
    return api.get("api_id"), api.get("api_hash")


def is_owner(user_id, check_id) -> bool:
    """Владелец ли пользователь. Сам аккаунт — всегда владелец."""
    try:
        user_id = int(user_id)
        check_id = int(check_id)
    except Exception:
        return False
    if check_id == user_id:
        return True
    return check_id in (get(user_id, "owners") or [])


def invalidate(user_id=None) -> None:
    """Сброс кэша (например, после внешней записи в файл)."""
    if user_id is None:
        _cache.clear()
    else:
        _cache.pop(int(user_id), None)


# ---------------------------------------------------------------------------
# Protection policy
# ---------------------------------------------------------------------------

def _resolve_request_class(name: str):
    """Ищет TLRequest-класс по имени в telethon.tl.functions.*."""
    if not name:
        return None
    try:
        from telethon.tl import TLRequest
        import telethon.tl.functions as functions
    except Exception:
        return None

    namespaces = ["account", "auth", "users", "messages", "channels", "bots", "payments", "stats"]
    for ns in namespaces:
        module = getattr(functions, ns, None)
        if module is None:
            continue
        cls = getattr(module, name, None)
        if isinstance(cls, type) and issubclass(cls, TLRequest):
            return cls
    return None


def build_protection_policy(cfg):
    """Собирает ProtectionPolicy из конфига.

    mode = 'safe' по умолчанию (разрешает вход в аккаунты с 2FA),
    whitelist добавляет отдельные опасные запросы в allowed_requests.
    """
    from telethon.client.protection import build_protection_policy as _build

    prot = (cfg or {}).get("protection") or {}
    mode = str(prot.get("mode", "safe")).lower()
    if mode not in VALID_PROTECTION_MODES:
        mode = "safe"

    allowed = []
    for name in prot.get("allowed_requests") or []:
        cls = _resolve_request_class(name)
        if cls is not None and cls not in allowed:
            allowed.append(cls)

    return _build(mode, allowed_requests=tuple(allowed))


def apply_to_client(client, cfg=None) -> None:
    """Ставит protection policy на уже созданный клиент."""
    if cfg is None:
        cfg = load(getattr(client, "_self_id", 0))
    try:
        client._protection_policy = build_protection_policy(cfg)
    except Exception as e:
        logger.warning("Не удалось применить protection policy: %s", e)
