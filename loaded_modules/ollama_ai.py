# ollama_ai.py
# Локальный ИИ-ассистент через Ollama
# Системный промпт через .set_prompt_ai
# История разговора до 100 сообщений с каждой стороны

import asyncio
import html
import json
from telethon import events

# ────────────────────────────────────────────────
# Настройки
# ────────────────────────────────────────────────

OLLAMA_HOST = "http://127.0.0.1:11434"
MODEL = "gemini-3-flash-preview"
TIMEOUT = 120
MAX_TOKENS = 4096
MAX_HISTORY_PER_SIDE = 100  # 100 сообщений с каждой стороны

# ────────────────────────────────────────────────

async def ai_cmd(client, message, args):
    chat_id = message.chat_id
    query = " ".join(args).strip()

    if not query:
        return await message.edit(
            "<blockquote><tg-emoji emoji-id=5775887550262546277>❗️</emoji> "
            "<b>Usage: .ai [твой вопрос]</b></blockquote>",
            parse_mode='html'
        )

    # Получаем/инициализируем историю и промпт
    if not hasattr(client.kernel, 'ai_history'):
        client.kernel.ai_history = {}
    if not hasattr(client.kernel, 'ai_system_prompt'):
        client.kernel.ai_system_prompt = "Ты полезный и умный ассистент."

    history = client.kernel.ai_history.get(chat_id, [])
    system_prompt = client.kernel.ai_system_prompt

    # Формируем контекст для Ollama
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # Добавляем историю (последние N пар)
    start_idx = max(0, len(history) - MAX_HISTORY_PER_SIDE * 2)
    for i in range(start_idx, len(history), 2):
        messages.append({"role": "user", "content": history[i]})
        if i + 1 < len(history):
            messages.append({"role": "assistant", "content": history[i+1]})

    # Добавляем текущий запрос
    messages.append({"role": "user", "content": query})

    # Начальное сообщение
    msg = await message.edit(
        "<blockquote><tg-emoji emoji-id=5891211339170326418>⌛️</emoji> "
        f"<b>Генерирую ответ ({MODEL})...</b></blockquote>",
        parse_mode='html'
    )

    try:
        import aiohttp

        payload = {
            "model": MODEL,
            "messages": messages,
            "stream": False,  # для простоты используем non-stream, т.к. стриминг с messages иногда глючит
            "options": {
                "temperature": 0.75,
                "top_p": 0.9,
                "num_predict": MAX_TOKENS
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_HOST}/api/chat",
                json=payload,
                timeout=TIMEOUT
            ) as resp:

                if resp.status != 200:
                    text = await resp.text()
                    return await msg.edit(
                        f"<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
                        f"<b>Ollama ошибка {resp.status}</b>\n<code>{html.escape(text[:500])}</code></blockquote>",
                        parse_mode='html'
                    )

                data = await resp.json()
                response_text = data.get("message", {}).get("content", "").strip()

                if not response_text:
                    return await msg.edit(
                        "<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
                        "<b>Пустой ответ от модели</b></blockquote>",
                        parse_mode='html'
                    )

                # Экранируем и отправляем
                escaped = html.escape(response_text)
                await msg.edit(
                    f"<blockquote expandable>"
                    f"<b>Запрос:</b> <code>{html.escape(query[:180])}...</code>\n\n"
                    f"<b>Ответ ({MODEL}):</b>\n"
                    f"<code>{escaped}</code>"
                    f"</blockquote>",
                    parse_mode='html'
                )

                # Сохраняем в историю
                history.append(query)
                history.append(response_text)

                # Ограничиваем длину истории
                if len(history) > MAX_HISTORY_PER_SIDE * 2:
                    history = history[-MAX_HISTORY_PER_SIDE * 2:]

                client.kernel.ai_history[chat_id] = history

    except ImportError:
        await msg.edit(
            "<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
            "<b>Не установлен aiohttp</b>\n<code>pip install aiohttp</code></blockquote>",
            parse_mode='html'
        )
    except asyncio.TimeoutError:
        await msg.edit(
            "<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
            f"<b>Ответ от Ollama не пришёл за {TIMEOUT} секунд</b></blockquote>",
            parse_mode='html'
        )
    except Exception as e:
        await msg.edit(
            f"<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
            f"<b>Ошибка:</b> <code>{type(e).__name__}: {html.escape(str(e))}</code></blockquote>",
            parse_mode='html'
        )


async def set_prompt_ai_cmd(client, message, args):
    if not args:
        current_prompt = getattr(client.kernel, 'ai_system_prompt', "Не установлен")
        return await message.edit(
            f"<blockquote><b>Текущий системный промпт:</b>\n<code>{html.escape(current_prompt)}</code>\n\n"
            "<b>Usage: .set_prompt_ai [новый промпт]</b></blockquote>",
            parse_mode='html'
        )

    new_prompt = " ".join(args).strip()
    client.kernel.ai_system_prompt = new_prompt

    await message.edit(
        "<blockquote><tg-emoji emoji-id=5776375003280838798>✅</emoji> "
        f"<b>Системный промпт установлен:</b>\n<code>{html.escape(new_prompt)}</code></blockquote>",
        parse_mode='html'
    )


def register(app, commands, module_name):
    commands["ai"] = {
        "func": ai_cmd,
        "module": module_name,
        "description": "Спрашивает локальную модель Ollama с историей и системным промптом"
    }
    commands["set_prompt_ai"] = {
        "func": set_prompt_ai_cmd,
        "module": module_name,
        "description": "Устанавливает системный промпт для .ai"
    }