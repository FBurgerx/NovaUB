import os
import json
import time
import zipfile
import html as html_mod

from telethon.tl.types import PeerChannel


async def backup_cmd(client, message, args):
    """Создает резервную копию и отправляет в топик 'Бекапы'."""
    user_id = client._self_id
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_file = f"novaub_backup_{user_id}_{timestamp}.zip"

    await message.edit(
        "<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Создаю бекап...</b>",
        parse_mode='html'
    )

    try:
        files_added = 0
        with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            config_files = [
                f"config-{user_id}.json",
                f"kernel_config-{user_id}.json",
                f"telegram_api-{user_id}.json",
                "novaub.db",
            ]
            for cf in config_files:
                if os.path.exists(cf):
                    zf.write(cf, cf)
                    files_added += 1

            lm_dir = "loaded_modules"
            if os.path.isdir(lm_dir):
                for fname in os.listdir(lm_dir):
                    fpath = os.path.join(lm_dir, fname)
                    if os.path.isfile(fpath):
                        zf.write(fpath, os.path.join("loaded_modules", fname))
                        files_added += 1

        zip_size = os.path.getsize(backup_file)
        if zip_size < 1024 * 1024:
            size_str = f"{zip_size / 1024:.1f} KB"
        else:
            size_str = f"{zip_size / (1024 * 1024):.2f} MB"

        sent = False
        kernel = getattr(client, 'kernel', None)
        if kernel and kernel.inline_bot and kernel.inline_bot.bot_client:
            config_path = f"config-{user_id}.json"
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        config = json.load(f)
                    group_id = config.get("management_group_id")
                    topics = config.get("management_topics", {})
                    topic_id = topics.get("Бекапы")

                    if group_id and topic_id:
                        channel_id = -group_id if group_id < 0 else group_id
                        entity = PeerChannel(channel_id)

                        caption = (
                            f"<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>NovaUB Backup</b>\n\n"
                            f"<blockquote><b>Account:</b> <code>{user_id}</code>\n"
                            f"<b>Files:</b> <code>{files_added}</code>\n"
                            f"<b>Size:</b> <code>{size_str}</code>\n"
                            f"<b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code></blockquote>"
                        )

                        await kernel.inline_bot.bot_client.send_file(
                            entity=entity,
                            file=backup_file,
                            caption=caption,
                            parse_mode='html',
                            reply_to=topic_id,
                        )
                        sent = True
                except Exception:
                    pass

        if sent:
            await message.edit(
                f"<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Бекап создан</b>\n\n"
                f"<blockquote><b>Файлов:</b> <code>{files_added}</code>\n"
                f"<b>Размер:</b> <code>{size_str}</code>\n"
                f"<b>Отправлен в топик «Бекапы»</b></blockquote>",
                parse_mode='html'
            )
        else:
            await message.edit(
                "<b>Ошибка:</b> не удалось отправить бекап в группу. "
                "Проверьте настройку management-группы и инлайн-бота.",
                parse_mode='html'
            )

    except Exception as e:
        await message.edit(
            f"<b>Ошибка создания бекапа:</b> <code>{html_mod.escape(str(e))}</code>",
            parse_mode='html'
        )
    finally:
        if os.path.exists(backup_file):
            os.remove(backup_file)


async def restore_cmd(client, message, args):
    """Восстанавливает данные из резервной копии."""
    if not message.is_reply:
        await message.edit(
            "<b>Ответьте на сообщение с ZIP-файлом бекапа.</b>",
            parse_mode='html'
        )
        return

    reply = await message.get_reply_message()
    if not reply.file or not reply.file.name or not reply.file.name.endswith('.zip'):
        await message.edit(
            "<b>Ответьте на ZIP-файл с бекапом.</b>",
            parse_mode='html'
        )
        return

    backup_path = None
    try:
        await message.edit(
            "<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Загрузка бекапа...</b>",
            parse_mode='html'
        )
        backup_path = await reply.download_media()

        await message.edit(
            "<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Распаковка бекапа...</b>",
            parse_mode='html'
        )
        with zipfile.ZipFile(backup_path, 'r') as zf:
            zf.extractall()

        os.remove(backup_path)
        backup_path = None
        await message.edit(
            "<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Бекап восстановлен</b>\n\n"
            "<blockquote>Перезагрузите юзербота для применения изменений.</blockquote>",
            parse_mode='html'
        )
    except Exception as e:
        if backup_path and os.path.exists(backup_path):
            os.remove(backup_path)
        await message.edit(
            f"<b>Ошибка восстановления:</b> <code>{html_mod.escape(str(e))}</code>",
            parse_mode='html'
        )


def register(app, commands, module_name, kernel=None):
    commands["backup"] = {
        "func": backup_cmd,
        "module": module_name,
        "description": "Создать бекап и отправить в management-группу",
    }
    commands["restore"] = {
        "func": restore_cmd,
        "module": module_name,
        "description": "Восстановить из бекапа (ответом на ZIP)",
    }
