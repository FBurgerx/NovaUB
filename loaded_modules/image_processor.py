"""
Модуль для обработки изображений.
Тестовый модуль с зависимостями.
"""

__meta__ = {
    "name": "Image Processor",
    "author": "NovaUB",
    "description": "Обработка изображений с помощью Pillow.",
    "commands": ["imginfo", "resize"],
    "requires": ["pillow>=9.0.0"]
}

import os
from PIL import Image


async def imginfo_cmd(client, message, args):
    """Показать информацию об изображении."""
    reply = await message.get_reply_message()
    
    if not reply or not reply.media:
        return await message.edit(
            "<blockquote><tg-emoji emoji-id=5775887550262546277>❗️</emoji> "
            "<b>Usage:</b> Ответьте на сообщение с изображением</blockquote>",
            parse_mode='html'
        )
    
    await message.edit(
        "<blockquote><tg-emoji emoji-id=5891211339170326418>⌛️</emoji> <b>Загрузка изображения...</b></blockquote>",
        parse_mode='html'
    )
    
    try:
        path = await reply.download_media()
        
        with Image.open(path) as img:
            info = (
                f"<blockquote><b>📊 Информация об изображении:</b>\n\n"
                f"<b>Формат:</b> <code>{img.format}</code>\n"
                f"<b>Размер:</b> <code>{img.width}x{img.height}</code>\n"
                f"<b>Режим:</b> <code>{img.mode}</code></blockquote>"
            )
        
        os.remove(path)
        await message.edit(info, parse_mode='html')
        
    except Exception as e:
        await message.edit(
            f"<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
            f"<b>Ошибка:</b> <code>{e}</code></blockquote>",
            parse_mode='html'
        )


async def resize_cmd(client, message, args):
    """Изменить размер изображения."""
    reply = await message.get_reply_message()
    
    if not reply or not reply.media:
        return await message.edit(
            "<blockquote><tg-emoji emoji-id=5775887550262546277>❗️</emoji> "
            "<b>Usage:</b> .resize [ширина] [высота] (ответ на фото)</blockquote>",
            parse_mode='html'
        )
    
    if len(args) < 2:
        return await message.edit(
            "<blockquote><tg-emoji emoji-id=5775887550262546277>❗️</emoji> "
            "<b>Usage:</b> .resize [ширина] [высота]</blockquote>",
            parse_mode='html'
        )
    
    try:
        width = int(args[0])
        height = int(args[1])
    except ValueError:
        return await message.edit(
            "<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
            "<b>Неверные размеры</b></blockquote>",
            parse_mode='html'
        )
    
    await message.edit(
        "<blockquote><tg-emoji emoji-id=5891211339170326418>⌛️</emoji> <b>Обработка...</b></blockquote>",
        parse_mode='html'
    )
    
    try:
        path = await reply.download_media()
        
        with Image.open(path) as img:
            resized = img.resize((width, height), Image.Resampling.LANCZOS)
            output_path = f"resized_{os.path.basename(path)}"
            resized.save(output_path)
        
        await client.send_file(
            message.chat_id,
            output_path,
            caption=f"<blockquote><b>✅ Изменён размер:</b> <code>{width}x{height}</code></blockquote>",
            parse_mode='html'
        )
        
        os.remove(path)
        os.remove(output_path)
        await message.delete()
        
    except Exception as e:
        await message.edit(
            f"<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
            f"<b>Ошибка:</b> <code>{e}</code></blockquote>",
            parse_mode='html'
        )


def get_config(kernel, module_name):
    """Конфигурация модуля."""
    return {
        "default_quality": {
            "type": "list",
            "name": "Качество по умолчанию",
            "default": "95",
            "options": ["75", "85", "95", "100"],
            "description": "Качество сохранения JPEG."
        }
    }


def register(app, commands, module_name, kernel=None):
    """Регистрация команд."""
    commands["imginfo"] = {"func": imginfo_cmd, "module": module_name}
    commands["resize"] = {"func": resize_cmd, "module": module_name}
