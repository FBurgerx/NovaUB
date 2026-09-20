"""
Модуль для автоматического фарма в FunStat.
Пересылает ссылки из поискового бота в целевой.
"""

import asyncio
import contextlib
from datetime import datetime

__meta__ = {
    "name":        "FunStatFarm",
    "version":     "1.2.0",
    "author":      "Needlemouse",
    "description": "Автоматический фарм /rand для FunStat",
    "commands":    ["farmfs", "stopfs", "fsstatus"],
}

# Глобальные переменные для работы с ядром
_kernel = None
_is_farming_active = False
_farm_task = None
_session_started_at = None
_reply_chat_id = None

# Вспомогательные функции для статистики через БД NovaUB
async def get_stat(key, default=0):
    cfg = await _kernel.get_module_config("funstatfarm")
    return cfg.get(key, default)

async def set_stat(key, value):
    cfg = await _kernel.get_module_config("funstatfarm")
    cfg[key] = value
    await _kernel.set_module_config("funstatfarm", cfg)

async def inc_stat(key, step=1):
    val = await get_stat(key, 0)
    await set_stat(key, val + step)

def format_duration(seconds):
    seconds = int(max(seconds, 0))
    hours, rem = divmod(seconds, 3600)
    minutes, sec = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}"

# --- Логика фарма ---

async def farm_loop(client):
    global _is_farming_active, _farm_task
    
    # Получаем настройки из конфига kernel
    search_bot = _kernel.config.get("fs_search_bot", "@en_SearchBot")
    delay = _kernel.config.get("fs_delay", 10)

    try:
        while _is_farming_active:
            await client.send_message(search_bot, "/rand")
            await inc_stat("rand_sent")
            await set_stat("last_rand_at", int(datetime.now().timestamp()))
            await asyncio.sleep(delay)
    except Exception as e:
        _is_farming_active = False
        await set_stat("last_error", str(e))
        if _reply_chat_id:
            await client.send_message(_reply_chat_id, f"❌ **Фарм остановлен из-за ошибки:** `{e}`")

# --- Команды ---

async def farmfs_cmd(client, message, args):
    """Запустить фарм FunStat."""
    global _is_farming_active, _farm_task, _session_started_at, _reply_chat_id
    
    if _is_farming_active:
        await message.edit("ℹ️ Фарм уже запущен.")
        return

    _is_farming_active = True
    _reply_chat_id = message.chat_id
    _session_started_at = datetime.now().timestamp()
    
    # Запускаем цикл в фоне
    _farm_task = asyncio.create_task(farm_loop(client))
    
    search_bot = _kernel.config.get("fs_search_bot", "@en_SearchBot")
    await message.edit(f"✅ **Фарм запущен.**\nБот: `{search_bot}`")

async def stopfs_cmd(client, message, args):
    """Остановить фарм FunStat."""
    global _is_farming_active, _farm_task
    
    if not _is_farming_active:
        await message.edit("ℹ️ Фарм не активен.")
        return

    _is_farming_active = False
    if _farm_task:
        _farm_task.cancel()
    
    await message.edit("✅ **Фарм остановлен.**")

async def fsstatus_cmd(client, message, args):
    """Показать статистику фарма."""
    status = "🟢 Активен" if _is_farming_active else "🔴 Остановлен"
    
    started = _session_started_at or 0
    uptime = format_duration(datetime.now().timestamp() - started) if _is_farming_active else "00:00:00"
    
    sent = await get_stat("rand_sent", 0)
    fwd = await get_stat("forwarded", 0)
    err = await get_stat("last_error", "Нет")

    text = (
        f"<b>📊 FunStat Farm Status</b>\n"
        f"<b>Состояние:</b> {status}\n"
        f"<b>Аптайм:</b> <code>{uptime}</code>\n"
        f"<b>Отправлено /rand:</b> <code>{sent}</code>\n"
        f"<b>Переслано:</b> <code>{fwd}</code>\n"
        f"<b>Последняя ошибка:</b> <code>{err}</code>"
    )
    await message.edit(text, parse_mode="html")

# --- Обработчик входящих (Watcher аналог) ---

async def watcher_handler(event):
    """Следит за ответами поискового бота и пересылает их."""
    global _is_farming_active
    if not _is_farming_active:
        return

    search_bot = _kernel.config.get("fs_search_bot", "@en_SearchBot")
    target_bot = _kernel.config.get("fs_target_bot", "@JDHXYU_bot")

    # Проверяем, что сообщение от нужного бота
    sender = await event.get_sender()
    if hasattr(sender, 'username') and f"@{sender.username}".lower() == search_bot.lower():
        if event.text and not event.text.startswith('/'):
            await _kernel.client.send_message(target_bot, event.text)
            await inc_stat("forwarded")

# --- Регистрация ---

def register(app, commands, module_name, kernel=None):
    global _kernel
    _kernel = kernel
    
    # Регистрация команд
    commands["farmfs"] = {
        "func": farmfs_cmd,
        "module": module_name,
        "description": "Запустить фарм",
    }
    commands["stopfs"] = {
        "func": stopfs_cmd,
        "module": module_name,
        "description": "Остановить фарм",
    }
    commands["fsstatus"] = {
        "func": fsstatus_cmd,
        "module": module_name,
        "description": "Статус фарма",
    }

    # Добавляем обработчик событий Telethon напрямую через клиент ядра
    if _kernel and _kernel.client:
        from telethon import events
        _kernel.client.add_event_handler(watcher_handler, events.NewMessage(incoming=True))
