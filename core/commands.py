"""Декораторы NovaUB для объявления команд, инлайн-хендлеров и хуков.

Новый стиль:

    from core.commands import command, inline, hook

    @command("ping", aliases=["p"], desc="Задержка", cooldown=3)
    async def ping_cmd(client, message, args):
        ...

    @inline("ping")
    async def inline_ping(event):
        ...

    @hook("startup")
    async def on_start(kernel):
        ...

Декораторы не выполняют регистрацию — они только помечают функцию.
Регистрацией занимается loader: он находит все помеченные функции в модуле
и строит команды/хуки. Старые модули с register() продолжают работать
(обратная совместимость через meta_lib).
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple


# ── Внутренние атрибуты на функциях ──────────────────────────────────────

_ATTR_COMMAND = "_novaub_command"
_ATTR_INLINE = "_novaub_inline"
_ATTR_HOOK = "_novaub_hook"

# Уровни доступа. Порядок — от слабого к сильному.
ACCESS_LEVELS = ("public", "trusted", "owner")


def _normalize_aliases(aliases: Optional[Any]) -> List[str]:
    if not aliases:
        return []
    if isinstance(aliases, str):
        aliases = [aliases]
    out: List[str] = []
    seen = set()
    for item in aliases:
        text = str(item).strip().lower().lstrip("./!")
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def command(
    name: str,
    *,
    aliases: Optional[Any] = None,
    desc: str = "",
    description: Optional[str] = None,
    usage: str = "",
    example: str = "",
    cooldown: float = 0.0,
    level: str = "owner",
    owner_only: bool = False,
    hidden: bool = False,
) -> Callable:
    """Объявляет команду модуля.

    Аргументы:
        name:       имя команды без префикса ("ping" → ".ping")
        aliases:    синонимы, регистрируются ядром
        desc:       короткое описание для .help
        usage:      как вызывать (".ping")
        example:    пример вызова
        cooldown:   секунд между вызовами для одного пользователя
        level:      "public" | "trusted" | "owner"
        owner_only: устаревший флаг, эквивалент level="owner"
        hidden:     не показывать в .help
    """
    resolved_level = "owner" if owner_only else level
    if resolved_level not in ACCESS_LEVELS:
        resolved_level = "owner"

    spec: Dict[str, Any] = {
        "name": (name or "").strip().lower().lstrip("./!"),
        "aliases": _normalize_aliases(aliases),
        "desc": description or desc,
        "usage": usage,
        "example": example,
        "cooldown": float(cooldown or 0.0),
        "level": resolved_level,
        "hidden": bool(hidden),
    }

    def decorator(fn: Callable) -> Callable:
        setattr(fn, _ATTR_COMMAND, spec)
        return fn

    return decorator


def inline(name: str, *, desc: str = "", hidden: bool = False) -> Callable:
    """Объявляет инлайн-хендлер: @inline("ping") → @bot ping.

    Функция получает событие инлайн-запроса (events.InlineQuery.Event).
    Проверка доступа выполняется ядром.
    """
    spec: Dict[str, Any] = {
        "name": (name or "").strip().lower().lstrip("./!"),
        "desc": desc,
        "hidden": bool(hidden),
    }

    def decorator(fn: Callable) -> Callable:
        setattr(fn, _ATTR_INLINE, spec)
        return fn

    return decorator


def hook(event_name: str) -> Callable:
    """Объявляет хук жизненного цикла модуля.

    События: "startup" (модуль загружен/юзербот стартовал),
    "shutdown" (юзербот останавливается/модуль выгружается).
    """
    spec: Dict[str, Any] = {
        "event": (event_name or "").strip().lower(),
    }

    def decorator(fn: Callable) -> Callable:
        setattr(fn, _ATTR_HOOK, spec)
        return fn

    return decorator


# ── Сборщик ──────────────────────────────────────────────────────────────


def collect(module: Any) -> Dict[str, List[Dict[str, Any]]]:
    """Собирает все декорированные функции из модуля.

    Возвращает {"commands": [...], "inlines": [...], "hooks": [...]}.
    Каждая запись команды — словарь с ключами name/aliases/desc/usage/
    example/cooldown/level/hidden + "func" и "module".
    """
    commands: List[Dict[str, Any]] = []
    inlines: List[Dict[str, Any]] = []
    hooks: List[Dict[str, Any]] = []

    if not module:
        return {"commands": commands, "inlines": inlines, "hooks": hooks}

    module_name = getattr(module, "__name__", "")

    for attr_name in dir(module):
        if attr_name.startswith("__"):
            continue
        try:
            fn = getattr(module, attr_name)
        except Exception:
            continue

        cmd_spec = getattr(fn, _ATTR_COMMAND, None)
        if cmd_spec is not None and callable(fn):
            entry = dict(cmd_spec)
            entry["func"] = fn
            entry["module"] = module_name
            if not entry.get("name"):
                continue
            commands.append(entry)
            continue

        inline_spec = getattr(fn, _ATTR_INLINE, None)
        if inline_spec is not None and callable(fn):
            entry = dict(inline_spec)
            entry["func"] = fn
            entry["module"] = module_name
            if not entry.get("name"):
                continue
            inlines.append(entry)
            continue

        hook_spec = getattr(fn, _ATTR_HOOK, None)
        if hook_spec is not None and callable(fn):
            entry = dict(hook_spec)
            entry["func"] = fn
            entry["module"] = module_name
            hooks.append(entry)

    return {"commands": commands, "inlines": inlines, "hooks": hooks}


def has_decorators(module: Any) -> bool:
    """ True если модуль использует новый стиль (есть хоть одна декорированная
    функция). Используется loader'ом, чтобы решить, вызывать ли register()."""
    if not module:
        return False
    try:
        collected = collect(module)
    except Exception:
        return False
    return bool(collected["commands"] or collected["inlines"] or collected["hooks"])


# ── Кулдаун (ядровый, общий для всех команд) ──────────────────────────────


class Cooldown:
    """Пер-пользовательный кулдаун для команд."""

    def __init__(self) -> None:
        self._timestamps: Dict[Tuple[str, int], float] = {}

    def check(self, command_name: str, user_id: int, cooldown: float) -> bool:
        """True — можно выполнять, False — кулдаун ещё не прошёл."""
        if not cooldown or cooldown <= 0:
            return True
        key = (command_name, user_id)
        now = time.monotonic()
        last = self._timestamps.get(key)
        if last is not None and (now - last) < cooldown:
            return False
        self._timestamps[key] = now
        return True

    def clear(self) -> None:
        self._timestamps.clear()
