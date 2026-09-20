import asyncio
from pyrogram.enums import ParseMode

async def neofetch_cmd(client, message, args):
    pref = getattr(client, "prefix", ".")

    proc = await asyncio.create_subprocess_shell(
        "neofetch --stdout",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    out = (stdout or b"").decode(errors="ignore").strip()
    err = (stderr or b"").decode(errors="ignore").strip()

    if proc.returncode == 0 and out:
        text = f"<blockquote expandable><code>{out}</code></blockquote>"
        if len(text) > 4000:
            text = text[:3990] + "…</code></blockquote>"
        return await message.edit(text, parse_mode=ParseMode.HTML)

    if "command not found" in err.lower() or "not found" in err.lower():
        await message.edit(
            "<b>neofetch не установлен</b>\n"
            "<code>Пробую установить neofetch...</code>",
            parse_mode=ParseMode.HTML
        )

        install_cmds = [
            "apt-get update -y && apt-get install -y neofetch",
            "pkg install -y neofetch"
        ]

        installed = False
        for cmd in install_cmds:
            proc_i = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc_i.communicate()
            if proc_i.returncode == 0:
                installed = True
                break

        if installed:
            return await message.edit(
                "<b>neofetch установлен.</b>\n"
                f"<code>Повтори команду {pref}neofetch</code>",
                parse_mode=ParseMode.HTML
            )
        else:
            return await message.edit(
                "<b>Не удалось установить neofetch автоматически.</b>\n"
                "Установи его вручную и попробуй ещё раз.",
                parse_mode=ParseMode.HTML
            )

    text = (
        "<b>Ошибка при выполнении neofetch.</b>\n\n"
        f"<b>stderr:</b>\n<blockquote expandable><code>{err or 'нет вывода'}</code></blockquote>"
    )
    await message.edit(text, parse_mode=ParseMode.HTML)

def register(app, commands, module_name):
    commands["neofetch"] = {"func": neofetch_cmd, "module": module_name}