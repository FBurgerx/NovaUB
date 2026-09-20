import html
import time

__meta__ = {
    "name": "AutoReply",
    "author": "NovaUB",
    "description": "Автоответчик в ЛС, когда вы заняты.",
    "commands": ["autoreply"]
}

_last_reply = {}

async def autoreply_cmd(client, message, args):
    kernel = client.kernel
    config = await kernel.get_module_config(__name__)
    enabled = config.get("enabled", False)
    text = config.get("reply_text", "Сейчас не в сети. Отвечу позже.")
    cooldown = config.get("cooldown", 60)

    status = "включён" if enabled else "выключен"
    await message.edit(
        f"<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>AutoReply</b>\n\n"
        f"<blockquote>"
        f"<b>Статус:</b> <code>{status}</code>\n"
        f"<b>Текст:</b> <code>{html.escape(str(text))}</code>\n"
        f"<b>Кулдаун:</b> <code>{cooldown}с</code>"
        f"</blockquote>\n\n"
        f"<i>Настройка через .config → Модули → autoreply</i>",
        parse_mode='html'
    )

async def _on_pm(event):
    client = event.client
    message = event.message

    if message.out or not message.is_private or not message.sender_id:
        return

    kernel = getattr(client, 'kernel', None)
    if not kernel:
        return

    config = await kernel.get_module_config("autoreply")
    if not config.get("enabled", False):
        return

    cooldown = config.get("cooldown", 60)
    now = time.time()
    uid = message.sender_id

    if uid in _last_reply and (now - _last_reply[uid]) < cooldown:
        return

    text = config.get("reply_text", "Сейчас не в сети. Отвечу позже.")
    await event.reply(text)
    _last_reply[uid] = now

def get_config(kernel, module_name):
    return {
        "enabled": {
            "type": "bool",
            "name": "Включён",
            "default": False,
            "description": "Включить автоответчик в ЛС."
        },
        "reply_text": {
            "type": "str",
            "name": "Текст ответа",
            "default": "Сейчас не в сети. Отвечу позже.",
            "description": "Сообщение, которое отправляется в ЛС."
        },
        "cooldown": {
            "type": "list",
            "name": "Кулдаун (сек)",
            "default": "60",
            "options": ["30", "60", "120", "300"],
            "description": "Минимальный интервал между ответами одному пользователю."
        }
    }

def register(app, commands, module_name, kernel=None):
    commands["autoreply"] = {
        "func": autoreply_cmd,
        "module": module_name,
        "description": "Статус автоответчика"
    }
    from telethon import events
    app.add_event_handler(_on_pm, events.NewMessage(incoming=True))
