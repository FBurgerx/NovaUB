import html
import json
import os
import sys
from telethon.tl.custom import Message

from core.meta_lib import extract_command_descriptions, read_module_meta
from core.rich import send_rich, table, details, list_items, emoji

LIST_ALIASES = {"list", "all", "ls"}

# Loader регистрирует модули в sys.modules под префиксированными именами
# (modules_<name> для modules/, loaded_<name> для loaded_modules/), чтобы
# избежать затенения корневых модулей. Помогаем найти объект модуля по
# любому из вариантов.
_MODULE_KEY_PREFIXES = ("", "modules_", "loaded_")


def _find_module(module_name):
    for prefix in _MODULE_KEY_PREFIXES:
        obj = sys.modules.get(f"{prefix}{module_name}")
        if obj is not None:
            return obj
    return None

# ── Премиум-эмодзи (по ID — голый юникод в MTProto не рендерится) ─────────
EMOJI_GHOST   = "<tg-emoji emoji-id=5897962422169243693>👻</tg-emoji>"
EMOJI_GEAR    = "<tg-emoji emoji-id=5877396173135811032>⚙️</tg-emoji>"
EMOJI_USER    = "<tg-emoji emoji-id=5879770735999717115>👤</tg-emoji>"
EMOJI_ERR     = "<tg-emoji emoji-id=5778527486270770928>❌</tg-emoji>"
EMOJI_ARROW   = "<tg-emoji emoji-id=5877468380125990242>➡️</tg-emoji>"
EMOJI_BOX     = "<tg-emoji emoji-id=5461117441612462242>📦</tg-emoji>"
EMOJI_CMD     = "<tg-emoji emoji-id=5219855643518212850>💬</tg-emoji>"
EMOJI_SPARK   = "<tg-emoji emoji-id=5775887550262546277>✨</tg-emoji>"


def _escape(value):
    return html.escape(str(value)) if value is not None else ""


def _get_prefix(client):
    pref = getattr(client, "prefix", None)
    if pref:
        return pref
    path = f"config-{client._self_id}.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                pref = json.load(f).get("prefix", ".")
        except Exception:
            pref = "."
    return pref or "."


def _collect_commands(client):
    module_cmds = {}
    for cmd_name, info in client.commands.items():
        mod_name = info.get("module", "unknown")
        module_cmds.setdefault(mod_name, []).append(cmd_name)
    for cmds in module_cmds.values():
        cmds.sort()
    return module_cmds


def _first_line(text):
    if not text:
        return ""
    return str(text).strip().splitlines()[0].strip()


def _command_descriptions(client, module_name, commands):
    module = _find_module(module_name)
    raw_meta = getattr(module, "__meta__", None) if module else None
    meta_descs = extract_command_descriptions(raw_meta)
    result = {}
    for cmd in commands:
        key = cmd.lower()
        desc = ""
        info = client.commands.get(cmd, {})
        if isinstance(info, dict):
            desc = info.get("description") or info.get("desc") or info.get("about") or info.get("help") or ""
        desc = _first_line(desc)
        if not desc:
            desc = meta_descs.get(key, "")
        if not desc:
            func = client.commands.get(cmd, {}).get("func")
            desc = _first_line(getattr(func, "__doc__", ""))
        result[key] = desc
    return result


def _resolve_target(target, module_names, commands_map, pref):
    cleaned = target.strip()
    if cleaned.startswith(pref):
        cleaned = cleaned[len(pref):]
    cleaned_lower = cleaned.lower()
    if cleaned_lower in commands_map:
        return commands_map[cleaned_lower]["module"], []
    exact = [m for m in module_names if m.lower() == cleaned_lower]
    if exact:
        return exact[0], []
    partial = [m for m in module_names if m.lower().startswith(cleaned_lower)]
    if len(partial) == 1:
        return partial[0], []
    return None, partial


# ── РЕНДЕР: карточка модуля (.help <модуль>) ─────────────────────────────


def _render_module_detail(client, module_name, module, meta, pref):
    display = meta.get("name") or module_name
    author = meta.get("author") or "Не указан"
    description = _first_line(meta.get("description")) or "Нет описания"
    commands = meta.get("commands") or []
    cmd_descs = _command_descriptions(client, module_name, commands) if module else {}

    header = f"<h3>{EMOJI_GHOST} {_escape(display)}</h3>"
    desc_line = f"{EMOJI_GEAR} <b>Описание:</b> {_escape(description)}"

    if commands:
        lines = []
        for cmd in commands:
            # алиас не рисуем как отдельную команду — он уйдёт в «синонимы»
            info = client.commands.get(cmd, {})
            if isinstance(info, dict) and info.get("alias_of"):
                continue
            desc = cmd_descs.get(cmd.lower()) or "нет описания"
            aliases = []
            if isinstance(info, dict):
                aliases = [a for a in info.get("aliases", []) if a != cmd]
            alias_html = ""
            if aliases:
                alias_html = (
                    "\n     <i>синонимы:</i> "
                    + ", ".join(f"<code>{_escape(pref + a)}</code>" for a in aliases)
                )
            line = (
                f"{EMOJI_ARROW} <code>{_escape(pref + cmd)}</code>"
                f" — {_escape(desc)}{alias_html}"
            )
            lines.append(line)
        cmds_block = "\n".join(lines) if lines else "<i>Нет команд</i>"
    else:
        cmds_block = "<i>Нет команд</i>"

    author_line = f"{EMOJI_USER} <b>Разработчик:</b> <code>{_escape(author)}</code>"

    return (
        f"{header}"
        f"\n{desc_line}"
        f"\n\n{cmds_block}"
        f"\n\n{author_line}"
    )


# ── РЕНДЕР: общий список (.help) ──────────────────────────────────────────


def _render_module_list(client, module_cmds, pref):
    """Список всех модулей: системные и внешние — отдельными секциями."""
    sys_mods, ext_mods = {}, {}

    # Принадлежность модуля к modules/ или loaded_modules/ определяем по
    # __file__ объекта модуля из sys.modules. Loader кладёт модули под
    # префиксированными именами (modules_<name> / loaded_<name>), поэтому
    # перебираем все варианты.
    def _module_file(mod_name):
        mod = _find_module(mod_name)
        if mod is None:
            return ""
        return getattr(mod, "__file__", "") or ""

    for cmd_name, info in client.commands.items():
        if not isinstance(info, dict):
            continue
        mod_name = info.get("module", "unknown")
        if info.get("alias_of"):
            continue
        mod_path = _module_file(mod_name)
        target = ext_mods if "loaded_modules" in mod_path else sys_mods
        target.setdefault(mod_name, []).append(cmd_name)

    total_mods = len(sys_mods) + len(ext_mods)
    total_cmds = sum(
        1 for c in client.commands.values()
        if not (isinstance(c, dict) and c.get("alias_of"))
    )


    def section(title, emoji, mods_dict):
        if not mods_dict:
            return f"{emoji} <b>{title}</b>\n<i>Пусто</i>"
        lines = []
        for mod, cmds in sorted(mods_dict.items()):
            cmds_str = " | ".join(f"{pref}{c}" for c in sorted(cmds))
            module = _find_module(mod)
            meta = read_module_meta(module, mod, cmds) if module else {}
            display = (meta.get("name") if meta else None) or mod
            lines.append(
                f"{EMOJI_ARROW} <b>{_escape(display)}</b>"
                f"\n     <code>{_escape(cmds_str)}</code>"
            )
        return f"{emoji} <b>{title}</b>\n" + "\n".join(lines)

    text = (
        f"<h1>{EMOJI_GHOST} NovaUB Modules</h1>"
        f"\n{EMOJI_SPARK} Модулей: <b>{total_mods}</b> · Команд: <b>{total_cmds}</b>"
        f"\n<i>Подробнее о модуле:</i> <code>{pref}help &lt;имя&gt;</code>"
        f"\n\n"
        f"{section('Системные', EMOJI_GEAR, sys_mods)}"
        f"\n\n"
        f"{section('Внешние', EMOJI_BOX, ext_mods)}"
    )
    return text


async def help_cmd(client, message, args):
    pref = _get_prefix(client)
    module_cmds = _collect_commands(client)
    module_names = sorted(set(module_cmds.keys()) | set(getattr(client, "loaded_modules", set())))

    # Rich-режим: .help rich (или .help rich <модуль>) — отправляет
    # полноценную таблицу/<details> через инлайн-бота.
    rich_mode = bool(args) and args[0].lower() == "rich"
    if rich_mode:
        args = args[1:]

    if args and args[0].lower() not in LIST_ALIASES:
        target = args[0]
        module_name, matches = _resolve_target(target, module_names, client.commands, pref)
        if not module_name:
            hint = ""
            if matches:
                preview = " | ".join(sorted(matches)[:10])
                hint = f"\n{EMOJI_ARROW} Возможные совпадения: <code>{_escape(preview)}</code>"
            text = (
                f"{EMOJI_ERR} <b>Модуль не найден</b>"
                f"{hint}\n"
                f"<b>Usage:</b> <code>{_escape(pref)}help &lt;module|command&gt;</code>"
            )
            return await message.edit(text, parse_mode='html')

        module = _find_module(module_name)
        # команды модуля — из реестра команд, а не только из __meta__:
        # так видны команды и нового стиля (с @command), и алиасы
        module_commands = [
            c for c, info in client.commands.items()
            if isinstance(info, dict) and info.get("module") == module_name
            and not info.get("alias_of")
        ]
        meta = read_module_meta(module, module_name, module_commands)
        detail = _render_module_detail(client, module_name, module, meta, pref)
        return await message.edit(detail, parse_mode='html')

    # ── Список всех модулей ──────────────────────────────────────────────
    if rich_mode:
        ok = await _send_rich_help(client, message, module_cmds, pref)
        if ok:
            return
        # бот недоступен → обычный текст

    text = _render_module_list(client, module_cmds, pref)
    await message.edit(text, parse_mode='html')


async def _send_rich_help(client, message, module_cmds, pref):
    """Отправляет .help как настоящее rich-сообщение (таблица + details).

    Возвращает True при успехе, False если бот недоступен
    (тогда help падает на обычный текстовый режим).
    """
    sys_mods, ext_mods = {}, {}

    def _split(mods_dict, src, is_ext):
        for mod, cmds in sorted(mods_dict.items()):
            target = ext_mods if is_ext else sys_mods
            target.setdefault(mod, []).extend(cmds)

    for cmd_name, info in client.commands.items():
        if not isinstance(info, dict) or info.get("alias_of"):
            continue
        mod_name = info.get("module", "unknown")
        mod = _find_module(mod_name)
        mod_path = getattr(mod, "__file__", "") or "" if mod else ""
        if "loaded_modules" in mod_path:
            ext_mods.setdefault(mod_name, []).append(cmd_name)
        else:
            sys_mods.setdefault(mod_name, []).append(cmd_name)

    def _build_section(title, mods_dict):
        if not mods_dict:
            return ""
        rows = []
        for mod, cmds in sorted(mods_dict.items()):
            mod_obj = _find_module(mod)
            meta = read_module_meta(mod_obj, mod, cmds) if mod_obj else {}
            display = (meta.get("name") if meta else None) or mod
            cmds_str = " | ".join(f"{pref}{c}" for c in sorted(cmds))
            rows.append([display, cmds_str])
        return (
            f"<h3>{_escape(title)}</h3>"
            + table(["Модуль", "Команды"], rows)
        )

    html_text = (
        f"<h1>NovaUB Modules</h1>"
        + _build_section("Системные", sys_mods)
        + _build_section("Внешние", ext_mods)
        + details(
            "Подробнее о модуле",
            f"<p>Используй <code>{pref}help &lt;имя&gt;</code> "
            f"для карточки модуля</p>",
        )
    )

    try:
        reply_to = getattr(message, "reply_to_msg_id", None) or None
        result = await send_rich(
            client,
            message.peer_id,
            html_text,
            reply_to=reply_to,
        )
        if result is not None:
            try:
                await message.delete()
            except Exception:
                pass
            return True
    except Exception:
        pass
    return False


def register(app, commands, module_name):
    commands["help"] = {"func": help_cmd, "module": module_name}
