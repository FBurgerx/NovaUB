import os
import sys
import asyncio
from telethon import events, Button

async def restart_cmd(client, message, args):
    """Команда .restart через инлайн-запрос."""
    kernel = client.kernel
    
    if not hasattr(kernel, 'inline_bot') or not kernel.inline_bot:
        await message.edit("❌ Инлайн-бот не настроен.")
        return

    try:
        await asyncio.sleep(0.1)  # Небольшая задержка
        await kernel.inline_query_and_click(
            chat_id=message.chat_id,
            query="restart"
        )
        await message.delete()
    except Exception as e:
        await message.edit(f"❌ Ошибка: {e}")

# === Обработчик инлайн-запроса для рестарта ===
async def restart_inline_handler(event: events.InlineQuery.Event):
    """Обработчик инлайн-запроса для рестарта."""
    kernel = event.client.kernel
    user_id = event.sender_id
    query = event.text.strip()
    
    if query != "restart":
        return

    if not is_owner(kernel, user_id):
        builder = event.builder
        no_access = builder.article(
            title="🔒 Доступ запрещен",
            text="<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> <b>Доступ запрещен.</b></blockquote>",
            parse_mode='html'
        )
        await event.answer([no_access])
        return

    builder = event.builder
    result = builder.article(
        title="🔄 Перезагрузка юзербота",
        text="<blockquote><b>🔄 Подтверждение перезагрузки</b>\nВы уверены, что хотите перезагрузить юзербота?</blockquote>",
        parse_mode='html',
        buttons=[
            [
                Button.inline("✅ Подтвердить", data="restart_confirm"),
                Button.inline("❌ Отмена", data="restart_cancel")
            ]
        ]
    )
    await event.answer([result])

# === Обработчик кнопок рестарта ===
async def restart_callback_handler(event: events.CallbackQuery.Event):
    """Обработчик кнопок подтверждения рестарта."""
    kernel = event.client.kernel
    user_id = event.sender_id
    
    if not is_owner(kernel, user_id):
        await event.answer("Доступ запрещен!", alert=True)
        return

    data = event.data.decode('utf-8')
    
    if data == "restart_confirm":
        await event.edit(
            "<blockquote><tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Перезагрузка...</b>\nЮзербот будет перезапущен.</blockquote>",
            parse_mode='html'
        )
        # Выполняем перезагрузку
        await perform_restart(kernel)
        
    elif data == "restart_cancel":
        await event.delete()

async def perform_restart(kernel):
    """Выполняет перезагрузку юзербота."""
    # Останавливаем клиента
    if kernel.client and kernel.client.is_connected():
        await kernel.client.disconnect()
    
    # Перезапускаем процесс
    os.execl(sys.executable, sys.executable, *sys.argv)

def is_owner(kernel, user_id):
    """Проверяет, является ли пользователь владельцем."""
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

# === Регистрация ===
def register(app, commands, module_name, kernel=None):
    commands["restart"] = {"func": restart_cmd, "module": module_name}
    
    if kernel is not None:
        kernel.register_inline_handler(restart_inline_handler)
        kernel.register_callback_handler(restart_callback_handler)