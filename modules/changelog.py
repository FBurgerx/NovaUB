# changelog.py
# Команда для просмотра истории изменений

import os
import html

async def changelog_cmd(client, message, args):
    """Показать историю изменений"""
    
    changelog_path = "CHANGELOG.md"
    
    if not os.path.exists(changelog_path):
        return await message.edit(
            "<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
            "<b>Changelog не найден</b></blockquote>",
            parse_mode='html'
        )
    
    try:
        with open(changelog_path, 'r', encoding='utf-8') as f:
            changelog = f.read()
        
        # Пропускаем заголовок "# Changelog" и добавляем свой с эмодзи
        if changelog.startswith('# Changelog'):
            changelog = changelog[len('# Changelog'):]
        
        # Форматируем текст
        text = html.escape(changelog.strip())
        
        # Разбиваем на части если больше 4000 символов
        if len(text) > 4000:
            text = text[:3990] + "\n\n<i>... продолжение в файле CHANGELOG.md</i>"
        
        await message.edit(
            f"<blockquote expandable>\n"
            f"<tg-emoji emoji-id=5897962422169243693>📝</emoji> <b>Changelog</b>\n\n"
            f"{text}"
            f"</blockquote>",
            parse_mode='html'
        )
    
    except Exception as e:
        await message.edit(
            f"<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
            f"<b>Ошибка:</b> <code>{html.escape(str(e))}</code></blockquote>",
            parse_mode='html'
        )


def register(app, commands, module_name):
    """Регистрация команды"""
    commands["changelog"] = {
        "func": changelog_cmd,
        "module": module_name,
        "description": "Показать историю изменений"
    }
