from telethon import events

async def test_cmd(client, message, args):
    """Тестовая команда для проверки конфигурации."""
    kernel = client.kernel
    config_data = await kernel.get_module_config(__name__)
    
    enabled = config_data.get("enabled", True)
    api_key = config_data.get("api_key", "default")
    mode = config_data.get("mode", "fast")
    
    await message.edit(
        f"<blockquote><b>Тест конфигурации:</b>\n"
        f"Включено: <code>{enabled}</code>\n"
        f"API Ключ: <code>{api_key}</code>\n"
        f"Режим: <code>{mode}</code></blockquote>",
        parse_mode='html'
    )

def get_config(kernel, module_name):
    """Возвращает конфигурацию для этого модуля."""
    return {
        "enabled": {
            "type": "bool",
            "name": "Активен",
            "default": True,
            "description": "Включить или выключить модуль."
        },
        "api_key": {
            "type": "str",
            "name": "API Ключ",
            "default": "default_key",
            "description": "Секретный ключ для API."
        },
        "mode": {
            "type": "list",
            "name": "Режим работы",
            "default": "fast",
            "options": ["fast", "slow", "ultra", "turbo"],
            "description": "Выберите режим работы модуля."
        }
    }

def register(app, commands, module_name, kernel=None):
    commands["testcfg"] = {"func": test_cmd, "module": module_name}