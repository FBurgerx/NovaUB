import html
import time


def _escape(value):
    return html.escape(str(value)) if value is not None else ""


async def accounts_cmd(client, message, args):
    me = await client.get_me()
    name = f"{me.first_name or ''} {me.last_name or ''}".strip()
    uptime_sec = int(time.time() - getattr(client, 'start_time', time.time()))
    hours, rem = divmod(uptime_sec, 3600)
    mins, secs = divmod(rem, 60)
    uptime_str = f"{hours}h {mins}m {secs}s"
    modules_count = len(getattr(client, 'loaded_modules', set()))

    text = (
        "<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Аккаунт</b>\n\n"
        f"<blockquote><b>Имя:</b> {_escape(name)}\n"
        f"<b>ID:</b> <code>{me.id}</code>\n"
        f"<b>Username:</b> @{_escape(me.username) if me.username else '—'}\n"
        f"<b>Uptime:</b> <code>{uptime_str}</code>\n"
        f"<b>Модули:</b> <code>{modules_count}</code></blockquote>"
    )
    await message.edit(text, parse_mode='html')


def register(app, commands, module_name):
    commands["account"] = {"func": accounts_cmd, "module": module_name, "description": "Информация об аккаунте"}
