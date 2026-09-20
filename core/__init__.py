"""NovaUB core — ядро юзербота.

Папка core/ содержит системные модули. Модули пользователя (modules/,
loaded_modules/) НЕ должны импортировать внутренности ядра напрямую —
для них есть стабильный API, доступный через `import core`.

Обратная совместимость: до рефакторинга скрипты делали
    import config as nova_config
    from meta_lib import ...
    from utils import get_args_raw

Эти имена по-прежнему работают из любой точки проекта — core
прокидывает их в себя. Это нужно, чтобы сторонние модули не сломались.
"""

# Стабильный публичный API ядра. Расширяем по мере необходимости.
from . import config as config
from . import database as database
from . import kernel as kernel
from . import loader as loader

__all__ = ["config", "database", "kernel", "loader"]

# --- Обратная совместимость со старыми плоскими импортами ---
# Модули из modules/loaded_modules могли использовать "import config".
# Прокидываем ссылку в sys.modules, чтобы старый код не сломался.
import sys as _sys

for _name in ("config", "database", "meta_lib", "utils"):
    if _name not in _sys.modules:
        try:
            _sys.modules[_name] = __import__(
                f"core.{_name}", fromlist=[_name]
            )
        except Exception:
            pass
del _sys, _name
