import json
import os
from telethon.tl.custom import Message

async def addowner_cmd(client, message, args):
    """Добавить овнера"""
    
    # Проверяем аргументы
    if not args and not await message.get_reply_message():
        return await message.edit(
            "<blockquote><tg-emoji emoji-id=5775887550262546277>❗️</emoji> <b>Usage:</b>\n\n"
            "<code>.addowner [user_id]</code> - добавить по ID\n"
            "<code>.addowner</code> (ответ на сообщение) - добавить пользователя</blockquote>",
            parse_mode='html'
        )
    
    # Получаем ID пользователя
    reply_msg = await message.get_reply_message()
    if reply_msg:
        user_id = reply_msg.sender_id
        user_name = (await reply_msg.get_sender()).first_name if reply_msg.sender else f"User {user_id}"
    else:
        try:
            user_id = int(args[0])
            user_name = f"User {user_id}"
        except:
            return await message.edit(
                "<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> <b>Неверный ID</b></blockquote>",
                parse_mode='html'
            )
    
    # Загружаем конфиг
    config_path = f"config-{client._self_id}.json"
    config = {"prefix": "."}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except:
            pass
    
    # Добавляем овнера
    owners = config.get("owners", [])
    if user_id in owners:
        return await message.edit(
            f"<blockquote><tg-emoji emoji-id=5775887550262546277>❗️</emoji> <b>{user_name}</b> уже является овнером</blockquote>",
            parse_mode='html'
        )
    
    owners.append(user_id)
    config["owners"] = owners
    
    # Сохраняем
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)
    
    await message.edit(
        f"<blockquote><tg-emoji emoji-id=5776375003280838798>✅</emoji> <b>Овнер добавлен!</b>\n\n"
        f"<b>User:</b> <code>{user_name}</code>\n"
        f"<b>ID:</b> <code>{user_id}</code>\n\n"
        f"<b>Всего овнеров:</b> <code>{len(owners)}</code></blockquote>",
        parse_mode='html'
    )

async def delowner_cmd(client, message, args):
    """Удалить овнера"""
    
    # Проверяем аргументы
    if not args and not await message.get_reply_message():
        return await message.edit(
            "<blockquote><tg-emoji emoji-id=5775887550262546277>❗️</emoji> <b>Usage:</b>\n\n"
            "<code>.delowner [user_id]</code> - удалить по ID\n"
            "<code>.delowner</code> (ответ на сообщение) - удалить пользователя</blockquote>",
            parse_mode='html'
        )
    
    # Получаем ID пользователя
    reply_msg = await message.get_reply_message()
    if reply_msg:
        user_id = reply_msg.sender_id
    else:
        try:
            user_id = int(args[0])
        except:
            return await message.edit(
                "<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> <b>Неверный ID</b></blockquote>",
                parse_mode='html'
            )
    
    # Нельзя удалить себя
    if user_id == client._self_id:
        return await message.edit(
            "<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> <b>Нельзя удалить владельца бота</b></blockquote>",
            parse_mode='html'
        )
    
    # Загружаем конфиг
    config_path = f"config-{client._self_id}.json"
    config = {"prefix": "."}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except:
            pass
    
    # Удаляем овнера
    owners = config.get("owners", [])
    if user_id not in owners:
        return await message.edit(
            "<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> <b>Пользователь не является овнером</b></blockquote>",
            parse_mode='html'
        )
    
    owners.remove(user_id)
    config["owners"] = owners
    
    # Сохраняем
    with open(config_path, "w") as f:
        json.dump(config, f, indent=4)
    
    await message.edit(
        f"<blockquote><tg-emoji emoji-id=5776375003280838798>✅</emoji> <b>Овнер удален!</b>\n\n"
        f"<b>ID:</b> <code>{user_id}</code>\n\n"
        f"<b>Осталось овнеров:</b> <code>{len(owners)}</code></blockquote>",
        parse_mode='html'
    )

async def owners_cmd(client, message, args):
    """Список овнеров"""
    
    # Загружаем конфиг
    config_path = f"config-{client._self_id}.json"
    config = {"prefix": "."}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except:
            pass
    
    owners = config.get("owners", [])
    
    # Добавляем владельца бота если его нет
    if client._self_id not in owners:
        owners.insert(0, client._self_id)
    
    if not owners:
        return await message.edit(
            "<blockquote><tg-emoji emoji-id=5775887550262546277>❗️</emoji> <b>Нет добавленных овнеров</b></blockquote>",
            parse_mode='html'
        )
    
    text = "<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Список овнеров</b>\n\n"
    
    for i, owner_id in enumerate(owners, 1):
        if owner_id == client._self_id:
            text += f"<blockquote><tg-emoji emoji-id=5776375003280838798>✅</emoji> <code>{owner_id}</code> (Владелец бота)</blockquote>\n"
        else:
            text += f"<blockquote><tg-emoji emoji-id=5877468380125990242>➡️</emoji> <code>{owner_id}</code></blockquote>\n"
    
    text += f"\n<b>Всего:</b> <code>{len(owners)}</code> овнеров"
    
    await message.edit(text, parse_mode='html')

def register(app, commands, module_name):
    """Регистрация команд"""
    commands["addowner"] = {"func": addowner_cmd, "module": module_name}
    commands["delowner"] = {"func": delowner_cmd, "module": module_name}
    commands["owners"] = {"func": owners_cmd, "module": module_name}