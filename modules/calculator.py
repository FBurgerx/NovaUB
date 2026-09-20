import os
import json
import re
from telethon import events, Button

def calculate_expression(expr: str):
    """Безопасно вычисляет простое математическое выражение."""
    # Удаляем все, кроме разрешенных символов
    expr = re.sub(r'[^0-9+\-*/().\s]', '', expr)
    if not expr:
        raise ValueError("Пустое выражение")
    
    # Защита от опасных штук
    if '..' in expr or '//' in expr or expr.count('(') != expr.count(')'):
        raise ValueError("Некорректное выражение")
    
    try:
        # Используем eval с пустыми globals и locals для безопасности
        result = eval(expr, {"__builtins__": {}}, {})
        return result
    except ZeroDivisionError:
        raise ValueError("Деление на ноль")
    except Exception as e:
        raise ValueError(f"Ошибка: {e}")

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

# === Команды для юзербота ===
async def calc_cmd(client, message, args):
    if not args:
        return await message.edit(
            "<blockquote><b>Использование:</b> <code>.calc &lt;выражение&gt;</code>\nПример: <code>.calc 2 + 2 * 5</code></blockquote>",
            parse_mode='html'
        )
    
    expression = " ".join(args)
    try:
        result = calculate_expression(expression)
        await message.edit(
            f"<blockquote><b>Результат:</b> <code>{result}</code></blockquote>",
            parse_mode='html'
        )
    except Exception as e:
        await message.edit(
            f"<blockquote><b>Ошибка:</b> <code>{e}</code></blockquote>",
            parse_mode='html'
        )

# === Обработчики для инлайн-бота ===
async def inline_calc_handler(event: events.InlineQuery.Event):
    kernel = event.client.kernel
    user_id = event.sender_id
    query = event.text.strip()

    # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Игнорируем запросы, не относящиеся к калькулятору ---
    if not query.startswith("calc"):
        return  # <-- Это позволяет другим обработчикам работать

    if not is_owner(kernel, user_id):
        builder = event.builder
        no_access_result = builder.article(
            title="🔒 Доступ запрещен",
            description="Эта функция доступна только владельцам.",
            text="<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> <b>Доступ запрещен.</b>\nЭта функция доступна только владельцам юзербота.</blockquote>",
            parse_mode='html'
        )
        await event.answer([no_access_result], switch_pm="Доступ запрещен", switch_pm_param="forbidden")
        return

    if query == "calc":
        builder = event.builder
        help_result = builder.article(
            title="🔢 Калькулятор",
            description="Введите выражение, например: calc 2+2*3",
            text="<blockquote><b>Использование:</b> <code>calc &lt;выражение&gt;</code>\nПример: <code>calc 2 + 2 * 5</code></blockquote>",
            parse_mode='html'
        )
        await event.answer([help_result], switch_pm="Как использовать", switch_pm_param="help")
        return

    if query.startswith("calc "):
        expression = query[5:]
        try:
            result_value = calculate_expression(expression)
            result_text = f"<blockquote><b>Выражение:</b> <code>{expression}</code>\n<b>Результат:</b> <code>{result_value}</code></blockquote>"
            
            builder = event.builder
            result = builder.article(
                title=f"Результат: {result_value}",
                description=expression,
                text=result_text,
                parse_mode='html'
            )
            await event.answer([result])
        except Exception as e:
            builder = event.builder
            error_result = builder.article(
                title="❌ Ошибка",
                description=str(e),
                text=f"<blockquote><b>Ошибка при вычислении:</b>\n<code>{expression}</code>\n\n<code>{e}</code></blockquote>",
                parse_mode='html'
            )
            await event.answer([error_result], switch_pm="Ошибка", switch_pm_param="error")

async def bot_calc_handler(event: events.NewMessage.Event):
    kernel = event.client.kernel
    user_id = event.sender_id

    if not is_owner(kernel, user_id):
        await event.reply(
            "<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> <b>Доступ запрещен.</b>\nЭта команда доступна только владельцам юзербота.</blockquote>",
            parse_mode='html'
        )
        return

    text = event.message.text
    match = re.match(r'/calc(?:@\w+)?\s+(.+)', text, re.IGNORECASE)
    if not match:
        await event.reply(
            "<blockquote><b>Использование:</b> <code>/calc &lt;выражение&gt;</code>\nПример: <code>/calc 2 + 2 * 5</code></blockquote>",
            parse_mode='html'
        )
        return
    
    expression = match.group(1)
    try:
        result = calculate_expression(expression)
        await event.reply(
            f"<blockquote><b>Результат:</b> <code>{result}</code></blockquote>",
            parse_mode='html'
        )
    except Exception as e:
        await event.reply(
            f"<blockquote><b>Ошибка:</b> <code>{e}</code></blockquote>",
            parse_mode='html'
        )

def register(app, commands, module_name, kernel=None):
    commands["calc"] = {"func": calc_cmd, "module": module_name}
    
    if kernel is not None and hasattr(kernel, 'register_bot_command') and hasattr(kernel, 'register_inline_handler'):
        if hasattr(kernel, 'inline_bot') and kernel.inline_bot and kernel.inline_bot.bot_client:
            kernel.inline_bot.bot_client.kernel = kernel
        
        kernel.register_bot_command("calc", bot_calc_handler)
        kernel.register_inline_handler(inline_calc_handler)
        print(f"[Calculator] Инлайн-команды зарегистрированы.")