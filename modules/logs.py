import os
from telethon import events

async def log_cmd(client, message, args):
    user_id = message.sender_id
    config_path = f"config-{client._self_id}.json"
    
    # Проверка владельца
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                owners = config.get("owners", [])
                if client._self_id not in owners:
                    owners.append(client._self_id)
                if user_id not in owners:
                    await message.edit("❌ Доступ запрещен.")
                    return
        except:
            if user_id != client._self_id:
                await message.edit("❌ Доступ запрещен.")
                return
    else:
        if user_id != client._self_id:
            await message.edit("❌ Доступ запрещен.")
            return

    if not os.path.exists("novaub.log"):
        await message.edit("❌ Файл лога не найден.")
        return

    # --- КЛЮЧЕВАЯ ПРОВЕРКА: БОТ ДОЛЖЕН БЫТЬ ПОДКЛЮЧЕН ---
    if (hasattr(client, 'kernel') and 
        client.kernel.inline_bot and 
        client.kernel.inline_bot.bot_client and
        client.kernel.inline_bot.bot_client.is_connected()): # <-- ЭТО ВАЖНО
        
        bot_client = client.kernel.inline_bot.bot_client
        config_path = f"config-{client._self_id}.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                group_id = config.get("management_group_id")
                topics = config.get("management_topics", {})
                logs_topic_id = topics.get("Логи")
                
                if group_id and logs_topic_id:
                    await bot_client.send_file(
                        entity=group_id,
                        file="novaub.log",
                        message_thread_id=logs_topic_id
                    )
                    await message.edit("✅ Логи отправлены инлайн-ботом в топик 'Логи'.")
                    return
            except Exception as e:
                pass
    
    # Если бот не готов, отправляем от юзербота
    await client.send_file(message.chat_id, "novaub.log", caption="📋 Логи юзербота")
    await message.delete()

def register(app, commands, module_name):
    commands["log"] = {"func": log_cmd, "module": module_name}