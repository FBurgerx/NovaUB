#!/usr/bin/env python3
"""
NovaUB CLI - Интерактивная консоль управления
Запуск: python cli.py
"""

import os
import sys
import json
import time
import zipfile
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


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

# ────────────────────────────────────────────────
# Цвета для терминала
# ────────────────────────────────────────────────
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"

# ────────────────────────────────────────────────
# Утилиты
# ────────────────────────────────────────────────
def clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')

def print_header(title, subtitle=""):
    width = 62
    print(f"\n{Colors.CYAN}╔{'═' * width}╗{Colors.RESET}")
    print(f"{Colors.CYAN}║{Colors.WHITE} {title.center(width - 2)} {Colors.CYAN}║{Colors.RESET}")
    if subtitle:
        print(f"{Colors.CYAN}║{Colors.WHITE} {subtitle.center(width - 2)} {Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.CYAN}╚{'═' * width}╝{Colors.RESET}")

def print_box(title, lines):
    width = 62
    print(f"{Colors.BLUE}┌{'─' * (width - 2)}┐{Colors.RESET}")
    print(f"{Colors.BLUE}│{Colors.WHITE} {title.ljust(width - 3)} {Colors.BLUE}│{Colors.RESET}")
    print(f"{Colors.BLUE}├{'─' * (width - 2)}┤{Colors.RESET}")
    for line in lines:
        print(f"{Colors.BLUE}│{Colors.WHITE} {line.ljust(width - 3)} {Colors.BLUE}│{Colors.RESET}")
    print(f"{Colors.BLUE}└{'─' * (width - 2)}┘{Colors.RESET}")

def print_table(headers, rows):
    if not rows:
        print(f"{Colors.YELLOW}  Нет данных{Colors.RESET}")
        return
    
    # Вычисляем ширину колонок
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Печатаем заголовок
    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator = "─" * len(header_line)
    print(f"  {Colors.CYAN}{separator}{Colors.RESET}")
    print(f"  {Colors.BOLD}{header_line}{Colors.RESET}")
    print(f"  {Colors.CYAN}{separator}{Colors.RESET}")
    
    # Печатаем строки
    for row in rows:
        row_line = "  ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        print(f"  {row_line}")
    
    print(f"  {Colors.CYAN}{separator}{Colors.RESET}")

def get_input(prompt="> "):
    try:
        return input(f"{Colors.GREEN}{prompt}{Colors.RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{Colors.YELLOW}Выход...{Colors.RESET}")
        sys.exit(0)

def get_choice(options, prompt="Выберите пункт"):
    while True:
        choice = get_input(f"{prompt}: ")
        if choice in options:
            return choice
        print(f"{Colors.RED}Неверный выбор. Доступные варианты: {', '.join(options)}{Colors.RESET}")

def load_json_file(filepath, default=None):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def save_json_file(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"{Colors.RED}Ошибка записи: {e}{Colors.RESET}")
        return False

def get_user_id():
    """Получаем ID первого найденного аккаунта"""
    for f in os.listdir('.'):
        if f.startswith("nova-") and f.endswith('.session'):
            try:
                return int(f[8:-8])
            except:
                pass
    return None

def get_config(user_id):
    return load_json_file(f"config-{user_id}.json", {})

def get_kernel_config(user_id):
    return load_json_file(f"kernel_config-{user_id}.json", {})

def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"

# ────────────────────────────────────────────────
# Главное меню
# ────────────────────────────────────────────────
def main_menu(user_id):
    while True:
        clear_screen()
        config = get_config(user_id)
        kernel_config = get_kernel_config(user_id)
        
        # Получаем информацию об аккаунте
        status = "🟢 Работает"  # Предполагаем, что работает
        uptime = "N/A"
        
        print_header("🤖 NovaUB CLI Panel", "v1.0.0")
        print()
        print(f"  {Colors.BOLD}Аккаунт:{Colors.RESET} User [{user_id}]")
        print(f"  {Colors.BOLD}Статус:{Colors.RESET} {status}")
        print(f"  {Colors.BOLD}Бот:{Colors.RESET} @{kernel_config.get('inline_bot_username', 'N/A')}")
        print()
        
        menu_items = [
            ("1", "📊", "Статус бота"),
            ("2", "📦", "Модули"),
            ("3", "⚙️", "Конфигурация"),
            ("4", "📋", "Логи"),
            ("5", "💾", "Бекапы"),
            ("6", "👥", "Овнеры"),
            ("7", "🔄", "Управление"),
            ("8", "🏥", "Диагностика"),
            ("9", "⚡", "Выполнение команд"),
            ("0", "🚪", "Выход"),
        ]
        
        for key, emoji, name in menu_items:
            print(f"  {Colors.GREEN}{key}){Colors.RESET} {emoji} {name}")
        
        print()
        choice = get_choice([str(i) for i in range(10)])
        
        if choice == "1":
            status_menu(user_id)
        elif choice == "2":
            modules_menu(user_id)
        elif choice == "3":
            config_menu(user_id)
        elif choice == "4":
            logs_menu(user_id)
        elif choice == "5":
            backup_menu(user_id)
        elif choice == "6":
            owners_menu(user_id)
        elif choice == "7":
            control_menu(user_id)
        elif choice == "8":
            diagnostics_menu(user_id)
        elif choice == "9":
            execute_command_menu(user_id)
        elif choice == "0":
            print(f"\n{Colors.CYAN}👋 Goodbye! Юзербот продолжает работать в фоне.{Colors.RESET}")
            print(f"  {Colors.YELLOW}Для остановки выполните: python cli.py stop{Colors.RESET}\n")
            sys.exit(0)

# ────────────────────────────────────────────────
# 1. Статус бота
# ────────────────────────────────────────────────
def status_menu(user_id):
    while True:
        clear_screen()
        print_header("📊 Статус бота")
        print()
        
        config = get_config(user_id)
        kernel_config = get_kernel_config(user_id)
        
        # Считаем модули
        modules_count = 0
        for folder in ['modules', 'loaded_modules']:
            if os.path.exists(folder):
                modules_count += len([f for f in os.listdir(folder) if f.endswith('.py') and f != '__init__.py'])
        
        # Считаем команды
        commands_count = len(config.get('aliases', {})) + 15  # Примерно
        
        # Информация о хранилище
        total_size = 0
        file_count = 0
        for root, dirs, files in os.walk('.'):
            if '__pycache__' in root:
                continue
            for f in files:
                if not f.endswith(('.session', '.session-journal', '.pyc')):
                    try:
                        total_size += os.path.getsize(os.path.join(root, f))
                        file_count += 1
                    except:
                        pass
        
        lines = [
            f"{Colors.BOLD}Account:{Colors.RESET} User [{user_id}]",
            f"{Colors.BOLD}User ID:{Colors.RESET} {user_id}",
            f"{Colors.BOLD}Status:{Colors.RESET} 🟢 Running",
            f"{Colors.BOLD}Inline Bot:{Colors.RESET} @{kernel_config.get('inline_bot_username', 'N/A')}",
            "",
            f"{Colors.BOLD}Modules:{Colors.RESET} {modules_count} loaded",
            f"{Colors.BOLD}Commands:{Colors.RESET} ~{commands_count} registered",
            f"{Colors.BOLD}Aliases:{Colors.RESET} {len(config.get('aliases', {}))}",
            "",
            f"{Colors.BOLD}Files:{Colors.RESET} {file_count}",
            f"{Colors.BOLD}Storage:{Colors.RESET} {format_size(total_size)}",
            "",
            f"{Colors.BOLD}Management Group:{Colors.RESET} {config.get('management_group_id', 'N/A')}",
            f"{Colors.BOLD}Topics:{Colors.RESET} {len(config.get('management_topics', {}))}",
        ]
        
        print_box("Информация", lines)
        print()
        
        print(f"  {Colors.GREEN}1){Colors.RESET} Обновить")
        print(f"  {Colors.GREEN}2){Colors.RESET} Подробная информация")
        print(f"  {Colors.GREEN}0){Colors.RESET} Назад")
        print()
        
        choice = get_choice(["0", "1", "2"])
        
        if choice == "1":
            continue
        elif choice == "2":
            detailed_status(user_id)
        elif choice == "0":
            return

def get_version():
    """Загружает версию из файла version.txt"""
    try:
        with open('version.txt', 'r') as f:
            return f.read().strip()
    except:
        return "1.0.0"

def detailed_status(user_id):
    clear_screen()
    print_header("📊 Подробная информация")
    print()
    
    # Версия Python
    import platform
    python_version = platform.python_version()
    
    # Версия NovaUB
    novaub_version = get_version()
    
    # Git информация
    git_info = "N/A"
    try:
        import subprocess
        git_info = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], 
                                          stderr=subprocess.DEVNULL).decode().strip()
        git_info = f"#{git_info}"
    except:
        pass
    
    lines = [
        f"{Colors.BOLD}NovaUB Version:{Colors.RESET} {novaub_version}",
        f"{Colors.BOLD}Git Commit:{Colors.RESET} {git_info}",
        f"{Colors.BOLD}Python Version:{Colors.RESET} {python_version}",
        f"{Colors.BOLD}Platform:{Colors.RESET} {platform.system()} {platform.release()}",
        "",
        f"{Colors.BOLD}Config File:{Colors.RESET} config-{user_id}.json",
        f"{Colors.BOLD}Kernel Config:{Colors.RESET} kernel_config-{user_id}.json",
        f"{Colors.BOLD}Database:{Colors.RESET} novaub.db",
        "",
        f"{Colors.BOLD}Session Files:{Colors.RESET}",
    ]
    
    # Список сессий
    sessions = [f for f in os.listdir('.') if f.endswith('.session')]
    for s in sessions:
        lines.append(f"    📁 {s}")
    
    print_box("Системная информация", lines)
    print()
    get_input("Нажмите Enter для возврата... ")

# ────────────────────────────────────────────────
# 2. Модули
# ────────────────────────────────────────────────
def modules_menu(user_id):
    while True:
        clear_screen()
        print_header("📦 Управление модулями")
        print()
        
        # Системные модули
        sys_modules = []
        if os.path.exists('modules'):
            for f in os.listdir('modules'):
                if f.endswith('.py') and f != '__init__.py':
                    sys_modules.append(f[:-3])
        
        # Пользовательские модули
        user_modules = []
        if os.path.exists('loaded_modules'):
            for f in os.listdir('loaded_modules'):
                if f.endswith('.py') and f != '__init__.py':
                    user_modules.append(f[:-3])
        
        print(f"  {Colors.BOLD}System Modules ({len(sys_modules)}):{Colors.RESET}")
        for m in sorted(sys_modules):
            print(f"    {Colors.GREEN}✅{Colors.RESET} {m}")
        print()
        
        print(f"  {Colors.BOLD}External Modules ({len(user_modules)}):{Colors.RESET}")
        for m in sorted(user_modules):
            print(f"    {Colors.GREEN}✅{Colors.RESET} {m}")
        print()
        
        print(f"  {Colors.GREEN}1){Colors.RESET} Загрузить модуль из файла")
        print(f"  {Colors.GREEN}2){Colors.RESET} Выгрузить модуль")
        print(f"  {Colors.GREEN}3){Colors.RESET} Скачать из репозитория")
        print(f"  {Colors.GREEN}4){Colors.RESET} Информация о модуле")
        print(f"  {Colors.GREEN}5){Colors.RESET} Список репозиториев")
        print(f"  {Colors.GREEN}0){Colors.RESET} Назад")
        print()
        
        choice = get_choice(["0", "1", "2", "3", "4", "5"])
        
        if choice == "1":
            load_module_cli()
        elif choice == "2":
            unload_module_cli()
        elif choice == "3":
            download_module_cli()
        elif choice == "4":
            module_info_cli()
        elif choice == "5":
            show_repos_cli()
        elif choice == "0":
            return

def load_module_cli():
    print(f"\n{Colors.YELLOW}Введите путь к файлу модуля:{Colors.RESET}")
    path = get_input("> ")
    if not os.path.exists(path):
        print(f"{Colors.RED}Файл не найден: {path}{Colors.RESET}")
        get_input("Нажмите Enter... ")
        return
    
    # Копируем модуль в loaded_modules
    module_name = os.path.basename(path)
    if not module_name.endswith('.py'):
        print(f"{Colors.RED}Файл должен быть .py{Colors.RESET}")
        get_input("Нажмите Enter... ")
        return
    
    dest_path = f"loaded_modules/{module_name}"
    
    # Проверяем, не защищённый ли это модуль
    protected = ['loader', 'main']
    if module_name[:-3] in protected:
        print(f"{Colors.RED}Нельзя загрузить системный модуль: {module_name[:-3]}{Colors.RESET}")
        get_input("Нажмите Enter... ")
        return
    
    try:
        shutil.copy2(path, dest_path)
        print(f"{Colors.GREEN}✅ Модуль загружен: {dest_path}{Colors.RESET}")
        print(f"  {Colors.CYAN}Перезапустите бота для применения.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}Ошибка загрузки: {e}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def unload_module_cli():
    print(f"\n{Colors.YELLOW}Введите имя модуля:{Colors.RESET}")
    name = get_input("> ")
    
    protected = ['loader', 'main']
    if name in protected:
        print(f"{Colors.RED}Нельзя удалить системный модуль: {name}{Colors.RESET}")
        get_input("Нажмите Enter... ")
        return
    
    for folder in ['loaded_modules', 'modules']:
        path = f"{folder}/{name}.py"
        if os.path.exists(path):
            os.remove(path)
            print(f"{Colors.GREEN}Модуль {name} удалён из {folder}{Colors.RESET}")
            get_input("Нажмите Enter... ")
            return
    
    print(f"{Colors.RED}Модуль не найден: {name}{Colors.RESET}")
    get_input("Нажмите Enter... ")

def download_module_cli():
    print(f"\n{Colors.YELLOW}Введите имя модуля или URL:{Colors.RESET}")
    name_or_url = get_input("> ")
    print(f"{Colors.CYAN}Для загрузки используйте команду .dlm {name_or_url} в Telegram{Colors.RESET}")
    get_input("Нажмите Enter... ")

def module_info_cli():
    print(f"\n{Colors.YELLOW}Введите имя модуля:{Colors.RESET}")
    name = get_input("> ")
    
    for folder in ['modules', 'loaded_modules']:
        path = f"{folder}/{name}.py"
        if os.path.exists(path):
            print(f"\n{Colors.BOLD}Информация о модуле {name}:{Colors.RESET}")
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Ищем __meta__
            if '__meta__' in content:
                print(f"  {Colors.GREEN}✅{Colors.RESET} Имеет метаданные")
            if '__requires__' in content:
                print(f"  {Colors.GREEN}✅{Colors.RESET} Имеет зависимости")
            if 'register' in content:
                print(f"  {Colors.GREEN}✅{Colors.RESET} Имеет функцию register")
            
            print(f"\n  {Colors.BOLD}Путь:{Colors.RESET} {path}")
            print(f"  {Colors.BOLD}Размер:{Colors.RESET} {os.path.getsize(path)} bytes")
            get_input("Нажмите Enter... ")
            return
    
    print(f"{Colors.RED}Модуль не найден: {name}{Colors.RESET}")
    get_input("Нажмите Enter... ")

def show_repos_cli():
    repos = load_json_file('repos.json', [])
    print(f"\n{Colors.BOLD}Репозитории модулей:{Colors.RESET}")
    if repos:
        for i, repo in enumerate(repos, 1):
            print(f"  {i}. {repo}")
    else:
        print(f"  {Colors.YELLOW}Нет добавленных репозиториев{Colors.RESET}")
    print()
    get_input("Нажмите Enter... ")

# ────────────────────────────────────────────────
# 3. Конфигурация
# ────────────────────────────────────────────────
def config_menu(user_id):
    while True:
        clear_screen()
        print_header("⚙️ Конфигурация")
        print()
        
        config = get_config(user_id)
        
        lines = [
            f"{Colors.BOLD}Prefix:{Colors.RESET} {config.get('prefix', '.')}",
            f"{Colors.BOLD}Owners:{Colors.RESET} {config.get('owners', [])}",
            f"{Colors.BOLD}Aliases:{Colors.RESET} {config.get('aliases', {})}",
            f"{Colors.BOLD}Management Group:{Colors.RESET} {config.get('management_group_id', 'N/A')}",
            "",
            f"{Colors.BOLD}Topics:{Colors.RESET}",
        ]
        
        topics = config.get('management_topics', {})
        for topic, topic_id in topics.items():
            lines.append(f"    • {topic}: {topic_id}")
        
        print_box(f"config-{user_id}.json", lines)
        print()
        
        print(f"  {Colors.GREEN}1){Colors.RESET} Изменить префикс")
        print(f"  {Colors.GREEN}2){Colors.RESET} Добавить овнера")
        print(f"  {Colors.GREEN}3){Colors.RESET} Удалить овнера")
        print(f"  {Colors.GREEN}4){Colors.RESET} Создать алиас")
        print(f"  {Colors.GREEN}5){Colors.RESET} Удалить алиас")
        print(f"  {Colors.GREEN}6){Colors.RESET} Экспорт конфига")
        print(f"  {Colors.GREEN}7){Colors.RESET} Импорт конфига")
        print(f"  {Colors.GREEN}0){Colors.RESET} Назад")
        print()
        
        choice = get_choice(["0", "1", "2", "3", "4", "5", "6", "7"])
        
        if choice == "1":
            change_prefix(user_id)
        elif choice == "2":
            add_owner(user_id)
        elif choice == "3":
            remove_owner(user_id)
        elif choice == "4":
            create_alias(user_id)
        elif choice == "5":
            delete_alias(user_id)
        elif choice == "6":
            export_config(user_id)
        elif choice == "7":
            import_config(user_id)
        elif choice == "0":
            return

def change_prefix(user_id):
    print(f"\n{Colors.YELLOW}Текущий префикс: {get_config(user_id).get('prefix', '.')}{Colors.RESET}")
    print(f"{Colors.YELLOW}Введите новый префикс:{Colors.RESET}")
    new_prefix = get_input("> ")
    
    config = get_config(user_id)
    config['prefix'] = new_prefix
    
    if save_json_file(f"config-{user_id}.json", config):
        print(f"{Colors.GREEN}Префикс изменён: . → {new_prefix}{Colors.RESET}")
    get_input("Нажмите Enter... ")

def add_owner(user_id):
    print(f"\n{Colors.YELLOW}Введите ID пользователя:{Colors.RESET}")
    try:
        owner_id = int(get_input("> "))
    except ValueError:
        print(f"{Colors.RED}Неверный ID{Colors.RESET}")
        get_input("Нажмите Enter... ")
        return
    
    config = get_config(user_id)
    owners = config.get('owners', [])
    
    if owner_id in owners:
        print(f"{Colors.YELLOW}Пользователь уже является овнером{Colors.RESET}")
    else:
        owners.append(owner_id)
        config['owners'] = owners
        if save_json_file(f"config-{user_id}.json", config):
            print(f"{Colors.GREEN}Овнер добавлен: {owner_id}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def remove_owner(user_id):
    config = get_config(user_id)
    owners = config.get('owners', [])
    
    print(f"\n{Colors.BOLD}Текущие овнеры:{Colors.RESET}")
    for i, o in enumerate(owners, 1):
        marker = " (вы)" if o == user_id else ""
        print(f"  {i}. {o}{marker}")
    print()
    
    print(f"{Colors.YELLOW}Введите номер для удаления:{Colors.RESET}")
    try:
        idx = int(get_input("> ")) - 1
        if 0 <= idx < len(owners):
            if owners[idx] == user_id:
                print(f"{Colors.RED}Нельзя удалить себя!{Colors.RESET}")
            else:
                owners.pop(idx)
                config['owners'] = owners
                if save_json_file(f"config-{user_id}.json", config):
                    print(f"{Colors.GREEN}Овнер удалён{Colors.RESET}")
        else:
            print(f"{Colors.RED}Неверный номер{Colors.RESET}")
    except ValueError:
        print(f"{Colors.RED}Неверный ввод{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def create_alias(user_id):
    print(f"\n{Colors.YELLOW}Введите алиас (короткое имя):{Colors.RESET}")
    alias = get_input("> ")
    print(f"{Colors.YELLOW}Введите команду (полное имя):{Colors.RESET}")
    command = get_input("> ")
    
    config = get_config(user_id)
    if 'aliases' not in config:
        config['aliases'] = {}
    
    config['aliases'][alias] = command
    
    if save_json_file(f"config-{user_id}.json", config):
        print(f"{Colors.GREEN}Алиас создан: .{alias} → .{command}{Colors.RESET}")
    get_input("Нажмите Enter... ")

def delete_alias(user_id):
    config = get_config(user_id)
    aliases = config.get('aliases', {})
    
    print(f"\n{Colors.BOLD}Текущие алиасы:{Colors.RESET}")
    for alias, command in aliases.items():
        print(f"  .{alias} → .{command}")
    print()
    
    print(f"{Colors.YELLOW}Введите алиас для удаления:{Colors.RESET}")
    alias = get_input("> ")
    
    if alias in aliases:
        del aliases[alias]
        config['aliases'] = aliases
        if save_json_file(f"config-{user_id}.json", config):
            print(f"{Colors.GREEN}Алиас удалён: .{alias}{Colors.RESET}")
    else:
        print(f"{Colors.RED}Алиас не найден{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def export_config(user_id):
    config = get_config(user_id)
    export_path = f"config-{user_id}_export.json"
    
    if save_json_file(export_path, config):
        print(f"{Colors.GREEN}Конфиг экспортирован: {export_path}{Colors.RESET}")
    get_input("Нажмите Enter... ")

def import_config(user_id):
    print(f"\n{Colors.YELLOW}Введите путь к файлу конфига:{Colors.RESET}")
    path = get_input("> ")
    
    if not os.path.exists(path):
        print(f"{Colors.RED}Файл не найден{Colors.RESET}")
        get_input("Нажмите Enter... ")
        return
    
    config = load_json_file(path)
    if config and save_json_file(f"config-{user_id}.json", config):
        print(f"{Colors.GREEN}Конфиг импортирован. Перезапустите бота.{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

# ────────────────────────────────────────────────
# 4. Логи
# ────────────────────────────────────────────────
def logs_menu(user_id):
    while True:
        clear_screen()
        print_header("📋 Логи")
        print()
        
        log_file = "novaub.log"
        
        if not os.path.exists(log_file):
            print(f"{Colors.YELLOW}Файл логов не найден: {log_file}{Colors.RESET}")
            print()
            get_input("Нажмите Enter... ")
            return
        
        # Читаем последние 20 строк
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                last_lines = lines[-20:] if len(lines) > 20 else lines
        except Exception as e:
            print(f"{Colors.RED}Ошибка чтения: {e}{Colors.RESET}")
            get_input("Нажмите Enter... ")
            return
        
        print(f"  {Colors.BOLD}Последние {len(last_lines)} строк:{Colors.RESET}\n")
        for line in last_lines:
            line = line.strip()
            if 'ERROR' in line:
                print(f"  {Colors.RED}{line}{Colors.RESET}")
            elif 'WARN' in line:
                print(f"  {Colors.YELLOW}{line}{Colors.RESET}")
            elif 'INFO' in line:
                print(f"  {Colors.GREEN}{line}{Colors.RESET}")
            else:
                print(f"  {Colors.WHITE}{line}{Colors.RESET}")
        
        print()
        print(f"  {Colors.GREEN}1){Colors.RESET} Обновить")
        print(f"  {Colors.GREEN}2){Colors.RESET} Показать больше (50)")
        print(f"  {Colors.GREEN}3){Colors.RESET} Только ошибки")
        print(f"  {Colors.GREEN}4){Colors.RESET} Поиск по логам")
        print(f"  {Colors.GREEN}5){Colors.RESET} Очистить логи")
        print(f"  {Colors.GREEN}0){Colors.RESET} Назад")
        print()
        
        choice = get_choice(["0", "1", "2", "3", "4", "5"])
        
        if choice == "1":
            continue
        elif choice == "2":
            show_more_logs(50)
        elif choice == "3":
            show_error_logs()
        elif choice == "4":
            search_logs()
        elif choice == "5":
            clear_logs()
        elif choice == "0":
            return

def show_more_logs(n=50):
    log_file = "novaub.log"
    if not os.path.exists(log_file):
        return
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            last_lines = lines[-n:] if len(lines) > n else lines
        
        print(f"\n{Colors.BOLD}Последние {len(last_lines)} строк:{Colors.RESET}\n")
        for line in last_lines:
            print(f"  {line.strip()}")
    except Exception as e:
        print(f"{Colors.RED}Ошибка: {e}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def show_error_logs():
    log_file = "novaub.log"
    if not os.path.exists(log_file):
        return
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            error_lines = [l for l in lines if 'ERROR' in l or 'WARN' in l]
        
        print(f"\n{Colors.BOLD}Ошибки и предупреждения:{Colors.RESET}\n")
        for line in error_lines[-30:]:
            print(f"  {Colors.RED if 'ERROR' in line else Colors.YELLOW}{line.strip()}{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}Ошибка: {e}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def search_logs():
    print(f"\n{Colors.YELLOW}Введите текст для поиска:{Colors.RESET}")
    pattern = get_input("> ")
    
    log_file = "novaub.log"
    if not os.path.exists(log_file):
        return
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            matched = [l for l in lines if pattern.lower() in l.lower()]
        
        print(f"\n{Colors.BOLD}Найдено совпадений: {len(matched)}{Colors.RESET}\n")
        for line in matched[-20:]:
            print(f"  {line.strip()}")
    except Exception as e:
        print(f"{Colors.RED}Ошибка: {e}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def clear_logs():
    print(f"\n{Colors.YELLOW}Вы уверены? Это действие необратимо.{Colors.RESET}")
    print(f"  {Colors.GREEN}1){Colors.RESET} Да, очистить")
    print(f"  {Colors.GREEN}0){Colors.RESET} Отмена")
    
    choice = get_choice(["0", "1"])
    
    if choice == "1":
        try:
            with open("novaub.log", 'w') as f:
                pass
            print(f"{Colors.GREEN}Логи очищены{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}Ошибка: {e}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

# ────────────────────────────────────────────────
# 5. Бекапы
# ────────────────────────────────────────────────
def backup_menu(user_id):
    while True:
        clear_screen()
        print_header("💾 Бекапы")
        print()
        
        # Ищем файлы бекапов
        backups = [f for f in os.listdir('.') if f.startswith('novaub_backup_') and f.endswith('.zip')]
        
        if backups:
            print(f"  {Colors.BOLD}Доступные бекапы:{Colors.RESET}\n")
            for i, b in enumerate(sorted(backups, reverse=True)[:10], 1):
                size = os.path.getsize(b)
                print(f"  {i}. 📁 {b} ({format_size(size)})")
            print()
            print(f"  Всего: {len(backups)} бекапов")
        else:
            print(f"  {Colors.YELLOW}Нет доступных бекапов{Colors.RESET}\n")
        
        print()
        print(f"  {Colors.GREEN}1){Colors.RESET} Создать бекап")
        print(f"  {Colors.GREEN}2){Colors.RESET} Восстановить из бекапа")
        print(f"  {Colors.GREEN}3){Colors.RESET} Удалить бекап")
        print(f"  {Colors.GREEN}4){Colors.RESET} Открыть папку с бекапами")
        print(f"  {Colors.GREEN}0){Colors.RESET} Назад")
        print()
        
        choice = get_choice(["0", "1", "2", "3", "4"])
        
        if choice == "1":
            create_backup_cli()
        elif choice == "2":
            restore_backup_cli()
        elif choice == "3":
            delete_backup_cli()
        elif choice == "4":
            print(f"\n{Colors.CYAN}Папка: /storage/emulated/0/forelka-userbot-telethon{Colors.RESET}")
            get_input("Нажмите Enter... ")
        elif choice == "0":
            return

def create_backup_cli():
    print(f"\n{Colors.CYAN}Создание бекапа...{Colors.RESET}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"novaub_backup_full_{timestamp}.zip"
    
    exclude_extensions = {'.pyc', '.pyo', '.session', '.session-journal'}
    exclude_dirs = {'__pycache__', '.git', '.idea', '.vscode'}
    
    files_added = 0
    total_size = 0
    
    try:
        with zipfile.ZipFile(backup_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk('.'):
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, '.')
                    
                    _, ext = os.path.splitext(file)
                    if ext.lower() in exclude_extensions:
                        continue
                    
                    try:
                        zipf.write(file_path, rel_path)
                        files_added += 1
                        total_size += os.path.getsize(file_path)
                    except:
                        pass
        
        archive_size = os.path.getsize(backup_filename)
        print(f"\n{Colors.GREEN}✅ Бекап создан: {backup_filename}{Colors.RESET}")
        print(f"  Файлов: {files_added}")
        print(f"  Размер: {format_size(archive_size)}")
    except Exception as e:
        print(f"{Colors.RED}Ошибка: {e}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def restore_backup_cli():
    backups = [f for f in os.listdir('.') if f.startswith('novaub_backup_') and f.endswith('.zip')]
    
    if not backups:
        print(f"\n{Colors.YELLOW}Нет доступных бекапов{Colors.RESET}")
        get_input("Нажмите Enter... ")
        return
    
    print(f"\n{Colors.YELLOW}Введите номер бекапа для восстановления:{Colors.RESET}")
    for i, b in enumerate(sorted(backups, reverse=True)[:10], 1):
        print(f"  {i}. {b}")
    
    try:
        idx = int(get_input("> ")) - 1
        if 0 <= idx < len(backups):
            backup_file = sorted(backups, reverse=True)[idx]
            print(f"\n{Colors.CYAN}Восстановление из {backup_file}...{Colors.RESET}")
            
            with zipfile.ZipFile(backup_file, 'r') as zipf:
                zipf.extractall('.')
            
            print(f"{Colors.GREEN}✅ Бекап восстановлен. Перезапустите бота.{Colors.RESET}")
        else:
            print(f"{Colors.RED}Неверный номер{Colors.RESET}")
    except ValueError:
        print(f"{Colors.RED}Неверный ввод{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}Ошибка: {e}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def delete_backup_cli():
    backups = [f for f in os.listdir('.') if f.startswith('novaub_backup_') and f.endswith('.zip')]
    
    if not backups:
        print(f"\n{Colors.YELLOW}Нет доступных бекапов{Colors.RESET}")
        get_input("Нажмите Enter... ")
        return
    
    print(f"\n{Colors.YELLOW}Введите номер бекапа для удаления:{Colors.RESET}")
    for i, b in enumerate(sorted(backups, reverse=True)[:10], 1):
        print(f"  {i}. {b}")
    
    try:
        idx = int(get_input("> ")) - 1
        if 0 <= idx < len(backups):
            backup_file = sorted(backups, reverse=True)[idx]
            os.remove(backup_file)
            print(f"{Colors.GREEN}✅ Бекап удалён: {backup_file}{Colors.RESET}")
        else:
            print(f"{Colors.RED}Неверный номер{Colors.RESET}")
    except ValueError:
        print(f"{Colors.RED}Неверный ввод{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}Ошибка: {e}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

# ────────────────────────────────────────────────
# 6. Овнеры
# ────────────────────────────────────────────────
def owners_menu(user_id):
    while True:
        clear_screen()
        print_header("👥 Овнеры")
        print()
        
        config = get_config(user_id)
        owners = config.get('owners', [])
        
        if owners:
            print(f"  {Colors.BOLD}Список овнеров:{Colors.RESET}\n")
            for i, o in enumerate(owners, 1):
                marker = " (Владелец бота)" if o == user_id else ""
                print(f"  {i}. {Colors.GREEN}✅{Colors.RESET} {o}{marker}")
            print()
        else:
            print(f"  {Colors.YELLOW}Нет добавленных овнеров{Colors.RESET}\n")
        
        print(f"  {Colors.GREEN}1){Colors.RESET} Добавить овнера")
        print(f"  {Colors.GREEN}2){Colors.RESET} Удалить овнера")
        print(f"  {Colors.GREEN}3){Colors.RESET} Список с правами")
        print(f"  {Colors.GREEN}0){Colors.RESET} Назад")
        print()
        
        choice = get_choice(["0", "1", "2", "3"])
        
        if choice == "1":
            add_owner(user_id)
        elif choice == "2":
            remove_owner(user_id)
        elif choice == "3":
            print(f"\n{Colors.CYAN}Используйте команду .owners в Telegram для подробной информации{Colors.RESET}")
            get_input("Нажмите Enter... ")
        elif choice == "0":
            return

# ────────────────────────────────────────────────
# 7. Управление
# ────────────────────────────────────────────────
def control_menu(user_id):
    while True:
        clear_screen()
        print_header("🔄 Управление")
        print()
        
        # Проверяем, запущен ли бот
        is_running, pid = is_bot_running()
        
        status = f"{Colors.GREEN}🟢 Running{Colors.RESET} (PID: {pid})" if is_running else f"{Colors.RED}🔴 Stopped{Colors.RESET}"
        
        print(f"  {Colors.BOLD}Status:{Colors.RESET} {status}")
        print()
        
        print(f"  {Colors.GREEN}1){Colors.RESET} 🔄 Перезапустить бота")
        print(f"  {Colors.GREEN}2){Colors.RESET} ⏹  Остановить бота")
        print(f"  {Colors.GREEN}3){Colors.RESET} 📥 Обновить из git")
        print(f"  {Colors.GREEN}4){Colors.RESET} 🧹 Очистить кэш")
        print(f"  {Colors.GREEN}5){Colors.RESET} 🔧 Режим отладки (вкл/выкл)")
        print(f"  {Colors.GREEN}6){Colors.RESET} 📊 Запустить бота")
        print(f"  {Colors.GREEN}0){Colors.RESET} Назад")
        print()
        
        choice = get_choice(["0", "1", "2", "3", "4", "5", "6"])
        
        if choice == "1":
            restart_bot_cli()
        elif choice == "2":
            stop_bot_cli()
        elif choice == "3":
            update_bot_cli()
        elif choice == "4":
            clear_cache_cli()
        elif choice == "5":
            toggle_debug_mode()
        elif choice == "6":
            start_bot_cli()
        elif choice == "0":
            return

# ────────────────────────────────────────────────
# Глобальная переменная для user_id
# ────────────────────────────────────────────────
CURRENT_USER_ID = None

def is_bot_running():
    """Проверяет, запущен ли бот, возвращает (True/False, PID)"""
    import subprocess
    try:
        # Ищем процесс main.py с нашим session файлом
        result = subprocess.run(
            ['pgrep', '-f', 'python.*main.py'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            return True, pids[0]
        return False, None
    except:
        return False, None

def start_bot_cli():
    global CURRENT_USER_ID
    is_running, pid = is_bot_running()
    if is_running:
        print(f"\n{Colors.YELLOW}Бот уже запущен (PID: {pid}){Colors.RESET}")
        get_input("Нажмите Enter... ")
        return
    
    print(f"\n{Colors.CYAN}Запуск бота...{Colors.RESET}")
    
    try:
        import subprocess
        # Запускаем бота в фоне
        proc = subprocess.Popen(
            [sys.executable, 'main.py'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        # Сохраняем PID
        if CURRENT_USER_ID:
            with open(f"novaub-{CURRENT_USER_ID}.pid", 'w') as f:
                f.write(str(proc.pid))
        
        print(f"{Colors.GREEN}✅ Бот запущен (PID: {proc.pid}){Colors.RESET}")
        print(f"  {Colors.CYAN}Для просмотра логов: Меню 4 → Логи{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}Ошибка запуска: {e}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def stop_bot_cli():
    global CURRENT_USER_ID
    is_running, pid = is_bot_running()
    if not is_running:
        print(f"\n{Colors.YELLOW}Бот не запущен{Colors.RESET}")
        get_input("Нажмите Enter... ")
        return
    
    print(f"\n{Colors.YELLOW}Остановка бота (PID: {pid})...{Colors.RESET}")
    print(f"  {Colors.GREEN}1){Colors.RESET} Да, остановить")
    print(f"  {Colors.GREEN}0){Colors.RESET} Отмена")
    
    choice = get_choice(["0", "1"])
    
    if choice == "1":
        try:
            import subprocess
            import signal
            os.killpg(int(pid), signal.SIGTERM)
            print(f"{Colors.GREEN}✅ Бот остановлен{Colors.RESET}")
            
            # Удаляем PID файл
            if CURRENT_USER_ID:
                pid_file = f"novaub-{CURRENT_USER_ID}.pid"
                if os.path.exists(pid_file):
                    os.remove(pid_file)
        except Exception as e:
            print(f"{Colors.RED}Ошибка остановки: {e}{Colors.RESET}")
            print(f"  {Colors.YELLOW}Попробуйте остановить вручную: kill -TERM {pid}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def restart_bot_cli():
    global CURRENT_USER_ID
    is_running, pid = is_bot_running()
    
    if not is_running:
        print(f"\n{Colors.YELLOW}Бот не запущен. Запускаю...{Colors.RESET}")
        start_bot_cli()
        return
    
    print(f"\n{Colors.CYAN}Перезапуск бота (PID: {pid})...{Colors.RESET}")
    print(f"  {Colors.GREEN}1){Colors.RESET} Да, перезапустить")
    print(f"  {Colors.GREEN}0){Colors.RESET} Отмена")
    
    choice = get_choice(["0", "1"])
    
    if choice == "1":
        try:
            import subprocess
            import signal
            
            # Останавливаем
            os.killpg(int(pid), signal.SIGTERM)
            time.sleep(1)
            
            # Запускаем заново
            proc = subprocess.Popen(
                [sys.executable, 'main.py'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            # Обновляем PID
            if CURRENT_USER_ID:
                with open(f"novaub-{CURRENT_USER_ID}.pid", 'w') as f:
                    f.write(str(proc.pid))
            
            print(f"{Colors.GREEN}✅ Бот перезапущен (PID: {proc.pid}){Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}Ошибка перезапуска: {e}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def update_bot_cli():
    print(f"\n{Colors.CYAN}Проверка обновлений...{Colors.RESET}")
    
    try:
        import subprocess
        
        # Проверяем, есть ли git
        result = subprocess.run(
            ['git', 'status'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print(f"{Colors.RED}Это не git репозиторий или git не установлен{Colors.RESET}")
            get_input("Нажмите Enter... ")
            return
        
        # Делаем git pull
        print(f"{Colors.CYAN}Выполняю git pull...{Colors.RESET}")
        result = subprocess.run(
            ['git', 'pull'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        output = result.stdout + result.stderr
        
        if "Already up to date" in output or "уже обновлено" in output.lower():
            print(f"{Colors.GREEN}✅ Уже последняя версия{Colors.RESET}")
        else:
            print(f"{Colors.GREEN}✅ Обновление выполнено:{Colors.RESET}")
            print(f"  {Colors.CYAN}{output[:500]}{Colors.RESET}")
            print(f"\n{Colors.YELLOW}Перезапустите бота для применения обновлений{Colors.RESET}")
            print(f"  {Colors.GREEN}1){Colors.RESET} Перезапустить сейчас")
            print(f"  {Colors.GREEN}0){Colors.RESET} Позже")
            
            choice = get_choice(["0", "1"])
            if choice == "1":
                restart_bot_cli()
                return
        
    except subprocess.TimeoutExpired:
        print(f"{Colors.RED}Таймаут обновления{Colors.RESET}")
    except FileNotFoundError:
        print(f"{Colors.RED}git не найден. Установите git.{Colors.RESET}")
    except Exception as e:
        print(f"{Colors.RED}Ошибка: {e}{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

def toggle_debug_mode():
    debug_file = ".debug_mode"
    is_enabled = os.path.exists(debug_file)
    
    print(f"\n{Colors.BOLD}Режим отладки:{Colors.RESET} {'🟢 ВКЛ' if is_enabled else '🔴 ВЫКЛ'}")
    print()
    print(f"  {Colors.GREEN}1){Colors.RESET} {'Выключить' if is_enabled else 'Включить'}")
    print(f"  {Colors.GREEN}0){Colors.RESET} Назад")
    print()
    
    choice = get_choice(["0", "1"])
    
    if choice == "1":
        if is_enabled:
            os.remove(debug_file)
            print(f"{Colors.GREEN}✅ Режим отладки выключен{Colors.RESET}")
        else:
            with open(debug_file, 'w') as f:
                f.write('1')
            print(f"{Colors.GREEN}✅ Режим отладки включён{Colors.RESET}")
    
    get_input("Нажмите Enter... ")

# ────────────────────────────────────────────────
# 9. Выполнение команд бота
# ────────────────────────────────────────────────
def execute_command_menu(user_id):
    while True:
        clear_screen()
        print_header("⚡ Выполнение команд")
        print()
        
        config = get_config(user_id)
        prefix = config.get('prefix', '.')
        aliases = config.get('aliases', {})
        
        print(f"  {Colors.BOLD}Префикс:{Colors.RESET} {prefix}")
        print(f"  {Colors.BOLD}Алиасы:{Colors.RESET} {len(aliases)}")
        print()
        
        # Список популярных команд
        print(f"  {Colors.BOLD}Популярные команды:{Colors.RESET}")
        popular_commands = [
            (".ping", "Проверка задержки"),
            (".help", "Справка по модулям"),
            (".backup", "Создать бекап"),
            (".restart", "Перезапуск бота"),
            (".owners", "Список овнеров"),
            (".config", "Панель конфигурации"),
            (".neofetch", "Системная информация"),
            (".ai", "AI ассистент"),
        ]
        
        for i, (cmd, desc) in enumerate(popular_commands, 1):
            print(f"  {Colors.GREEN}{i}){Colors.RESET} {cmd} - {desc}")
        
        print()
        print(f"  {Colors.GREEN}9){Colors.RESET} Ввести свою команду")
        print(f"  {Colors.GREEN}0){Colors.RESET} Назад")
        print()
        
        choice = get_choice([str(i) for i in range(10)])
        
        if choice == "0":
            return
        elif choice == "9":
            execute_custom_command(user_id)
        else:
            cmd, _ = popular_commands[int(choice) - 1]
            execute_command(user_id, cmd)

def execute_custom_command(user_id):
    print(f"\n{Colors.YELLOW}Введите команду (без префикса):{Colors.RESET}")
    cmd = get_input("> ")
    
    config = get_config(user_id)
    prefix = config.get('prefix', '.')
    
    full_cmd = f"{prefix}{cmd}"
    execute_command(user_id, full_cmd)

def execute_command(user_id, command):
    """
    Выполняет команду бота через эмуляцию сообщения.
    Для этого нужно отправить сообщение в чат с ботом.
    """
    print(f"\n{Colors.CYAN}Выполнение команды: {command}{Colors.RESET}")
    print()
    print(f"  {Colors.YELLOW}⚠️  Внимание:{Colors.RESET}")
    print(f"  Для выполнения команды отправьте это сообщение в Telegram:")
    print(f"  {Colors.BOLD}{command}{Colors.RESET}")
    print()
    print(f"  {Colors.CYAN}Результат появится в чате и в Меню 4 → Логи{Colors.RESET}")
    print()
    
    # Альтернатива - прямое выполнение через импорт модулей
    print(f"  {Colors.GREEN}1){Colors.RESET} Попробовать выполнить напрямую")
    print(f"  {Colors.GREEN}0){Colors.RESET} Отправить в Telegram")
    print()
    
    choice = get_choice(["0", "1"])
    
    if choice == "0":
        get_input("Нажмите Enter... ")
        return
    
    # Пытаемся выполнить напрямую
    print(f"\n{Colors.CYAN}Попытка выполнения...{Colors.RESET}")
    
    # Извлекаем имя команды
    cmd_name = command.lstrip('.').split()[0]
    args = command.split()[1:] if ' ' in command else []
    
    # Ищем модуль с этой командой
    found = False
    for folder in ['modules', 'loaded_modules']:
        if not os.path.exists(folder):
            continue
        
        for module_file in os.listdir(folder):
            if not module_file.endswith('.py'):
                continue
            
            module_path = os.path.join(folder, module_file)
            try:
                with open(module_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Проверяем, есть ли такая команда в модуле
                if f'commands["{cmd_name}"]' in content or f"'{cmd_name}'" in content or f'"{cmd_name}"' in content:
                    print(f"  {Colors.GREEN}✅{Colors.RESET} Команда найдена в {module_path}")
                    found = True
                    break
            except:
                pass
    
    if found:
        print(f"\n{Colors.GREEN}Команда доступна в системе{Colors.RESET}")
        print(f"  {Colors.CYAN}Отправьте '{command}' в Telegram для выполнения{Colors.RESET}")
        print(f"  {Colors.GREEN}Или перезапустите бота: Меню 7 → Перезапустить{Colors.RESET}")
    else:
        print(f"\n{Colors.YELLOW}Команда не найдена в модулях{Colors.RESET}")
        print(f"  {Colors.CYAN}Возможно, это алиас или команда инлайн-бота{Colors.RESET}")
    
    get_input("Нажмите Enter... ")
# ────────────────────────────────────────────────
def diagnostics_menu(user_id):
    while True:
        clear_screen()
        print_header("🏥 Диагностика")
        print()
        
        checks = []
        
        # Проверка сессии
        session_file = f"nova-{user_id}.session"
        session_exists = os.path.exists(session_file)
        checks.append(("Session file", session_exists, session_file))
        
        # Проверка конфига
        config_file = f"config-{user_id}.json"
        config_exists = os.path.exists(config_file)
        checks.append(("Config file", config_exists, config_file))
        
        # Проверка kernel_config
        kernel_config_file = f"kernel_config-{user_id}.json"
        kernel_config_exists = os.path.exists(kernel_config_file)
        checks.append(("Kernel config", kernel_config_exists, kernel_config_file))
        
        # Проверка базы данных
        db_exists = os.path.exists("novaub.db")
        checks.append(("Database", db_exists, "novaub.db"))
        
        # Проверка папок
        modules_exists = os.path.exists("modules")
        checks.append(("Modules folder", modules_exists, "modules/"))
        
        loaded_modules_exists = os.path.exists("loaded_modules")
        checks.append(("Loaded modules", loaded_modules_exists, "loaded_modules/"))
        
        # Проверка логов
        log_exists = os.path.exists("novaub.log")
        checks.append(("Log file", log_exists, "novaub.log"))
        
        # Проверка репозиториев
        repos_exists = os.path.exists("repos.json")
        checks.append(("Repos file", repos_exists, "repos.json"))
        
        # Вывод результатов
        print(f"  {Colors.BOLD}Результаты проверки:{Colors.RESET}\n")
        
        all_ok = True
        for name, ok, path in checks:
            status = f"{Colors.GREEN}✅ OK{Colors.RESET}" if ok else f"{Colors.RED}❌ FAIL{Colors.RESET}"
            if not ok:
                all_ok = False
            print(f"  {status}  {name}: {path}")
        
        print()
        
        if all_ok:
            print(f"  {Colors.GREEN}Все проверки пройдены успешно!{Colors.RESET}")
        else:
            print(f"  {Colors.RED}Обнаружены проблемы. Проверьте файлы выше.{Colors.RESET}")
        
        print()
        print(f"  {Colors.GREEN}1){Colors.RESET} Повторить проверку")
        print(f"  {Colors.GREEN}2){Colors.RESET} Проверить зависимости")
        print(f"  {Colors.GREEN}3){Colors.RESET} Информация о системе")
        print(f"  {Colors.GREEN}0){Colors.RESET} Назад")
        print()
        
        choice = get_choice(["0", "1", "2", "3"])
        
        if choice == "1":
            continue
        elif choice == "2":
            check_dependencies()
        elif choice == "3":
            system_info()
        elif choice == "0":
            return

def check_dependencies():
    print(f"\n{Colors.CYAN}Проверка зависимостей...{Colors.RESET}\n")
    
    deps = ['telethon', 'aiosqlite', 'flask', 'pyrogram', 'requests', 'aiohttp']
    
    for dep in deps:
        try:
            __import__(dep)
            print(f"  {Colors.GREEN}✅{Colors.RESET} {dep}")
        except ImportError:
            print(f"  {Colors.RED}❌{Colors.RESET} {dep} - не установлен")
    
    print()
    get_input("Нажмите Enter... ")

def system_info():
    import platform
    
    print(f"\n{Colors.BOLD}Системная информация:{Colors.RESET}\n")
    print(f"  {Colors.BOLD}OS:{Colors.RESET} {platform.system()} {platform.release()}")
    print(f"  {Colors.BOLD}Python:{Colors.RESET} {platform.python_version()}")
    print(f"  {Colors.BOLD}Architecture:{Colors.RESET} {platform.architecture()[0]}")
    print(f"  {Colors.BOLD}Processor:{Colors.RESET} {platform.processor() or 'N/A'}")
    print()
    get_input("Нажмите Enter... ")

# ────────────────────────────────────────────────
# Точка входа
# ────────────────────────────────────────────────
def main():
    global CURRENT_USER_ID
    
    # Проверяем аргументы командной строки
    if len(sys.argv) > 1:
        if sys.argv[1] == "stop":
            print(f"{Colors.YELLOW}Для остановки бота используйте Меню 7 → Остановить{Colors.RESET}")
            sys.exit(0)
        elif sys.argv[1] == "help":
            print(f"\n{Colors.BOLD}NovaUB CLI - Доступные команды:{Colors.RESET}")
            print(f"  python cli.py       - Запустить интерактивный CLI")
            print(f"  python cli.py stop  - Информация об остановке")
            print(f"  python cli.py help  - Эта справка")
            sys.exit(0)
    
    # Находим ID аккаунта
    user_id = get_user_id()
    
    if not user_id:
        print(f"{Colors.RED}Ошибка: Не найдена сессия nova-*.session{Colors.RESET}")
        print(f"  Убедитесь, что бот был запущен хотя бы один раз.")
        sys.exit(1)
    
    # Устанавливаем глобальную переменную
    CURRENT_USER_ID = user_id
    
    # Проверяем наличие конфига
    config_file = f"config-{user_id}.json"
    if not os.path.exists(config_file):
        print(f"{Colors.YELLOW}Предупреждение: Конфиг {config_file} не найден{Colors.RESET}")
        print(f"  Будет создан новый конфиг при первом запуске бота.")
    
    # Запускаем главное меню
    try:
        main_menu(user_id)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Выход...{Colors.RESET}")
        sys.exit(0)

if __name__ == "__main__":
    main()
