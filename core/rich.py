"""Rich-форматирование для NovaUB.

MTProto не умеет отправлять PageBlock-блоки (таблицы, <details>, списки,
настоящие заголовки) от имени пользователя — только MessageEntity. Зато
Telegram Bot API умеет: sendRichMessage принимает HTML с <table>, <details>,
<ul>, <h1>-<h6> и рендерит их настоящими PageBlock-ами.

Путь сообщения: модуль NovaUB → send_rich() → Bot API sendRichMessage
через инлайн-бота (komaru_vibesbot) → Telegram парсит HTML в RichMessage.

┌─ Использование ──────────────────────────────────────────────────────┐
│ from core.rich import send_rich                                      │
│                                                                     │
│ await send_rich(client, peer_id, '''                                │
│     <h1>NovaUB</h1>                                                 │
│     <table>                                                         │
│       <tr><th>Модуль</th><th>Команд</th></tr>                       │
│       <tr><td>ping</td><td>1</td></tr>                              │
│     </table>                                                        │
│     <details><summary>Команды</summary>                             │
│       <p>.ntest — тест</p>                                          │
│     </details>                                                      │
│ ''', reply_to=message.id)                                           │
└──────────────────────────────────────────────────────────────────────┘

Поддерживаемые теги (Bot API 10.2):
  <h1>-<h6>, <p>, <b>, <i>, <u>, <s>, <code>, <pre>, <a>,
  <blockquote>, <table> (с <tr>/<th>/<td>), <ul>/<ol> (с <li>),
  <details> (с <summary>), <tg-emoji emoji-id="…">, <tg-spoiler>,
  <mark>, <br>, <hr>
"""

import html as _html
import logging

log = logging.getLogger(__name__)

# ── Поддерживаемые теги для подсветки в строке документации ──────────────
SUPPORTED_TAGS = (
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "b", "strong", "i", "em",
    "u", "ins", "s", "del", "code", "pre", "a", "blockquote", "table",
    "tr", "th", "td", "thead", "tbody", "ul", "ol", "li", "details",
    "summary", "tg-emoji", "tg-spoiler", "mark", "br", "hr", "span", "div",
)


def _get_token(client):
    """Достаёт токен инлайн-бота из kernel/config."""
    kernel = getattr(client, "kernel", None)
    if kernel is not None:
        token = getattr(kernel, "config", {}).get("inline_bot_token")
        if token:
            return token
        bot = getattr(kernel, "inline_bot", None)
        if bot is not None:
            return getattr(bot, "token", None) or None
    return None


def _get_api_root(client):
    """api_id/api_hash для Bot API-вызовов (нужны только если токен от MCUB)."""
    kernel = getattr(client, "kernel", None)
    if kernel is not None:
        api = getattr(kernel, "config", {}).get("api", {})
        return api.get("api_id"), api.get("api_hash")
    return None, None


async def send_rich(client, peer_id, html_text, reply_to=None,
                    disable_notification=False, bot_token=None):
    """Отправляет rich-сообщение (с таблицами, <details>, списками).

    client     — TelegramClient юзербота
    peer_id    — куда отправить (int, username, Peer)
    html_text  — HTML с rich-тегами
    reply_to   — на какое сообщение ответить (id или Message)
    bot_token  — токен бота (по умолчанию берётся из kernel.inline_bot)

    Возвращает словарь ответа Bot API (с message_id) или None при ошибке.
    """
    import aiohttp
    import json

    if bot_token is None:
        bot_token = _get_token(client)
    if not bot_token:
        raise RuntimeError("токен инлайн-бота не найден — rich недоступен")

    # peer_id → chat_id для Bot API
    chat_id = await _resolve_chat_id(client, peer_id)

    payload = {
        "chat_id": chat_id,
        "rich_message": json.dumps({"html": html_text}, ensure_ascii=False),
    }
    if reply_to is not None:
        payload["reply_to_message_id"] = (
            reply_to.id if hasattr(reply_to, "id") else int(reply_to)
        )
    if disable_notification:
        payload["disable_notification"] = True

    url = f"https://api.telegram.org/bot{bot_token}/sendRichMessage"
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            if not data.get("ok"):
                desc = data.get("description", "неизвестная ошибка")
                log.error("sendRichMessage failed: %s", desc)
                return None
            return data.get("result", {})


async def _resolve_chat_id(client, peer_id):
    """Преобразует peer в chat_id, понятный Bot API."""
    # Уже число — отдаём как есть (бот видит этот чат)
    if isinstance(peer_id, int):
        return peer_id

    # Строка-username
    if isinstance(peer_id, str):
        if peer_id.startswith("@"):
            entity = await client.get_entity(peer_id)
            return entity.id
        try:
            return int(peer_id)
        except ValueError:
            entity = await client.get_entity(peer_id)
            return entity.id

    # Peer-объект Telethon
    if hasattr(peer_id, "chat_id"):
        return peer_id.chat_id
    if hasattr(peer_id, "user_id"):
        return peer_id.user_id

    # Message → его чат
    if hasattr(peer_id, "peer_id"):
        return await _resolve_chat_id(client, peer_id.peer_id)

    entity = await client.get_entity(peer_id)
    return entity.id


# ── Утилиты для построения HTML ───────────────────────────────────────────


def table(headers, rows, title=None, striped=True):
    """Собирает HTML-таблицу.

    headers  — список строк (шапка) или None
    rows     — список списков ячеек
    title    — заголовок таблицы (Paragraph перед ней)
    """
    parts = []
    if title:
        parts.append(f"<p>{_escape(title)}</p>")
    parts.append("<table>")
    if headers:
        parts.append("<tr>" + "".join(f"<th>{_escape(h)}</th>" for h in headers) + "</tr>")
    for row in rows:
        parts.append("<tr>" + "".join(f"<td>{_escape(c)}</td>" for c in row) + "</tr>")
    parts.append("</table>")
    return "\n".join(parts)


def details(summary, blocks, open_by_default=False):
    """Собирает свёрнутый блок <details>.

    summary  — что видно в свёрнутом виде
    blocks   — HTML-строка или список HTML-строк внутри
    open_by_default — развёрнут сразу
    """
    if isinstance(blocks, (list, tuple)):
        blocks = "\n".join(blocks)
    tag = "<details open>" if open_by_default else "<details>"
    return f"{tag}<summary>{_escape(summary)}</summary>{blocks}</details>"


def list_items(items, ordered=False):
    """Собирает <ul> или <ol>."""
    tag = "ol" if ordered else "ul"
    body = "".join(f"<li>{item}</li>" for item in items)
    return f"<{tag}>{body}</{tag}>"


def emoji(emoji_id, fallback="✨"):
    """Премиум-эмодзи по ID (в rich-контексте работает обычный тег)."""
    return f'<tg-emoji emoji-id="{int(emoji_id)}">{fallback}</tg-emoji>'


def _escape(value):
    return _html.escape(str(value)) if value is not None else ""
