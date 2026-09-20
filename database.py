"""Единый доступ к SQLite-базе NovaUB.

До этого база открывалась в каждом вызове:
  async with aiosqlite.connect("forelka_config.db") as db: ...

каждый такой open/close — это новый коннект, транзакция и fsync. А старый
database.py ещё и держал один синхронный коннект с глобальным локом, блокируя
весь event loop на каждом запросе.

Теперь — одно постоянное соединение с одним async-локом. Таблицы:
  module_configs (module_name, key, value)  — настройки модулей
  module_state  (module_name, key, value)   — состояние модулей (persist #7)
  kv            (key, value)                — произвольные пары ядра
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger("NovaUBDB")

DB_PATH = "novaub.db"
# Обратная совместимость: настройки модулей раньше лежали в forelka_config.db,
# а основная база — в forelka.db.
LEGACY_DB_PATH = "forelka_config.db"
LEGACY_DB_PATH_2 = "forelka.db"

_db: Optional[aiosqlite.Connection] = None
_lock = None  # asyncio.Lock, создаётся лениково в loop


async def init(db_path: str = DB_PATH) -> None:
    """Открывает соединение и создаёт таблицы. Идемпотентна."""
    global _db, _lock
    import asyncio

    if _lock is None:
        _lock = asyncio.Lock()

    async with _lock:
        if _db is not None:
            return
        _db = await aiosqlite.connect(db_path)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA synchronous=NORMAL")
        await _db.execute("PRAGMA busy_timeout=5000")
        await _db.executescript(
            """
            CREATE TABLE IF NOT EXISTS module_configs (
                module_name TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                PRIMARY KEY (module_name, key)
            );
            CREATE TABLE IF NOT EXISTS module_state (
                module_name TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                PRIMARY KEY (module_name, key)
            );
            CREATE TABLE IF NOT EXISTS kv (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS modules (
                name     TEXT PRIMARY KEY,
                enabled  INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        await _db.commit()
    logger.debug("DB ready: %s", db_path)


async def close() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


def _conn() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("db.init() не был вызван")
    return _db


# --- helpers -------------------------------------------------------------

def _encode(value: Any) -> str:
    """Числа/bool/json-структуры кладём как json, строки — как строки."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _decode(raw: str) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


async def _migrate_legacy_module_configs() -> None:
    """Переносит module_configs из forelka_config.db в основную базу."""
    import os

    for legacy_path in (LEGACY_DB_PATH, LEGACY_DB_PATH_2):
        if not os.path.exists(legacy_path):
            continue
        try:
            async with aiosqlite.connect(legacy_path) as legacy:
                async with legacy.execute(
                    "SELECT module_name, key, value FROM module_configs"
                ) as cur:
                    rows = await cur.fetchall()
            if not rows:
                continue
            await set_many("module_configs", [(r[0], r[1], r[2]) for r in rows])
            os.replace(legacy_path, f"{legacy_path}.bak")
            logger.info("Перенесено %d записей из %s", len(rows), legacy_path)
        except Exception as e:
            logger.warning("Легаси-миграция пропущена (%s): %s", legacy_path, e)


# --- обобщённый API для таблиц (module_name, key, value) -------------------

async def get_all(table: str, module_name: str) -> dict[str, Any]:
    """Возвращает все ключи модуля из таблицы (json-декодированные)."""
    out: dict[str, Any] = {}
    async with _lock:
        db = _conn()
        async with db.execute(
            f"SELECT key, value FROM {table} WHERE module_name = ?", (module_name,)
        ) as cur:
            async for row in cur:
                out[row[0]] = _decode(row[1])
    return out


async def get_value(table: str, module_name: str, key: str, default: Any = None) -> Any:
    async with _lock:
        db = _conn()
        async with db.execute(
            f"SELECT value FROM {table} WHERE module_name = ? AND key = ?",
            (module_name, key),
        ) as cur:
            row = await cur.fetchone()
    return _decode(row[0]) if row else default


async def set_value(table: str, module_name: str, key: str, value: Any) -> None:
    async with _lock:
        db = _conn()
        await db.execute(
            f"INSERT OR REPLACE INTO {table} (module_name, key, value) VALUES (?, ?, ?)",
            (module_name, key, _encode(value)),
        )
        await db.commit()


async def set_many(table: str, rows: list[tuple[str, str, Any]]) -> None:
    """Массовая запись: rows = [(module_name, key, value), ...]."""
    if not rows:
        return
    async with _lock:
        db = _conn()
        await db.executemany(
            f"INSERT OR REPLACE INTO {table} (module_name, key, value) VALUES (?, ?, ?)",
            [(m, k, _encode(v)) for m, k, v in rows],
        )
        await db.commit()


async def delete_value(table: str, module_name: str, key: str) -> None:
    async with _lock:
        db = _conn()
        await db.execute(
            f"DELETE FROM {table} WHERE module_name = ? AND key = ?",
            (module_name, key),
        )
        await db.commit()


async def clear_module(table: str, module_name: str) -> None:
    """Стираем все записи модуля (используется при unload/reload)."""
    async with _lock:
        db = _conn()
        await db.execute(f"DELETE FROM {table} WHERE module_name = ?", (module_name,))
        await db.commit()


# --- module_configs: настройки -------------------------------------------

async def get_module_config(module_name: str) -> dict[str, Any]:
    return await get_all("module_configs", module_name)


async def set_module_config_value(module_name: str, key: str, value: Any) -> None:
    await set_value("module_configs", module_name, key, value)


async def del_module_config_value(module_name: str, key: str) -> None:
    await delete_value("module_configs", module_name, key)


# --- module_state: персист состояния (#7) --------------------------------

async def get_module_state(module_name: str) -> dict[str, Any]:
    return await get_all("module_state", module_name)


async def set_module_state(module_name: str, key: str, value: Any) -> None:
    await set_value("module_state", module_name, key, value)


async def del_module_state(module_name: str, key: str) -> None:
    await delete_value("module_state", module_name, key)


# --- kv: произвольные пары -----------------------------------------------

async def kv_get(key: str, default: Any = None) -> Any:
    async with _lock:
        db = _conn()
        async with db.execute("SELECT value FROM kv WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
    return _decode(row[0]) if row else default


async def kv_set(key: str, value: Any) -> None:
    async with _lock:
        db = _conn()
        await db.execute(
            "INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, _encode(value))
        )
        await db.commit()


async def kv_delete(key: str) -> None:
    async with _lock:
        db = _conn()
        await db.execute("DELETE FROM kv WHERE key = ?", (key,))
        await db.commit()


# --- modules: реестр включённых модулей (#7) ------------------------------

async def set_module_enabled(name: str, enabled: bool) -> None:
    async with _lock:
        db = _conn()
        await db.execute(
            "INSERT OR REPLACE INTO modules (name, enabled) VALUES (?, ?)",
            (name, 1 if enabled else 0),
        )
        await db.commit()


async def is_module_enabled(name: str) -> Optional[bool]:
    """None — модуль не зарегистрирован (идём по умолчанию)."""
    async with _lock:
        db = _conn()
        async with db.execute(
            "SELECT enabled FROM modules WHERE name = ?", (name,)
        ) as cur:
            row = await cur.fetchone()
    if row is None:
        return None
    return bool(row[0])


async def list_enabled_modules() -> list[str]:
    async with _lock:
        db = _conn()
        async with db.execute("SELECT name FROM modules WHERE enabled = 1") as cur:
            rows = await cur.fetchall()
    return [r[0] for r in rows]


async def list_disabled_modules() -> list[str]:
    async with _lock:
        db = _conn()
        async with db.execute("SELECT name FROM modules WHERE enabled = 0") as cur:
            rows = await cur.fetchall()
    return [r[0] for r in rows]


# --- запуск ---------------------------------------------------------------

async def ensure_started() -> None:
    """Инициализация + легаси-миграция. Безопасно вызывать много раз."""
    if _db is None:
        await init()
    await _migrate_legacy_module_configs()


# ---------------------------------------------------------------------------
# Совместимость со старым синхронным database.py
# ---------------------------------------------------------------------------

class Database:
    """Старый интерфейс (sync), теперь поверх асинхронной базы.

    Оставлен только чтобы не сломать возможные внешние импорты.
    Все реальные вызовы в NovaUB идут через асинхронные функции выше.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def set(self, key, value):
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(kv_set(key, value))

    def get(self, key, default=None):
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(kv_get(key, default))

    def close(self):
        pass
