import os
import sys
import json
import logging
import asyncio
import aiosqlite
from pathlib import Path
from telethon import TelegramClient, functions
from telethon.tl.types import PeerChannel
from telethon.errors import SessionPasswordNeededError
from inline_bot import InlineBot

class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

class Kernel:
    def __init__(self):
        self.CONFIG_FILE = "kernel_config.json"
        self.config = self._load_config()
        self.logger = logging.getLogger("NovaUBKernel")
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.client = None
        self.inline_bot = None
        self.bot_command_handlers = {}
        self.inline_query_handlers = []
        self.callback_handlers = []
        self.inline_trigger_handlers = {}
        self.universal_message_handlers = []
        self.feedback_users = set()
        self.module_configs = {}

    def bind_client(self, client):
        """Привязывает клиент и переключает на per-account конфиг."""
        self.client = client
        # Единый конфиг аккаунта (config-<id>.json), с миграцией легаси-файлов.
        self.user_id = getattr(client, "_self_id", None)
        try:
            import config as nova_config
            self.config = nova_config.load(self.user_id) if self.user_id else self._load_config()
        except Exception:
            self.config = self._load_config()

    def _load_config(self):
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Ошибка загрузки конфигурации: {e}")
        return {}

    def save_config(self):
        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"Ошибка сохранения конфигурации: {e}")

    def get_api_credentials(self):
        api_id = self.config.get("api_id")
        api_hash = self.config.get("api_hash")
        if not api_id or not api_hash:
            print(f"{Colors.YELLOW}API ID и/или API HASH не найдены в конфигурации.{Colors.RESET}")
            api_id = input("Введите API ID: ")
            api_hash = input("Введите API HASH: ")
            self.config["api_id"] = int(api_id)
            self.config["api_hash"] = api_hash
            self.save_config()
            print(f"{Colors.GREEN}Учетные данные API сохранены в {self.CONFIG_FILE}{Colors.RESET}")
        return int(self.config["api_id"]), self.config["api_hash"]

    async def start_client(self, session_name: str):
        api_id, api_hash = self.get_api_credentials()
        self.client = TelegramClient(session_name, api_id, api_hash)
        await self.client.start()
        self.logger.info("Юзербот успешно запущен!")

    async def setup_inline_bot(self):
        self.inline_bot = InlineBot(self)
        await self.inline_bot.setup()

    def register_bot_command(self, command: str, handler):
        self.bot_command_handlers[command] = ("", handler)
        self.logger.debug(f"Зарегистрирована команда бота: /{command}")

    def register_inline_handler(self, handler):
        self.inline_query_handlers.append(handler)
        self.logger.debug("Зарегистрирован инлайн-обработчик")

    def register_callback_handler(self, handler):
        self.callback_handlers.append(handler)
        self.logger.debug("Зарегистрирован обработчик кнопок.")

    def register_inline_trigger(self, trigger_name: str, handler):
        self.inline_trigger_handlers[trigger_name] = handler
        self.logger.debug(f"Зарегистрирован инлайн-триггер: {trigger_name}")

    def register_universal_message_handler(self, handler):
        """Регистрирует обработчик для ВСЕХ сообщений к боту."""
        self.universal_message_handlers.append(handler)
        self.logger.debug("Зарегистрирован универсальный обработчик сообщений.")

    async def inline_query_and_click(self, chat_id, query):
        """Выполняет инлайн-запрос и отправляет первый результат."""
        if not self.inline_bot or not self.inline_bot.bot_client:
            raise ValueError("Инлайн-бот не запущен.")
        
        try:
            # Явно получаем entity бота
            bot_entity = await self.client.get_entity(self.inline_bot.username)
            chat_entity = await self.client.get_entity(chat_id)
            
            result = await self.client(
                functions.messages.GetInlineBotResultsRequest(
                    bot=bot_entity,
                    peer=chat_entity,
                    query=query,
                    offset=""
                )
            )
            
            if not result.results:
                raise ValueError("Бот не вернул результатов.")
            
            await self.client(
                functions.messages.SendInlineBotResultRequest(
                    peer=chat_entity,
                    query_id=result.query_id,
                    id=result.results[0].id
                )
            )
        except Exception as e:
            raise ValueError(f"Ошибка инлайн-запроса: {e}")

    async def send_to_topic(self, topic_name, text):
        """Отправляет сообщение в топик management-группы через бота."""
        try:
            if not self.inline_bot or not self.inline_bot.bot_client:
                return
            if not getattr(self, "user_id", None):
                return
            import config as nova_config
            config = nova_config.load(self.user_id)
            group_id = config.get("management_group_id")
            topics = config.get("management_topics") or {}
            topic_id = topics.get(topic_name)
            if not group_id or not topic_id:
                return
            # Бот не может резолвить отрицательный ID — используем PeerChannel
            channel_id = -group_id if group_id < 0 else group_id
            entity = PeerChannel(channel_id)
            await self.inline_bot.bot_client.send_message(
                entity=entity,
                message=text,
                parse_mode='html',
                reply_to=topic_id
            )
        except Exception:
            pass  # Логирование не должно ломать бота

    async def get_module_config(self, module_name):
        """Получает конфигурацию модуля из SQLite (единый db-слой)."""
        try:
            import database as db
            return await db.get_module_config(module_name)
        except Exception:
            return {}

    async def handle_error(self, exception, source="", event=None):
        self.logger.error(f"Ошибка в {source}: {exception}", exc_info=True)
        if event and hasattr(event, 'respond'):
            await event.respond(f"Произошла ошибка: {str(exception)}")

    async def stop(self):
        if self.inline_bot:
            await self.inline_bot.stop_bot()
        if self.client and self.client.is_connected():
            await self.client.disconnect()
        self.logger.info("Приложение остановлено.")