import os
import json
import asyncio
from telethon import events, Button

import database as db

# === ЕДИНСТВЕННЫЙ ОБРАБОТЧИК ИНЛАЙН-ЗАПРОСОВ ===
async def config_cmd(client, message, args):
    kernel = client.kernel
    if not hasattr(kernel, 'inline_bot') or not kernel.inline_bot:
        await message.edit("❌ Инлайн-бот не настроен.")
        return

    try:
        await asyncio.sleep(1)
        await kernel.inline_query_and_click(
            chat_id=message.chat_id,
            query="config"
        )
        await message.delete()
    except Exception as e:
        await message.edit(f"❌ Ошибка: {e}")

# === ЕДИНСТВЕННЫЙ ОБРАБОТЧИК ИНЛАЙН-ЗАПРОСОВ ===
async def config_inline_handler(event: events.InlineQuery.Event):
    kernel = event.client.kernel
    user_id = event.sender_id
    query = event.text.strip()
    
    # Главное меню
    if query == "config":
        if not is_owner(kernel, user_id):
            builder = event.builder
            no_access = builder.article(
                title="🔒 Доступ запрещен",
                text="<blockquote>Доступ запрещен.</blockquote>",
                parse_mode='html'
            )
            await event.answer([no_access])
            return

        builder = event.builder
        result = builder.article(
            title="⚙️ Панель конфигурации",
            text="<blockquote><b>⚙️ Выбери раздел для настройки</b></blockquote>",
            parse_mode='html',
            buttons=[
                [
                    Button.inline("🧩 Модули", data="config_modules"),
                    Button.inline("🌐 Общие", data="config_common")
                ],
                [
                    Button.inline("❌ Закрыть", data="config_close")
                ]
            ]
        )
        await event.answer([result])
        return
        
    # Обработка сохранения значения
    if query.startswith("cfg_save_") and " " in query:
        if not is_owner(kernel, user_id):
            return
            
        prefix, new_value_str = query.split(" ", 1)
        parts = prefix.split("_", 3)
        if len(parts) < 4:
            return
            
        module_name, key = parts[2], parts[3]
        if module_name not in kernel.module_configs:
            return
            
        # Парсим значение
        new_value = new_value_str
        if new_value_str.lower() == "true":
            new_value = True
        elif new_value_str.lower() == "false":
            new_value = False
        elif new_value_str.isdigit():
            new_value = int(new_value_str)
        elif new_value_str.replace(".", "", 1).isdigit():
            new_value = float(new_value_str)
            
        # Сохраняем
        await db.set_module_config_value(module_name, key, new_value)
        
        builder = event.builder
        result = builder.article(
            title="✅ Сохранено!",
            text=f"<blockquote>Параметр <b>{key}</b> модуля <b>{module_name}</b> обновлен!</blockquote>",
            parse_mode='html'
        )
        await event.answer([result])
        return

# === ОБРАБОТЧИК КНОПОК (ТОЛЬКО НАВИГАЦИЯ И ПЕРЕКЛЮЧЕНИЕ BOOL) ===
async def config_callback_handler(event: events.CallbackQuery.Event):
    kernel = event.client.kernel
    user_id = event.sender_id
    
    if not is_owner(kernel, user_id):
        await event.answer("Доступ запрещен!", alert=True)
        return

    data = event.data.decode('utf-8')
    
    if data == "config_close":
        await event.delete()
        return
        
    elif data == "config_main":
        await event.edit(
            "<blockquote><b>⚙️ Выбери раздел для настройки</b></blockquote>",
            parse_mode='html',
            buttons=[
                [
                    Button.inline("🧩 Модули", data="config_modules"),
                    Button.inline("🌐 Общие", data="config_common")
                ],
                [
                    Button.inline("❌ Закрыть", data="config_close")
                ]
            ]
        )
        return
        
    elif data == "config_modules":
        module_buttons = []
        for module_name in sorted(kernel.module_configs.keys()):
            module_buttons.append([Button.inline(f"🔧 {module_name}", data=f"config_module_{module_name}")])
        
        if not module_buttons:
            module_buttons = [[Button.inline("Нет модулей с конфигурацией", data="config_main")]]
            
        module_buttons.append([Button.inline("⬅️ Назад", data="config_main")])
        
        await event.edit(
            "<blockquote><b>⚙️ Выбери модуль для настройки</b></blockquote>",
            parse_mode='html',
            buttons=module_buttons
        )
        return
        
    elif data.startswith("config_module_"):
        module_name = data[len("config_module_"):]
        if module_name not in kernel.module_configs:
            await event.answer("Модуль не найден!", alert=True)
            return
            
        config_func = kernel.module_configs[module_name]
        default_config = config_func(kernel, module_name)
        current_config = await db.get_module_config(module_name)
        
        full_config = {}
        for key, setting in default_config.items():
            full_config[key] = {
                "name": setting["name"],
                "type": setting["type"],
                "value": current_config.get(key, setting.get("default", None)),
                "default": setting.get("default", "N/A"),
                "description": setting.get("description", "Описание отсутствует.")
            }
        
        current_settings = "\n".join([
            f"▫️ {key}: {full_config[key]['value']}" for key in full_config
        ])
        text = f"<blockquote><b>⚙️ Выбери параметр для модуля {module_name}</b>\n\nТекущие настройки:\n{current_settings}</blockquote>"
        
        config_buttons = build_config_buttons(full_config, module_name)
        config_buttons.append([Button.inline("⬅️ Назад", data="config_modules")])
        
        await event.edit(text, parse_mode='html', buttons=config_buttons)
        return
        
    elif data.startswith("cfg_toggle_"):
        parts = data.split("_", 3)
        module_name, key = parts[2], parts[3]
        if module_name not in kernel.module_configs:
            await event.answer("Модуль не найден!", alert=True)
            return
            
        config_func = kernel.module_configs[module_name]
        default_config = config_func(kernel, module_name)
        setting = default_config.get(key)
        if not setting or setting["type"] != "bool":
            await event.answer("Неверная настройка!", alert=True)
            return
            
        description = setting.get("description", "Описание отсутствует.")
        current_config = await db.get_module_config(module_name)
        current_value = current_config.get(key, setting.get("default", False))
        new_value = not current_value
        
        await db.set_module_config_value(module_name, key, new_value)
        
        text = f"<blockquote><b>⚙️ Управление параметром {key} модуля {module_name}</b>\nℹ️ {description}\n\nСтандартное: <code>{setting.get('default', 'N/A')}</code>\nТекущее: <code>{new_value}</code>\n\n🕵️ Должно быть логическим значением</blockquote>"
        
        await event.edit(
            text,
            parse_mode='html',
            buttons=[
                [
                    Button.inline("✅ Set True", data=f"cfg_save_{module_name}_{key}_true"),
                    Button.inline("❌ Set False", data=f"cfg_save_{module_name}_{key}_false")
                ],
                [Button.inline("⬅️ Назад", data=f"config_module_{module_name}")],
                [Button.inline("❌ Закрыть", data="config_close")]
            ]
        )
        return
        
    elif data.startswith("cfg_edit_"):
        parts = data.split("_", 3)
        module_name, key = parts[2], parts[3]
        if module_name not in kernel.module_configs:
            await event.answer("Модуль не найден!", alert=True)
            return
            
        config_func = kernel.module_configs[module_name]
        default_config = config_func(kernel, module_name)
        current_config = await db.get_module_config(module_name)
        setting = default_config.get(key)
        if not setting:
            await event.answer("Настройка не найдена!", alert=True)
            return
            
        current_value = current_config.get(key, setting.get("default", "N/A"))
        default_value = setting.get("default", "N/A")
        description = setting.get("description", "Описание отсутствует.")
        
        text = f"<blockquote><b>⚙️ Управление параметром {key} модуля {module_name}</b>\nℹ️ {description}\n\nСтандартное: <code>{default_value}</code>\nТекущее: <code>{current_value}</code></blockquote>"
        
        buttons = [
            [Button.switch_inline("📝 Ввести значение", query=f"cfg_save_{module_name}_{key} ", same_peer=True)],
            [Button.inline("⬅️ Назад", data=f"config_module_{module_name}")]
        ]
        await event.edit(text, parse_mode='html', buttons=buttons)
        return
        
    elif data.startswith("cfg_list_"):
        parts = data.split("_", 3)
        module_name, key = parts[2], parts[3]
        if module_name not in kernel.module_configs:
            await event.answer("Модуль не найден!", alert=True)
            return
            
        config_func = kernel.module_configs[module_name]
        default_config = config_func(kernel, module_name)
        current_config = await db.get_module_config(module_name)
        setting = default_config.get(key)
        if not setting or setting["type"] != "list":
            await event.answer("Неверная настройка!", alert=True)
            return
            
        current_value = current_config.get(key, setting.get("default", setting["options"][0]))
        option_buttons = []
        for option in setting["options"]:
            option_buttons.append([
                Button.inline(f"{'🔘' if option == current_value else '⚫'} {option}", 
                             data=f"cfg_save_{module_name}_{key}_{option}")
            ])
        option_buttons.append([Button.inline("⬅️ Назад", data=f"config_module_{module_name}")])
        
        await event.edit(
            f"<blockquote><b>⚙️ Выбор для {key} в {module_name}</b>\nТекущее: <code>{current_value}</code></blockquote>",
            parse_mode='html',
            buttons=option_buttons
        )
        return
        
    # Обработка кнопок SET TRUE/FALSE
    elif data.startswith("cfg_save_") and "_" in data[9:]:
        parts = data.split("_", 4)
        if len(parts) < 5:
            return
            
        module_name, key, raw_value = parts[2], parts[3], "_".join(parts[4:])
        if module_name not in kernel.module_configs:
            await event.answer("Модуль не найден!", alert=True)
            return
            
        # Преобразуем строку в bool
        if raw_value == "true":
            value = True
        elif raw_value == "false":
            value = False
        else:
            value = raw_value
            
        await db.set_module_config_value(module_name, key, value)
        
        await event.edit(
            f"<blockquote><b>⚙️ Параметр {key} модуля {module_name} сохранен!</b>\nТекущее: <code>{value}</code></blockquote>",
            parse_mode='html',
            buttons=[
                [Button.inline("⬅️ Назад", data=f"config_module_{module_name}")],
                [Button.inline("❌ Закрыть", data="config_close")]
            ]
        )
        return

def build_config_buttons(config_data, module_name):
    buttons = []
    for key, setting in config_data.items():
        if setting["type"] == "bool":
            status = "✅ Да" if setting["value"] else "❌ Нет"
            buttons.append([
                Button.inline(f"{status} {setting['name']}", data=f"cfg_toggle_{module_name}_{key}")
            ])
        elif setting["type"] == "str":
            buttons.append([
                Button.inline(f"📝 {setting['name']}", data=f"cfg_edit_{module_name}_{key}")
            ])
        elif setting["type"] == "list":
            buttons.append([
                Button.inline(f"🔄 {setting['name']}", data=f"cfg_list_{module_name}_{key}")
            ])
    return buttons

def is_owner(kernel, user_id):
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

def register(app, commands, module_name, kernel=None):
    commands["config"] = {"func": config_cmd, "module": module_name}
    if kernel is not None:
        asyncio.create_task(db.ensure_started())
        kernel.register_inline_handler(config_inline_handler)
        kernel.register_callback_handler(config_callback_handler)