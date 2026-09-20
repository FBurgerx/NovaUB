"""NovaUB core — ядро юзербота.

Папка core/ содержит системные модули. Модули пользователя (modules/,
loaded_modules/) НЕ должны импортировать внутренности ядра напрямую —
для них есть стабильный API в этом файле.

Обратная совместимость: модули, которые уже используют register(), продолжают
работать — загрузчик определяет стиль автоматически (см. novaub.py,
load_modules_with_config).
"""

# Стабильный API для модулей
from core.commands import command, inline, hook  # noqa: F401
from core import config, database  # noqa: F401
from core.config import is_owner  # noqa: F401

__all__ = ["command", "inline", "hook", "config", "database", "is_owner"]
