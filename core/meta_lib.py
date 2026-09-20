"""Метаданные модулей NovaUB.

Мета — это плоский словарь, который модуль объявляет как __meta__:

    __meta__ = {
        "name":        "AutoReply",
        "version":     "1.2.0",
        "author":      "NovaUB",
        "description": "Автоответчик в ЛС, когда вы заняты.",
        "requires":    ["aiohttp"],
    }

Ключи (всё остальное падает в "extra" и переживает валидацию):
    name, version, author, description, requires

Поддерживаются и dunder-атрибуты: __author__, __version__,
__description__, __requires__ и первая строка __doc__.

Описания команд больше не ищутся эвристиками в строках: команда сама
объявляет свой desc через @command(...). Этот модуль остаётся как
тонкий слой обратной совместимости для старых модулей.
"""

from __future__ import annotations

import re

from typing import Any, Dict, Iterable, List, Optional


META_FIELDS = {
    "name",
    "version",
    "author",
    "description",
    "requires",
}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_command_name(value: Any) -> str:
    text = _as_text(value)
    if not text:
        return ""
    text = text.strip()
    if text and text[0] in (".", "/", "!", "?"):
        text = text[1:]
    return text.strip().lower()


def _normalize_commands(value: Optional[Iterable[str]]) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value)
    out: List[str] = []
    seen = set()
    for item in items:
        text = _as_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _normalize_requires(value: Optional[Iterable[str]]) -> List[str]:
    """Нормализует список зависимостей (pip-пакеты)."""
    if not value:
        return []
    if isinstance(value, str):
        # Поддержка строки: "aiohttp, pillow>=1.0" или "aiohttp pillow"
        items = re.split(r"[,\s]+", value.strip())
        items = [i.strip() for i in items if i.strip()]
    else:
        items = list(value)
    out: List[str] = []
    seen = set()
    for item in items:
        pkg = _as_text(item).strip()
        if not pkg or pkg in seen:
            continue
        seen.add(pkg)
        out.append(pkg)
    return out


def _merge_commands(base: List[str], extra: Optional[Iterable[str]]) -> List[str]:
    out = list(base or [])
    for item in _normalize_commands(extra):
        if item not in out:
            out.append(item)
    return out


def _coerce_meta(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return dict(raw)
    if hasattr(raw, "to_dict") and callable(raw.to_dict):
        try:
            return dict(raw.to_dict())
        except Exception:
            return None
    if hasattr(raw, "__dict__"):
        try:
            return dict(raw.__dict__)
        except Exception:
            return None
    return None


def build_meta(
    name: str = "",
    version: str = "",
    author: str = "",
    description: str = "",
    commands: Optional[Iterable[str]] = None,
    requires: Optional[Iterable[str]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "name": _as_text(name),
        "version": _as_text(version),
        "author": _as_text(author),
        "description": _as_text(description),
        "commands": _normalize_commands(commands),
        "requires": _normalize_requires(requires),
    }
    if extra:
        meta["extra"] = dict(extra)
    return meta


def normalize_meta(
    raw: Any,
    fallback_name: str,
    commands: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    meta = build_meta(name=fallback_name)
    raw_meta = _coerce_meta(raw)
    extra: Dict[str, Any] = {}

    if raw_meta:
        for key, value in raw_meta.items():
            if key == "commands":
                meta["commands"] = _merge_commands(meta["commands"], value)
                continue
            if key == "requires":
                meta["requires"] = _normalize_requires(value)
                continue
            if key in META_FIELDS:
                text = _as_text(value)
                if text:
                    meta[key] = text
                continue
            extra[key] = value

    if commands:
        meta["commands"] = _merge_commands(meta["commands"], commands)

    if not meta["name"]:
        meta["name"] = _as_text(fallback_name)

    if extra:
        meta["extra"] = extra

    return meta


def read_module_meta(
    module: Any,
    fallback_name: str,
    commands: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    raw = getattr(module, "__meta__", None) if module else None
    meta = normalize_meta(raw, fallback_name=fallback_name, commands=commands)
    if not module:
        return meta

    # dunder-атрибуты — обратная совместимость
    attr_map = {
        "__author__": "author",
        "__version__": "version",
        "__description__": "description",
        "__requires__": "requires",
    }

    for attr, key in attr_map.items():
        value = _as_text(getattr(module, attr, ""))
        if value and not meta.get(key):
            meta[key] = value

    if not meta.get("description"):
        doc = _as_text(getattr(module, "__doc__", ""))
        if doc:
            meta["description"] = doc.splitlines()[0].strip()

    return meta


def extract_command_descriptions(raw: Any) -> Dict[str, str]:
    """Устаревший интерфейс. Описания команд теперь живут в @command(desc=...).

    Оставлен для старых модулей и help.py: пытается вытащить описания из
    мета-словаря, если они там есть (dict-форма commands), и из dunder-функций
    cmdname_desc / cmdname_help, которые иногда использовались раньше.
    """
    meta = _coerce_meta(raw) or {}
    result: Dict[str, str] = {}

    commands = meta.get("commands")
    if isinstance(commands, dict):
        for key, val in commands.items():
            name = _normalize_command_name(key)
            if not name:
                continue
            if isinstance(val, dict):
                desc = val.get("description") or val.get("desc") or val.get("about") or ""
            else:
                desc = val
            result[name] = _as_text(desc)

    return result
