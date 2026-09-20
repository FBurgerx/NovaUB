import asyncio
import aiohttp
import json
import os
import re
import sys
from telethon import TelegramClient, events, Button

class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

class InlineBot:
    def __init__(self, kernel):
        self.kernel = kernel
        self.bot_client = None
        self.token = None
        self.username = None

    async def setup(self):
        self.token = self.kernel.config.get("inline_bot_token")
        self.username = self.kernel.config.get("inline_bot_username")

        if not self.token:
            await self.create_bot()
        else:
            await self.start_bot()

    async def create_bot(self):
        self.kernel.logger.info("Настройка инлайн-бота")

        choice = input(
            f"{Colors.YELLOW}1. Автоматически создать бота\n2. Ввести токен вручную\nВыберите (1/2): {Colors.RESET}"
        ).strip()
        
        if choice == "1":
            await self.auto_create_bot()
        elif choice == "2":
            await self.manual_setup()
        else:
            self.kernel.logger.error("Неверный выбор при создании бота")
            return

    async def auto_create_bot(self):
        try:
            botfather = await self.kernel.client.get_entity("BotFather")

            while True:
                username = input(
                    f"{Colors.YELLOW}Желаемый username для бота (без @): {Colors.RESET}"
                ).strip()

                if not username:
                    print(f"{Colors.RED}=X Username не может быть пустым{Colors.RESET}")
                    continue

                if not username.endswith(('bot', '_bot', 'Bot', '_Bot')):
                    username += '_bot'
                    print(f"{Colors.YELLOW}=? Username автоматически изменен на: {username}{Colors.RESET}")

                if not re.match(r'^[a-zA-Z0-9_]{5,32}$', username):
                    self.kernel.logger.error(f"Некорректный формат username: {username}")
                    continue
                break

            async def wait_for_botfather_response(max_wait=30):
                start_time = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - start_time < max_wait:
                    messages = await self.kernel.client.get_messages(botfather, limit=3)
                    for msg in messages:
                        if hasattr(msg, "text") and msg.text:
                            yield msg
                    await asyncio.sleep(2)

            await self.kernel.client.send_message(botfather, "/newbot")
            await asyncio.sleep(2)
            await self.kernel.client.send_message(botfather, "🪄 NovaUB Inline Bot")
            await asyncio.sleep(2)
            await self.kernel.client.send_message(botfather, username)

            token = None
            bot_username = None

            async for msg in wait_for_botfather_response(15):
                text = msg.text
                token_match = re.search(r"(\d+:[A-Za-z0-9_-]+)", text)
                if token_match and "token" in text.lower():
                    token = token_match.group(1)

                username_match_tme = re.search(r"t\.me/([A-Za-z0-9_]+)", text)
                if username_match_tme:
                    bot_username = username_match_tme.group(1)

                if "error" in text.lower() or "invalid" in text.lower():
                    self.kernel.logger.error(f"BotFather вернул ошибку: {text[:100]}")
                    return

            if not bot_username:
                bot_username = username

            if token and bot_username:
                self.token = token
                self.username = bot_username
                self.kernel.logger.info(f"Получен токен для бота @{bot_username}")

                self.kernel.config["inline_bot_token"] = self.token
                self.kernel.config["inline_bot_username"] = self.username
                self.kernel.save_config()

                self.kernel.logger.info("Бот создан, настройка аватара...")
                
                # Настраиваем avatar через BotFather
                await self.kernel.client.send_message(botfather, "/setuserpic")
                await asyncio.sleep(5)
                await self.kernel.client.send_message(botfather, f"@{bot_username}")
                await asyncio.sleep(5)
                
                # Ищем аватар в папке assets
                avatar_paths = [
                    "assets/avatar_inline.jpg",
                    "assets/avatar_inline.png",
                    "assets/avatar.jpg",
                    "assets/avatar.png",
                ]
                
                avatar_path = None
                for path in avatar_paths:
                    if os.path.exists(path):
                        avatar_path = path
                        break
                
                if avatar_path:
                    await self.kernel.client.send_file(botfather, avatar_path)
                    self.kernel.logger.info(f"Аватар установлен из {avatar_path}")
                else:
                    self.kernel.logger.warning("Аватар не найден (assets/avatar_inline.jpg/png)")
                
                await asyncio.sleep(2)
                
                self.kernel.logger.info("Перезапуск для применения настроек...")
                os.execl(sys.executable, sys.executable, *sys.argv)
            else:
                self.kernel.logger.error("Не удалось получить данные бота из ответов BotFather")

        except Exception as e:
            self.kernel.logger.error(f"Ошибка создания бота: {str(e)}", exc_info=True)

    async def manual_setup(self):
        self.kernel.logger.info("Ручная настройка бота")

        while True:
            token = input(
                f"{Colors.YELLOW}Введите токен бота: {Colors.RESET}"
            ).strip()

            if not token:
                self.kernel.logger.error("Пустой токен при ручной настройке")
                continue

            username = input(
                f"{Colors.YELLOW}Введите username бота (без @): {Colors.RESET}"
            ).strip()

            if not username:
                self.kernel.logger.error("Пустой username при ручной настройке")
                continue

            if not re.match(r'^[a-zA-Z0-9_]{5,32}$', username):
                self.kernel.logger.error(f"Некорректный формат username: {username}")
                continue

            break

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.telegram.org/bot{token}/getMe") as resp:
                    data = await resp.json()

                    if data.get("ok"):
                        bot_info = data.get("result", {})
                        actual_username = bot_info.get("username", "")
                        if actual_username.lower() != username.lower():
                            self.kernel.logger.warning(f"Введенный username ({username}) не совпадает с фактическим ({actual_username})")
                            username = actual_username

                        self.token = token
                        self.username = username

                        self.kernel.config["inline_bot_token"] = token
                        self.kernel.config["inline_bot_username"] = username
                        self.kernel.save_config()

                        self.kernel.logger.info(f"Бот проверен и сохранен: @{username}")
                        await self.start_bot()
                    else:
                        error_desc = data.get("description", "Неизвестная ошибка")
                        self.kernel.logger.error(f"Неверный токен бота: {error_desc}")

        except Exception as e:
            self.kernel.logger.error(f"Ошибка проверки токена: {str(e)}", exc_info=True)

    async def _apply_registered_handlers(self):
        """Применяет все обработчики, зарегистрированные в ядре."""
        async def owner_check_middleware(event, original_handler):
            user_id = event.sender_id
            if not self._is_owner(user_id):
                await event.reply(
                    "<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> <b>Доступ запрещен.</b>\nЭта команда доступна только владельцам юзербота.</blockquote>",
                    parse_mode='html'
                )
                return
            await original_handler(event)

        for cmd, (old_pattern, handler) in self.kernel.bot_command_handlers.items():
            pattern = f'/{cmd}(@{self.username})?$'
            self.kernel.bot_command_handlers[cmd] = (pattern, handler)
            wrapped_handler = lambda ev, h=handler: owner_check_middleware(ev, h)
            self.bot_client.add_event_handler(wrapped_handler, events.NewMessage(pattern=pattern))

        for handler in self.kernel.inline_query_handlers:
            self.bot_client.add_event_handler(handler, events.InlineQuery)

        # === ГЛОБАЛЬНЫЙ ОБРАБОТЧИК С ПОДДЕРЖКОЙ ФИДБЕКА И ОТВЕТОВ ===
        @self.bot_client.on(events.NewMessage)
        async def global_message_handler(event):
            # --- 0. Проверка состояния ответа владельца ---
            if hasattr(event.client, 'feedback_reply_to'):
                from modules.feedback import owner_reply_handler
                await owner_reply_handler(event)
                return

            text = event.raw_text or ""
            user_id = event.sender_id
            kernel = self.kernel

            # --- 1. Проверка режима фидбека ---
            if user_id in kernel.feedback_users:
                # Игнорируем служебные сообщения и команды
                if not text.startswith('/') and not event.message.action and not event.message.out:
                    from modules.feedback import feedback_message_handler
                    await feedback_message_handler(event)
                    return
                # Если это команда /start, обрабатываем выход из режима
                if text.startswith('/start'):
                    pass # Продолжаем обработку как команду
                else:
                    return # Игнорируем другие команды в режиме фидбека

            # --- 2. Обработка команд ---
            if not text.startswith('/'):
                return

            command_match = re.match(r'^/(\w+)(@\w+)?$', text, re.IGNORECASE)
            if not command_match:
                return
                
            command = command_match.group(1).lower()
            
            # СПЕЦИАЛЬНО ДЛЯ /start и /feedback - УБИРАЕМ ПРОВЕРКУ ВЛАДЕЛЬЦА
            if command in ("start", "feedback"):
                if command in self.kernel.bot_command_handlers:
                    pattern, handler = self.kernel.bot_command_handlers[command]
                    await handler(event) # <-- Без проверки владельца
                elif command == "start":
                    await start_handler(event)
                return

            # Для остальных команд оставляем проверку владельца
            if command in self.kernel.bot_command_handlers:
                pattern, handler = self.kernel.bot_command_handlers[command]
                await owner_check_middleware(event, handler)

        @self.bot_client.on(events.CallbackQuery)
        async def global_callback_handler(event):
            try:
                if hasattr(self.kernel, 'callback_handlers'):
                    for handler in self.kernel.callback_handlers:
                        await handler(event)
            except Exception as e:
                self.kernel.logger.error(f"Ошибка в обработчике кнопки: {e}")
                await event.answer("Произошла ошибка.", alert=True)

        @self.bot_client.on(events.InlineQuery)
        async def universal_inline_handler(event):
            query_text = event.text.strip()
            if query_text.startswith("trigger_"):
                trigger_name = query_text[len("trigger_"):]
                handler = self.kernel.inline_trigger_handlers.get(trigger_name)
                if handler:
                    await handler(event)
                else:
                    await event.answer([])
            else:
                # Обработка обычных инлайн-запросов
                for handler in self.kernel.inline_query_handlers:
                    await handler(event)

        # === ОБРАБОТЧИК КНОПОК ФИДБЕКА ===
        @self.bot_client.on(events.CallbackQuery(data=re.compile(rb"fb_(reply|delete)_\d+")))
        async def feedback_callback_handler(event):
            try:
                kernel = self.kernel
                data = event.data.decode('utf-8')
                
                if data.startswith("fb_reply_"):
                    target_user_id = int(data.split("_")[2])
                    event.client.feedback_reply_to = target_user_id
                    await event.edit(
                        "<blockquote>✍️ Введите ваш ответ:</blockquote>",
                        parse_mode='html',
                        buttons=None
                    )
                elif data.startswith("fb_delete_"):
                    await event.delete()
            except Exception as e:
                await event.answer(f"Ошибка: {e}", alert=True)

        # === ПАГИНАЦИЯ ДЛЯ .ai ===
        @self.bot_client.on(events.CallbackQuery(data=re.compile(rb"ai_page_(\w+)_(\d+)")))
        async def ai_pagination_handler(event):
            data = event.data.decode('utf-8')
            parts = data.split('_')
            req_id = parts[2]
            page_num = int(parts[3])

            kernel = self.kernel
            if not hasattr(kernel, 'ai_pages') or req_id not in kernel.ai_pages:
                await event.answer("Страницы не найдены или устарели", alert=True)
                return

            pages = kernel.ai_pages[req_id]
            if page_num < 1 or page_num > len(pages):
                await event.answer("Неверная страница", alert=True)
                return

            page_text = pages[page_num - 1]
            escaped = html.escape(page_text)

            # Кнопки пагинации
            row1 = [Button.inline(str(i+1), data=f"ai_page_{req_id}_{i+1}") for i in range(min(5, len(pages)))]
            row2 = [Button.inline(str(i+1), data=f"ai_page_{req_id}_{i+1}") for i in range(5, min(10, len(pages)))]
            buttons = [row1] if not row2 else [row1, row2]

            await event.edit(
                f"<blockquote expandable>"
                f"<b>Ответ ({MODEL}) [страница {page_num}/{len(pages)}]:</b>\n"
                f"<code>{escaped}</code>"
                f"</blockquote>",
                parse_mode='html',
                buttons=buttons
            )

        # === ОБРАБОТЧИКИ /START И КНОПОК ===
        @self.bot_client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            buttons = [
                [
                    Button.url("📦 Официальный репозиторий", "https://github.com/your-repo"),
                    Button.url("👥 Группа поддержки", "https://t.me/your_support_chat")
                ],
                [
                    Button.inline("🤖 Команды бота", data="show_bot_commands")
                ]
            ]

            await event.reply(
                "<blockquote><tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Привет!</b>\n"
                "Это юзербот <b>NovaUB</b>!\n"
                "Спасибо за твой выбор!\n\n"
                "Ниже ты можешь ознакомиться с нашими разделами, "
                "а также вступить в группу поддержки юзербота.</blockquote>",
                buttons=buttons,
                parse_mode='html'
            )

        @self.bot_client.on(events.CallbackQuery(data=b"show_bot_commands"))
        async def show_commands_handler(event):
            commands_text = (
                "<blockquote><b>🤖 Команды инлайн-бота:</b>\n\n"
                "<b>/calc</b> - Калькулятор\n"
                "<b>/ping</b> - Проверка активности\n"
                "</blockquote>"
            )
            await event.edit(commands_text, parse_mode='html')

        self.kernel.logger.info(f"Применено {len(self.kernel.bot_command_handlers)} команд, "
                                f"{len(self.kernel.inline_query_handlers)} инлайн-обработчиков, "
                                f"{len(self.kernel.inline_trigger_handlers)} триггеров.")

    def _is_owner(self, user_id):
        """Проверяет, является ли пользователь владельцем."""
        config_path = f"config-{self.kernel.client._self_id}.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    owners = config.get("owners", [])
                    if self.kernel.client._self_id not in owners:
                        owners.append(self.kernel.client._self_id)
                    return user_id in owners
            except:
                pass
        return user_id == self.kernel.client._self_id

    async def start_bot(self):
        if not self.token:
            self.kernel.logger.error("Токен бота не указан")
            return

        try:
            self.kernel.logger.info("Запуск инлайн-бота...")

            api_id, api_hash = self.kernel.get_api_credentials()
            if not api_id or not api_hash:
                raise ValueError("API ID или Hash не найдены в конфигурации ядра.")

            self.bot_client = TelegramClient(
                "inline_bot_session",
                api_id,
                api_hash,
            )

            await self.bot_client.start(bot_token=self.token)
            me = await self.bot_client.get_me()
            self.username = me.username

            self.bot_client.kernel = self.kernel

            await self._apply_registered_handlers()

            self.kernel.logger.info(f"=> Инлайн-бот запущен @{self.username}")
            asyncio.create_task(self.bot_client.run_until_disconnected())

        except Exception as e:
            self.kernel.logger.error(f"Ошибка запуска инлайн-бота: {str(e)}", exc_info=True)

    async def stop_bot(self):
        if self.bot_client and self.bot_client.is_connected():
            await self.bot_client.disconnect()
            self.kernel.logger.info("Инлайн-бот остановлен")