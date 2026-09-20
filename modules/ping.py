import time
import os
import json
from telethon import events
from telethon.tl.custom import Message

def is_owner(kernel, user_id):
    """,    ."""
    config_path = f"config-{kernel.client._self_id}.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                owners = config.get("owners", [])
                if kernel.client._self_id not in owners:
                    owners.append(kernel.client._self_id)
                return user_id in owners
        except:
            pass
    return user_id == kernel.client._self_id

async def ping_cmd(client, message, args):
    start = time.perf_counter()
    await message.edit("<blockquote><tg-emoji emoji-id=5891211339170326418>⌛️</emoji> <b>Pinging...</b></blockquote>", parse_mode='html')
    
    ms = (time.perf_counter() - start) * 1000
    res = (
        f"<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Pong</b>\n"
        f"<blockquote><tg-emoji emoji-id=5776375003280838798>✅</emoji> <b>Latency:</b> <code>{ms:.2f} ms</code></blockquote>"
    )
    await message.edit(res, parse_mode='html')

# ===   - (@bot ping) ===
async def inline_ping_handler(event: events.InlineQuery.Event):
    kernel = event.client.kernel
    user_id = event.sender_id

    #    
    if not is_owner(kernel, user_id):
        builder = event.builder
        no_access_result = builder.article(
            title="🔒 Доступ запрещен",
            description="Эта функция доступна только владельцам.",
            text="<blockquote><tg-emoji emoji-id=5778527486270770928>⛔</emoji> <b>Доступ запрещен.</b>\nЭта функция доступна только владельцам юзербота.</blockquote>",
            parse_mode='html'
        )
        await event.answer([no_access_result], switch_pm="Доступ запрещен", switch_pm_param="forbidden")
        return

    query = event.text.strip()
    if query == "ping":
        start = time.perf_counter()
        # Эмулируем задержку
        ms = (time.perf_counter() - start) * 1000
        
        builder = event.builder
        ping_result = builder.article(
            title=f"Pong! {ms:.2f}ms",
            description="Проверка активности бота",
            text=(
                f"<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Pong</b>\n"
                f"<blockquote><tg-emoji emoji-id=5776375003280838798>✅</emoji> <b>Latency:</b> <code>{ms:.2f} ms</code></blockquote>"
            ),
            parse_mode='html'
        )
        await event.answer([ping_result])

# === Обработчик команды /ping в самом боте ===
async def bot_ping_handler(event: events.NewMessage.Event):
    kernel = event.client.kernel
    user_id = event.sender_id

    # Проверка владельца
    if not is_owner(kernel, user_id):
        await event.reply(
            "<blockquote><tg-emoji emoji-id=5778527486270770928>⛔</emoji> <b>Доступ запрещен.</b>\nЭта команда доступна только владельцам юзербота.</blockquote>",
            parse_mode='html'
        )
        return

    start = time.perf_counter()
    pong_msg = await event.reply("<blockquote><tg-emoji emoji-id=5891211339170326418>⌛️</emoji> <b>Pinging...</b></blockquote>", parse_mode='html')
    ms = (time.perf_counter() - start) * 1000
    res = (
        f"<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Pong</b>\n"
        f"<blockquote><tg-emoji emoji-id=5776375003280838798>✅</emoji> <b>Latency:</b> <code>{ms:.2f} ms</code></blockquote>"
    )
    await pong_msg.edit(res, parse_mode='html')

def register(app, commands, module_name, kernel=None):
    # Регистрация для юзербота
    commands["ping"] = {"func": ping_cmd, "module": module_name}
    
    # Регистрация для инлайн-бота
    if kernel is not None and hasattr(kernel, 'register_bot_command') and hasattr(kernel, 'register_inline_handler'):
        if hasattr(kernel, 'inline_bot') and kernel.inline_bot and kernel.inline_bot.bot_client:
            kernel.inline_bot.bot_client.kernel = kernel
        
        kernel.register_bot_command("ping", bot_ping_handler)
        kernel.register_inline_handler(inline_ping_handler)
        print(f"[Ping] Инлайн-команды зарегистрированы.")