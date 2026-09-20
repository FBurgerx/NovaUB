import json
import os
import html


def _escape(value):
    return html.escape(str(value)) if value is not None else ""


def _get_prefix(client):
    path = f"config-{client._self_id}.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("prefix", ".")
        except Exception:
            pass
    return "."


def _load_config(client):
    path = f"config-{client._self_id}.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_config(client, config):
    path = f"config-{client._self_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


async def alias_cmd(client, message, args):
    pref = _get_prefix(client)

    if len(args) < 2:
        await message.edit(
            f"<blockquote><tg-emoji emoji-id=5775887550262546277>❗️</emoji> "
            f"<b>Usage:</b> <code>{_escape(pref)}alias &lt;name&gt; &lt;target&gt;</code></blockquote>",
            parse_mode='html'
        )
        return

    name = args[0].lower()
    target = args[1].lower()

    if target not in client.commands:
        await message.edit(
            f"<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
            f"<b>Команда</b> <code>{_escape(target)}</code> <b>не найдена.</b></blockquote>",
            parse_mode='html'
        )
        return

    if name in client.commands:
        await message.edit(
            f"<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
            f"<b>Имя</b> <code>{_escape(name)}</code> <b>уже занято командой.</b></blockquote>",
            parse_mode='html'
        )
        return

    config = _load_config(client)
    aliases = config.get("aliases", {})
    aliases[name] = target
    config["aliases"] = aliases
    _save_config(client, config)

    await message.edit(
        f"<blockquote><tg-emoji emoji-id=5776375003280838798>✅</emoji> "
        f"<b>Алиас создан:</b> <code>{_escape(pref)}{_escape(name)}</code> → "
        f"<code>{_escape(pref)}{_escape(target)}</code></blockquote>",
        parse_mode='html'
    )


async def delalias_cmd(client, message, args):
    pref = _get_prefix(client)

    if not args:
        await message.edit(
            f"<blockquote><tg-emoji emoji-id=5775887550262546277>❗️</emoji> "
            f"<b>Usage:</b> <code>{_escape(pref)}delalias &lt;name&gt;</code></blockquote>",
            parse_mode='html'
        )
        return

    name = args[0].lower()
    config = _load_config(client)
    aliases = config.get("aliases", {})

    if name not in aliases:
        await message.edit(
            f"<blockquote><tg-emoji emoji-id=5778527486270770928>❌</emoji> "
            f"<b>Алиас</b> <code>{_escape(name)}</code> <b>не найден.</b></blockquote>",
            parse_mode='html'
        )
        return

    del aliases[name]
    config["aliases"] = aliases
    _save_config(client, config)

    await message.edit(
        f"<blockquote><tg-emoji emoji-id=5776375003280838798>✅</emoji> "
        f"<b>Алиас</b> <code>{_escape(name)}</code> <b>удалён.</b></blockquote>",
        parse_mode='html'
    )


async def aliases_cmd(client, message, args):
    pref = _get_prefix(client)
    config = _load_config(client)
    aliases = config.get("aliases", {})

    if not aliases:
        await message.edit(
            "<blockquote><tg-emoji emoji-id=5897962422169243693>👻</emoji> "
            "<b>Нет алиасов.</b></blockquote>",
            parse_mode='html'
        )
        return

    lines = []
    for name, target in sorted(aliases.items()):
        lines.append(
            f"<code>{_escape(pref)}{_escape(name)}</code> → "
            f"<code>{_escape(pref)}{_escape(target)}</code>"
        )

    text = (
        "<tg-emoji emoji-id=5897962422169243693>👻</emoji> <b>Алиасы</b>\n\n"
        "<blockquote>" + "\n".join(lines) + "</blockquote>"
    )
    await message.edit(text, parse_mode='html')


def register(app, commands, module_name):
    commands["alias"] = {"func": alias_cmd, "module": module_name, "description": "Создать алиас команды"}
    commands["delalias"] = {"func": delalias_cmd, "module": module_name, "description": "Удалить алиас"}
    commands["aliases"] = {"func": aliases_cmd, "module": module_name, "description": "Список алиасов"}
