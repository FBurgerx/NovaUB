import os
import json
import time
from datetime import datetime
from telethon import events, Button

def get_main_owner(kernel):
    config_path = f"config-{kernel.client._self_id}.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                owners = config.get("owners", [])
                if owners:
                    return owners[0]
        except:
            pass
    return kernel.client._self_id

async def bot_feedback_handler(event: events.NewMessage.Event):
    kernel = event.client.kernel
    user_id = event.sender_id
    kernel.feedback_users.add(user_id)
    await event.reply(
        "<blockquote>Режим обратной связи активирован!\n\n"
        "Отправьте сюда любое сообщение, включая медиа, "
        "и я обязательно передам его хозяину.</blockquote>",
        parse_mode='html'
    )

async def bot_start_handler(event: events.NewMessage.Event):
    kernel = event.client.kernel
    user_id = event.sender_id
    if user_id in kernel.feedback_users:
        kernel.feedback_users.remove(user_id)
        await event.reply(
            "<blockquote>Режим обратной связи деактивирован.</blockquote>",
            parse_mode='html'
        )

# Обработчик для сообщений в режиме фидбека
async def feedback_message_handler(event: events.NewMessage.Event):
    kernel = event.client.kernel
    user_id = event.sender_id
    
    main_owner_id = get_main_owner(kernel)
    timestamp = datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')
    
    original_text = event.raw_text or ""
    if not original_text and not event.message.media:
        original_text = "[Пустое сообщение]"
    
    owner_message = (
        f"<blockquote>\n"
        f"<b>Сообщение:</b>\n{original_text}\n\n"
        f"<b>ID:</b> <code>{user_id}</code>\n"
        f"<b>Time:</b> <code>{timestamp}</code>\n"
        f"</blockquote>"
    )

    try:
        bot_client = event.client
        if event.message.media:
            sent_msg = await bot_client.send_file(
                main_owner_id,
                file=event.message.media,
                caption=owner_message,
                parse_mode='html'
            )
        else:
            sent_msg = await bot_client.send_message(
                main_owner_id,
                owner_message,
                parse_mode='html'
            )
        
        buttons = [
            [
                Button.inline("📨 Ответить", data=f"fb_reply_{user_id}"),
                Button.inline("🗑 Удалить", data=f"fb_delete_{sent_msg.id}")
            ]
        ]
        await sent_msg.edit(buttons=buttons)
        await event.reply("✅ Ваше сообщение отправлено хозяину!")

    except Exception as e:
        await event.reply(f"❌ Ошибка отправки: {e}")

# Обработчик ответа владельца
async def owner_reply_handler(event: events.NewMessage.Event):
    bot_client = event.client
    if not hasattr(bot_client, 'feedback_reply_to'):
        return
        
    target_user_id = bot_client.feedback_reply_to
    delattr(bot_client, 'feedback_reply_to')
    
    try:
        if event.message.media:
            await bot_client.send_file(
                target_user_id,
                file=event.message.media,
                caption="<blockquote><b>Ответ от хозяина:</b></blockquote>",
                parse_mode='html'
            )
        else:
            await bot_client.send_message(
                target_user_id,
                f"<blockquote><b>Ответ от хозяина:</b>\n{event.raw_text}</blockquote>",
                parse_mode='html'
            )
        await event.reply("✅ Ответ отправлен!")
    except Exception as e:
        await event.reply(f"❌ Ошибка отправки: {e}")

def register(app, commands, module_name, kernel=None):
    if kernel is None:
        return
        
    kernel.register_bot_command("feedback", bot_feedback_handler)
    kernel.register_bot_command("start", bot_start_handler)
    
    # Регистрируем ТОЛЬКО обработчик ответа
    if hasattr(kernel, 'inline_bot') and kernel.inline_bot and kernel.inline_bot.bot_client:
        bot_client = kernel.inline_bot.bot_client
        bot_client.kernel = kernel
        bot_client.add_event_handler(owner_reply_handler, events.NewMessage(incoming=True))
        
        print(f"[Feedback] Система обратной связи зарегистрирована.")