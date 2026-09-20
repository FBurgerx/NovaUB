__meta__ = {
    "name": "Hello",
    "version": "1.0.0",
    "author": "Your Name",
    "description": "Приветственный модуль",
    "commands": ["hello", "greet"]
}

async def hello_cmd(client, message, args):
    """Отправить приветствие"""
    name = " ".join(args) if args else "мир"
    await message.edit(f"👋 Привет, {name}!")

async def greet_cmd(client, message, args):
    """Альтернативное приветствие"""
    await message.edit("🌟 Добро пожаловать!")

def register(app, commands, module_name):
    commands["hello"] = {"func": hello_cmd, "module": module_name}
    commands["greet"] = {"func": greet_cmd, "module": module_name}