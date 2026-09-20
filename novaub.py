import asyncio
import os
import json
import sys
import subprocess
import time
import re
import threading
import importlib.util
import inspect

from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel, PeerChat, PeerUser
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    InviteToChannelRequest,
)

# ── Импорты, которых может не быть в установленной версии telethon ───────
# Ядро не должно падать при старте только из-за того, что telethon старый:
# функции, которым эти классы нужны, используют getattr-проверку и сами
# отключаются, если поддержки нет (см. _tl_class).

def _tl_class(module_name: str, name: str):
    """Достаёт TL-класс из telethon или возвращает None, если его нет."""
    try:
        module = __import__(
            f"telethon.tl.functions.{module_name}",
            fromlist=[name],
        )
    except Exception:
        return None
    return getattr(module, name, None)


# forum-топики: старые/обрезанные сборки telethon могут их не иметь
_CreateForumTopicRequest = _tl_class("channels", "CreateForumTopicRequest")
_GetForumTopicsRequest = _tl_class("channels", "GetForumTopicsRequest")
# выдача админки: в старых версиях называется EditAdminRequest
_EditChatAdminRequest = (
    _tl_class("channels", "EditChatAdminRequest")
    or _tl_class("channels", "EditAdminRequest")
)

if _CreateForumTopicRequest is None:
    print("[i] telethon не поддерживает forum-топики — management-группа будет без топиков")
if _EditChatAdminRequest is None:
    print("[i] telethon не поддерживает выдачу админки — бот не станет админом management-группы")

from telethon.tl.types import ChatAdminRights

import sqlite3
import struct

from core.kernel import Kernel
from core import config as nova_config
from core import commands as nova_commands

# Корень проекта: novaub.py лежит в корне. Все файлы данных (сессии, логи,
# конфиги, БД) ищутся и создаются относительно него, а не от CWD запуска.
ROOT = os.path.dirname(os.path.abspath(__file__))

# Telethon-MCUB по умолчанию ставит protection mode 'strict', который блокирует
# account.GetPasswordRequest. Telethon вызывает его внутри sign_in(password=...)
# и check_password(), поэтому войти в аккаунт с 2FA вообще невозможно.
# Protection mode настраивается в config-<id>.json -> protection.mode
# (по умолчанию 'safe': всё ещё блокирует удаление аккаунта, сброс сессий и
# пароля, логоут, но разрешает вход по 2FA).
from core import config as nova_config

# Загружаем версию из файла
def get_version():
    try:
        with open(os.path.join(ROOT, 'version.txt'), 'r') as f:
            return f.read().strip()
    except:
        return "1.0.0"

FORELKA_VERSION = get_version()


def setup_git_safe_directory():
    """Автоматически добавляет текущую директорию в git safe.directory"""
    try:
        bot_dir = os.path.abspath(os.path.dirname(__file__))
        subprocess.run(
            ['git', 'config', '--global', '--add', 'safe.directory', bot_dir],
            check=True,
            capture_output=True,
            timeout=5
        )
    except Exception:
        pass  # Тихо игнорируем если git не установлен или нет доступа


# Вызываем настройку git при старте
setup_git_safe_directory()


def _convert_pyrogram_to_telethon(session_file):
    """Конвертирует Pyrogram .session в Telethon .session (если нужно)."""
    path = session_file if session_file.endswith(".session") else session_file + ".session"
    if not os.path.exists(path):
        return

    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        # Проверяем — это Pyrogram сессия?
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "sessions" not in tables or "version" not in tables:
            conn.close()
            return  # Уже Telethon или неизвестный формат

        # Читаем данные Pyrogram
        row = cur.execute("SELECT dc_id, auth_key, user_id FROM sessions").fetchone()
        if not row:
            conn.close()
            return

        dc_id, auth_key_bytes, user_id = row
        conn.close()

        if isinstance(auth_key_bytes, bytes) and len(auth_key_bytes) == 256:
            # DC серверные адреса Telethon
            dc_addresses = {
                1: "149.154.175.53",
                2: "149.154.167.51",
                3: "149.154.175.100",
                4: "149.154.167.91",
                5: "91.108.56.130",
            }
            server_address = dc_addresses.get(dc_id, "149.154.167.51")
            port = 443

            # Удаляем старый файл и создаём Telethon сессию
            os.remove(path)
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            cur.execute("""CREATE TABLE sessions (
                dc_id integer primary key,
                server_address text,
                port integer,
                auth_key blob,
                takeout_id integer
            )""")
            cur.execute("""CREATE TABLE entities (
                id integer primary key,
                hash integer not null,
                username text,
                phone integer,
                name text,
                date integer
            )""")
            cur.execute("""CREATE TABLE sent_files (
                md5_digest blob,
                file_size integer,
                type integer,
                id integer,
                hash integer,
                primary key(md5_digest, file_size, type)
            )""")
            cur.execute("""CREATE TABLE update_state (
                id integer primary key,
                pts integer,
                qts integer,
                date integer,
                seq integer
            )""")
            cur.execute("""CREATE TABLE version (version integer primary key)""")
            cur.execute("INSERT INTO version VALUES (7)")
            cur.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                (dc_id, server_address, port, auth_key_bytes, None)
            )
            conn.commit()
            conn.close()
            print(f"  [i] Сессия сконвертирована: Pyrogram → Telethon ({path})")
    except Exception as e:
        print(f"  [!] Ошибка конвертации сессии {path}: {e}")

class TerminalLogger:
    def __init__(self):
        self.terminal = sys.stdout
        self.log = open(os.path.join(ROOT, "novaub.log"), "a", encoding="utf-8")
        self.ignore_list = [
            "PERSISTENT_TIMESTAMP_OUTDATED",
            "updates.GetChannelDifference",
            "RPC_CALL_FAIL",
            "Retrying \"updates.GetChannelDifference\""
        ]
        
    def write(self, m):
        if not m.strip():
            return
        if any(x in m for x in self.ignore_list):
            return
        self.terminal.write(m)
        self.log.write(m)
        self.log.flush()
        try:
            self.terminal.flush()
        except Exception:
            pass
        
    def flush(self): 
        try:
            self.log.flush()
        except Exception:
            pass
        try:
            self.terminal.flush()
        except Exception:
            pass

sys.stdout = sys.stderr = TerminalLogger()

def _user_id_from_session(session_name: str):
    """Достаёт user_id из имени сессии 'nova-<id>' (или 0)."""
    base = session_name.replace("\\", "/").split("/")[-1]
    base = base[:-8] if base.endswith(".session") else base
    try:
        return int(str(base).split("-", 1)[1])
    except Exception:
        return 0

def load_saved_api_for_session(session_filename: str):
    """Возвращает (api_id, api_hash) из единого конфига аккаунта."""
    try:
        user_id = _user_id_from_session(session_filename)
        api_id, api_hash = nova_config.get_api_credentials(user_id)
        if api_id and api_hash:
            return int(api_id), str(api_hash)
    except Exception:
        pass

    # Легаси: telegram_api-<id>.json (-web login)
    try:
        base = session_filename[:-8]
        user_id = int(base.split("-", 1)[1])
    except Exception:
        return None

    path = f"telegram_api-{user_id}.json"
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        api_id = int(data["api_id"])
        api_hash = str(data["api_hash"])
        if not api_hash:
            return None
        return api_id, api_hash
    except Exception:
        return None

def _list_session_files():
    """Сессии nova-<id>.session и легаси forelka-<id>.session."""
    try:
        files = os.listdir(ROOT)
    except Exception:
        return []
    return sorted(
        [f for f in files if (f.startswith("nova-") or f.startswith("forelka-")) and f.endswith(".session")],
        key=lambda p: os.path.getmtime(p),
    )

def _pick_latest_session():
    sess = _list_session_files()
    return sess[-1] if sess else None

async def _terminal_login_create_session():
    api_id = input("API ID: ")
    api_hash = input("API HASH: ")
    temp = TelegramClient("temp", api_id, api_hash)
    await temp.start()
    me = await temp.get_me()
    await temp.disconnect()
    os.rename("temp.session", os.path.join(ROOT, f"nova-{me.id}.session"))
    return os.path.join(ROOT, f"nova-{me.id}.session")

def _watch_process_output_for_url(proc: subprocess.Popen, label: str):
    url_re = re.compile(r"(https?://[a-zA-Z0-9.-]+\.(?:localhost\.run|lhr\.life))")
    found = {"url": None}
    verbose = os.environ.get("FORELKA_TUNNEL_VERBOSE", "").strip() in ("1", "true", "yes", "on")

    def run():
        try:
            if proc.stdout is None:
                return
            for line in proc.stdout:
                if verbose:
                    try:
                        sys.stdout.write(f"[{label}] {line}")
                    except Exception:
                        pass
                m = url_re.search(line)
                if m and not found["url"]:
                    url = m.group(1)
                    if "admin.localhost.run" in url or "localhost.run/docs" in url:
                        continue
                    found["url"] = url
                    print(f"\nPublic URL: {found['url']}\n")
        except Exception:
            pass

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return found

async def _web_login_create_session(with_tunnel: bool = False):
    before = set(_list_session_files())

    host = os.environ.get("FORELKA_WEB_HOST", "127.0.0.1")
    port = os.environ.get("FORELKA_WEB_PORT", "8000")
    print(f"Web panel: http://{host}:{port}")

    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "web", "webapp.py")],
        env={**os.environ, "FORELKA_WEB_HOST": host, "FORELKA_WEB_PORT": str(port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    tunnel_proc = None
    if with_tunnel:
        try:
            tunnel_proc = subprocess.Popen(
                [sys.executable, "-u", "tunnel.py"],
                env={
                    **os.environ,
                    "FORELKA_WEB_HOST": host,
                    "FORELKA_WEB_PORT": str(port),
                    "FORELKA_TUNNEL_QUIET": "1",
                    "PYTHONUNBUFFERED": "1",
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            _watch_process_output_for_url(tunnel_proc, "tunnel")
        except Exception as e:
            print(f"[tunnel] Failed to start tunnel: {e}")
            tunnel_proc = None

    try:
        while True:
            await asyncio.sleep(0.6)
            now = set(_list_session_files())
            created = [s for s in now - before]
            if created:
                created.sort(key=lambda p: os.path.getmtime(p))
                return created[-1], proc, tunnel_proc

            if proc.poll() is not None:
                raise RuntimeError("web login server stopped unexpectedly")
    except KeyboardInterrupt:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            pass
        if tunnel_proc:
            try:
                tunnel_proc.terminate()
                tunnel_proc.wait(timeout=5)
            except Exception:
                pass
        raise

def is_owner(client, user_id):
    return nova_config.is_owner(client._self_id, user_id)


# Пер-пользовательный кулдаун команд (новый стиль: @command(cooldown=...))
_cooldown = nova_commands.Cooldown()

def _prefix_and_aliases(client, user_id=None):
    """Префикс и алиасы из единого конфига (с кэшем)."""
    cfg = nova_config.load(user_id or client._self_id)
    return cfg.prefix, (cfg.aliases or {})


def _check_access(level: str, client, user_id) -> bool:
    """Проверяет уровень доступа команды.

    public  — все
    trusted — владелец или доверенный (owners из конфига)
    owner   — только владелец
    """
    level = (level or "owner").lower()
    if level == "public":
        return True
    if level == "trusted":
        return nova_config.is_owner(client._self_id, user_id)
    return nova_config.is_owner(client._self_id, user_id)


async def handler(event):
    client = event.client
    message = event.message

    if not message.text:
        return

    from_id = getattr(message, "sender_id", None) or getattr(getattr(message, "sender", None), "id", None)
    pref, aliases = _prefix_and_aliases(client)

    if not message.text.startswith(pref):
        return

    parts = message.text[len(pref):].split(maxsplit=1)
    if not parts:
        return

    cmd = parts[0].lower()
    args = parts[1].split() if len(parts) > 1 else []

    # Resolve alias
    if cmd not in client.commands and cmd in aliases:
        cmd = aliases[cmd]

    if cmd in client.commands:
        entry = client.commands[cmd]
        # Прячем алиасы из dispatch — они разрешаются на основном имени
        if entry.get("alias_of"):
            cmd = entry["alias_of"]
            entry = client.commands.get(cmd, entry)

        # --- Права ---
        level = entry.get("level", "owner")
        if not _check_access(level, client, from_id):
            try:
                await message.edit(
                    "<blockquote><tg-emoji emoji-id=5778527486270770928>⛔</tg-emoji> "
                    "<b>Доступ запрещён.</b></blockquote>",
                    parse_mode="html",
                )
            except Exception:
                pass
            return

        # --- Кулдаун ---
        cooldown = entry.get("cooldown") or 0
        if cooldown and not _cooldown.check(cmd, from_id, cooldown):
            try:
                await message.edit(
                    "<blockquote><tg-emoji emoji-id=5891211339170326418>⌛</tg-emoji> "
                    "<b>Слишком быстро.</b> Подождите немного.</blockquote>",
                    parse_mode="html",
                )
            except Exception:
                pass
            return

        try:
            await client.commands[cmd]["func"](client, message, args)
            if hasattr(client, 'kernel') and client.kernel:
                log_text = (
                    f"<blockquote>"
                    f"<b>Команда:</b> <code>{pref}{cmd}</code>\n"
                    f"<b>Chat:</b> <code>{message.chat_id}</code>\n"
                    f"<b>Time:</b> <code>{time.strftime('%H:%M:%S')}</code>"
                    f"</blockquote>"
                )
                asyncio.create_task(client.kernel.send_to_topic("Команды", log_text))
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            if hasattr(client, 'kernel') and client.kernel:
                err_text = (
                    f"<blockquote>"
                    f"<b>Ошибка в команде:</b> <code>{pref}{cmd}</code>\n"
                    f"<b>Chat:</b> <code>{message.chat_id}</code>\n"
                    f"<b>Error:</b> <code>{type(e).__name__}: {e}</code>\n"
                    f"<b>Time:</b> <code>{time.strftime('%H:%M:%S')}</code>"
                    f"</blockquote>"
                )
                asyncio.create_task(client.kernel.send_to_topic("Логи", err_text))

async def owner_handler(event):
    client = event.client
    message = event.message
    
    if not message.text or not message.sender_id:
        return
    
    if not is_owner(client, message.sender_id):
        return

    pref, aliases = _prefix_and_aliases(client)

    if not message.text.startswith(pref):
        return

    parts = message.text[len(pref):].split(maxsplit=1)
    if not parts:
        return

    cmd = parts[0].lower()
    args = parts[1].split() if len(parts) > 1 else []

    # Resolve alias
    if cmd not in client.commands and cmd in aliases:
        cmd = aliases[cmd]

    if cmd in client.commands:
        entry = client.commands[cmd]
        if entry.get("alias_of"):
            cmd = entry["alias_of"]
            entry = client.commands.get(cmd, entry)

        # owner_handler и так работает только от владельца — права избыточны,
        # но кулдаун всё равно уважаем
        cooldown = entry.get("cooldown") or 0
        if cooldown and not _cooldown.check(cmd, message.sender_id, cooldown):
            try:
                await client.send_message(
                    message.chat_id,
                    "<blockquote><tg-emoji emoji-id=5891211339170326418>⌛</tg-emoji> "
                    "<b>Слишком быстро.</b> Подождите немного.</blockquote>",
                    parse_mode="html",
                )
            except Exception:
                pass
            return

        try:
            sent_msg = await client.send_message(message.chat_id, message.text)
            await client.commands[cmd]["func"](client, sent_msg, args)
            if hasattr(client, 'kernel') and client.kernel:
                log_text = (
                    f"<blockquote>"
                    f"<b>Команда:</b> <code>{pref}{cmd}</code>\n"
                    f"<b>From owner:</b> <code>{message.sender_id}</code>\n"
                    f"<b>Chat:</b> <code>{message.chat_id}</code>\n"
                    f"<b>Time:</b> <code>{time.strftime('%H:%M:%S')}</code>"
                    f"</blockquote>"
                )
                asyncio.create_task(client.kernel.send_to_topic("Команды", log_text))
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            if hasattr(client, 'kernel') and client.kernel:
                err_text = (
                    f"<blockquote>"
                    f"<b>Ошибка в команде:</b> <code>{pref}{cmd}</code>\n"
                    f"<b>From owner:</b> <code>{message.sender_id}</code>\n"
                    f"<b>Chat:</b> <code>{message.chat_id}</code>\n"
                    f"<b>Error:</b> <code>{type(e).__name__}: {e}</code>\n"
                    f"<b>Time:</b> <code>{time.strftime('%H:%M:%S')}</code>"
                    f"</blockquote>"
                )
                asyncio.create_task(client.kernel.send_to_topic("Логи", err_text))

async def edited_handler(event):
    await handler(event)

async def setup_management_group(kernel):
    """Создаёт management группу без добавления бота (бот добавляется позже)."""
    config = nova_config.load(kernel.client._self_id)

    if config.management_group_id:
        print("Management группа уже существует.")
        return

    print("Настройка группы управления...")

    if _CreateForumTopicRequest is None:
        print("[!] Управление топиками недоступно — telethon не поддерживает forum-топики")

    try:
        group = await kernel.client(CreateChannelRequest(
            title="NovaUB Management",
            about="Группа для управления юзерботом NovaUB.",
            megagroup=True,
            forum=True
        ))
        group_id = -group.chats[0].id
        print(f"Супергруппа создана: {group_id}")

        # Создаём топики (только если telethon поддерживает)
        topics = ["Логи", "Команды", "Бекапы", "Мусорка"]
        topic_ids = {}
        if _CreateForumTopicRequest is not None:
            for topic_name in topics:
                result = await kernel.client(_CreateForumTopicRequest(
                    peer=group_id,
                    title=topic_name
                ))
                topic_ids[topic_name] = result.updates[0].id
                print(f"Топик '{topic_name}' создан.")
        else:
            print(f"[!] Пропускаю создание топиков: {topics}")

        config["management_group_id"] = group_id
        config["management_topics"] = topic_ids
        nova_config.save(kernel.client._self_id, config)

        print("Группа управления создана!")
        print("⚠️ Инлайн-бот будет добавлен после запуска...")

    except Exception as e:
        print(f"Ошибка при настройке группы: {e}")

async def add_bot_to_management_group(kernel):
    """Добавляет инлайн-бота в management группу (megagroup) после его запуска."""
    config = nova_config.load(kernel.client._self_id)

    # Проверяем что группа уже создана
    if "management_group_id" not in config:
        print("Management группа ещё не создана.")
        return

    # Проверяем что инлайн-бот запущен
    if not hasattr(kernel, 'inline_bot') or not kernel.inline_bot:
        print("Инлайн-бот не инициализирован.")
        return

    if not kernel.inline_bot.username:
        print("Username бота не установлен (возможно бот ещё не создан).")
        return

    # Проверяем что bot_client подключён
    if not kernel.inline_bot.bot_client or not kernel.inline_bot.bot_client.is_connected():
        print("Bot client не подключён (бот ещё не запущен).")
        return

    group_id = config["management_group_id"]

    try:
        # Получаем entity бота
        bot_entity = await kernel.client.get_entity(f"@{kernel.inline_bot.username}")

        # Проверяем состоит ли уже бот в группе
        try:
            group_entity = await kernel.client.get_entity(group_id)
            
            # Получаем участников группы чтобы проверить есть ли там бот
            participants = await kernel.client.get_participants(group_entity)
            bot_in_group = any(p.user_id == bot_entity.id for p in participants)

            if bot_in_group:
                print("✓ Инлайн-бот уже состоит в management группе.")
                return

        except Exception as e:
            print(f"⚠️ Не удалось проверить участие бота: {e}")

        # Конвертируем group_id в положительный для PeerChannel (group_id отрицательный)
        channel_id = -group_id if group_id < 0 else group_id

        # Добавляем бота в группу используя правильный API для каналов/megagroups
        await kernel.client(InviteToChannelRequest(
            channel=PeerChannel(channel_id),
            users=[bot_entity]
        ))
        print("✓ Инлайн-бот добавлен в management группу.")

        # Назначаем бота админом со всеми правами
        if _EditChatAdminRequest is None:
            print("[!] telethon не поддерживает выдачу админки — пропуск")
            return

        full_rights = ChatAdminRights(
            post_messages=True,
            edit_messages=True,
            delete_messages=True,
            ban_users=True,
            invite_users=True,
            pin_messages=True,
            add_admins=True,
            anonymous=False,
            manage_call=True,
            other=True
        )
        await kernel.client(_EditChatAdminRequest(
            channel=PeerChannel(channel_id),
            user_id=bot_entity.id,
            admin_rights=full_rights,
            rank="NovaUB Bot"
        ))
        print("✓ Инлайн-бот назначен админом management группы.")

    except Exception as e:
        print(f"✗ Ошибка при добавлении бота в группу: {e}")

async def retry_add_bot_to_group(kernel):
    """Команда для ручного добавления бота в management группу."""
    print("\n🔄 Повторная попытка добавить бота в management группу...")
    await add_bot_to_management_group(kernel)

# === ИСПРАВЛЕННАЯ ФУНКЦИЯ ЗАГРУЗКИ МОДУЛЕЙ ===
def load_modules_with_config(client, kernel):
    """Загружает модули из modules/ и loaded_modules/ + регистрирует loader

    Поддерживает два стиля:
      1. Новый — команды объявлены через @command(...) в теле модуля.
         Ядро само собирает их, алиасы, описания, уровни доступа и кулдауны.
      2. Старый — модуль экспортирует register(app, commands, module_name[, kernel]).
         Оставлен для обратной совместимости.
    """
    commands = {}
    kernel.module_configs = getattr(kernel, 'module_configs', {})

    # Хуки жизненного цикла: "startup" / "shutdown"
    client._novaub_hooks = {"startup": [], "shutdown": []}

    folders = [os.path.join(ROOT, "modules"), os.path.join(ROOT, "loaded_modules")]

    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder)
            continue

        for module_file in os.listdir(folder):
            if not module_file.endswith('.py') or module_file == '__init__.py':
                continue

            module_name = module_file[:-3]
            full_path = os.path.join(folder, module_file)

            try:
                spec = importlib.util.spec_from_file_location(module_name, full_path)
                if spec is None:
                    continue

                module = importlib.util.module_from_spec(spec)
                sys.modules[f"modules_{module_name}" if os.path.basename(folder) == "modules" else f"loaded_{module_name}"] = module
                spec.loader.exec_module(module)

                # --- Новый стиль: декораторы @command/@inline/@hook ---
                try:
                    collected = nova_commands.collect(module)
                except Exception as e:
                    print(f"[-] Ошибка сбора команд {module_name}: {type(e).__name__}: {e}")
                    collected = {"commands": [], "inlines": [], "hooks": []}

                if collected["commands"] or collected["inlines"] or collected["hooks"]:
                    for cmd in collected["commands"]:
                        entry = {
                            "func": cmd["func"],
                            "module": module_name,
                            "name": cmd["name"],
                            "aliases": cmd.get("aliases", []),
                            "desc": cmd.get("desc", ""),
                            "usage": cmd.get("usage", ""),
                            "example": cmd.get("example", ""),
                            "cooldown": cmd.get("cooldown", 0),
                            "level": cmd.get("level", "owner"),
                            "hidden": cmd.get("hidden", False),
                        }
                        commands[cmd["name"]] = entry
                        # алиасы разрешаются ядром при dispatch
                        for alias in cmd.get("aliases", []):
                            commands.setdefault(alias, dict(entry, name=alias, alias_of=cmd["name"]))
                        print(f"  [c] .{cmd['name']}" + (f" (+{len(cmd.get('aliases', []))} алиас)" if cmd.get('aliases') else ""))

                    for il in collected["inlines"]:
                        if kernel is not None:
                            kernel.register_inline_handler(il["func"])
                            print(f"  [i] inline: {il['name']}")

                    for hk in collected["hooks"]:
                        evt = hk.get("event", "")
                        if evt in client._novaub_hooks:
                            client._novaub_hooks[evt].append(hk["func"])
                            print(f"  [h] hook: {evt}")

                    print(f"[+] Загружен модуль: {module_name} (новый стиль) из {folder}")
                else:
                    # --- Старый стиль: register() ---
                    if hasattr(module, 'register'):
                        sig = inspect.signature(module.register)
                        num_params = len(sig.parameters)

                        if num_params >= 4:
                            module.register(client, commands, module_name, kernel)
                        elif num_params == 3:
                            module.register(client, commands, module_name)
                        elif num_params == 2:
                            module.register(client, commands)
                        else:
                            module.register(client)

                        print(f"[+] Загружен модуль: {module_name} из {folder}")

                if hasattr(module, 'get_config'):
                    kernel.module_configs[module_name] = module.get_config
                    print(f"    [i] Конфигурация зарегистрирована для: {module_name}")

                if not hasattr(client, 'loaded_modules'):
                    client.loaded_modules = set()
                client.loaded_modules.add(module_name)

            except Exception as e:
                print(f"[-] Ошибка загрузки {module_name} из {folder}: {type(e).__name__}: {e}")

    return commands

async def main():
    sess = _pick_latest_session()
    web_proc = None
    tunnel_proc = None

    if not sess:
        print("No session found.")
        print("Choose login method:")
        print("  1) Terminal (API ID/HASH + phone in terminal)")
        print("  2) Web panel (HTML login page)")
        print("  3) Web + tunnel (HTML + public localhost.run URL)")
        choice = (input("> ").strip() or "2").lower()

        if choice in ("1", "t", "term", "terminal"):
            sess = await _terminal_login_create_session()
        elif choice in ("2", "w", "web"):
            sess, web_proc, tunnel_proc = await _web_login_create_session(with_tunnel=False)
        elif choice in ("3", "wt", "web+tunnel", "web+t"):
            sess, web_proc, tunnel_proc = await _web_login_create_session(with_tunnel=True)
        else:
            print("Cancelled.")
            return

    if web_proc:
        try:
            web_proc.terminate()
            web_proc.wait(timeout=5)
        except Exception:
            pass
    if tunnel_proc:
        try:
            tunnel_proc.terminate()
            tunnel_proc.wait(timeout=5)
        except Exception:
            pass

    session_name = sess[:-8]
    api = load_saved_api_for_session(sess)
    if api:
        api_id, api_hash = api
        print(f"Using saved API for session {session_name}")
    else:
        print("Saved API not found. Please provide API credentials.")
        api_id = input("API ID: ")
        api_hash = input("API HASH: ")
        temp_api_path = f"{session_name}_api_temp.json"
        with open(temp_api_path, "w") as f:
            json.dump({"api_id": api_id, "api_hash": api_hash}, f)

    _convert_pyrogram_to_telethon(session_name)

    client = TelegramClient(session_name, api_id, api_hash)
    temp_api_path = f"{session_name}_api_temp.json"
    need_to_save_api = os.path.exists(temp_api_path)

    # protection policy из единого конфига (до start(), иначе 2FA не войдёт)
    # На этом этапе аккаунт ещё не авторизован — смотрим конфиг по сессии.
    try:
        _uid = _user_id_from_session(session_name)
    except Exception:
        _uid = 0
    nova_config.apply_to_client(client, nova_config.load(_uid))

    client.commands = {}
    client.loaded_modules = set()

    client.add_event_handler(handler, events.NewMessage(outgoing=True))
    client.add_event_handler(owner_handler, events.NewMessage(incoming=True))
    client.add_event_handler(edited_handler, events.MessageEdited(outgoing=True))

    await client.start()

    if need_to_save_api:
        me = await client.get_me()
        user_id = me.id
        final_api_path = f"telegram_api-{user_id}.json"
        os.rename(temp_api_path, final_api_path)
        print(f"API credentials saved to {final_api_path}")

    client.start_time = time.time()

    kernel = Kernel()
    kernel.bind_client(client)

    # Единая база: постоянный aiosqlite-коннект + миграция nova_config.db.
    try:
        from core import database as db
        await db.ensure_started()
        client.db = db
    except Exception as e:
        print(f"[!] База данных недоступна: {e}")

    kernel.version = FORELKA_VERSION
    client.kernel = kernel

    client.commands = load_modules_with_config(client, kernel)

    try:
        from core.loader import register_loader_commands
        register_loader_commands(client)
        if "loader" not in client.loaded_modules:
            client.loaded_modules.add("loader")
        print("[+] Команды loader.py зарегистрированы")
    except ImportError:
        print("[!] loader.py не найден — команды .dlm .lm и т.д. недоступны")
    except Exception as e:
        print(f"[!] Ошибка при регистрации loader: {e}")

    # === ИСПРАВЛЕННЫЙ ПОРЯДОК ВЫЗОВОВ ===
    # 1. Сначала создаём management группу (без бота)
    await setup_management_group(kernel)
    
    # 2. Запускаем инлайн-бота
    await kernel.setup_inline_bot()
    
    # 3. Добавляем бота в management группу (теперь бот уже запущен)
    await add_bot_to_management_group(kernel)

    git = "unknown"
    try:
        git = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except:
        pass

    me = await client.get_me()
    name = f"{me.first_name or ''} {me.last_name or ''}".strip()
    modules_count = len(getattr(client, 'loaded_modules', set()))

    print(fr"""
  _   _                   
 | \ | |                  
 |  \| | _____   ___ _ __ 
 | . ` |/ _ \ \ / / | '__|
 | |\  | (_) \ V /| | |   
 \_| \_/\___/ \_/ |_| |_|

NovaUB v{FORELKA_VERSION} | Git: #{git}
""")

    # Отправляем уведомление о старте в "Логи"
    start_text = (
        f"<tg-emoji emoji-id=5897962422169243693>👻</tg-emoji> <b>NovaUB Started</b>\n\n"
        f"<blockquote><b>Version:</b> <code>{FORELKA_VERSION}</code>\n"
        f"<b>Git:</b> <code>#{git}</code>\n"
        f"<b>Python:</b> <code>{sys.version.split()[0]}</code>\n"
        f"<b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code></blockquote>\n"
        f"<blockquote><b>Account:</b> {name} [<code>{me.id}</code>]</blockquote>\n"
        f"<blockquote><b>Modules:</b> <code>{modules_count}</code></blockquote>"
    )
    if hasattr(client, 'kernel') and client.kernel:
        try:
            await client.kernel.send_to_topic("Логи", start_text)
        except:
            pass

    try:
        await client.run_until_disconnected()
    except asyncio.CancelledError:
        pass
    finally:
        uptime_sec = int(time.time() - client.start_time)
        hours, rem = divmod(uptime_sec, 3600)
        mins, secs = divmod(rem, 60)
        uptime_str = f"{hours}h {mins}m {secs}s"

        stop_text = (
            f"<tg-emoji emoji-id=5897962422169243693>👻</tg-emoji> <b>NovaUB Stopped</b>\n\n"
            f"<blockquote><b>Version:</b> <code>{FORELKA_VERSION}</code>\n"
            f"<b>Uptime:</b> <code>{uptime_str}</code>\n"
            f"<b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code></blockquote>"
        )
        if hasattr(client, 'kernel') and client.kernel:
            try:
                await client.kernel.send_to_topic("Логи", stop_text)
            except:
                pass
            await kernel.stop()

if __name__ == "__main__":
    asyncio.run(main())