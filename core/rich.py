"""Rich-форматирование для NovaUB.

MTProto не умеет отправлять PageBlock-блоки (таблицы, <details>, списки,
настоящие заголовки) от имени пользователя — только MessageEntity. Зато
их можно отправить через инлайн-бота: юзербот делает inline-запрос своему
боту, тот отвечает InputBotInlineMessageRichMessage, и юзербот отправляет
результат в чат. Сообщение приходит от имени пользователя.

Путь сообщения: модуль → send_rich() → inline-запрос к боту →
бот отдаёт rich-результат из кэша → SendInlineBotResultRequest → чат.

┌─ Использование ──────────────────────────────────────────────────────┐
│ from core.rich import send_rich, table, details, list_items          │
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

Поддерживаемые теги (Bot API 10.2 / InputRichMessageHTML):
  <h1>-<h6>, <p>, <b>, <i>, <u>, <s>, <code>, <pre>, <a>,
  <blockquote>, <table> (с <tr>/<th>/<td>), <ul>/<ol> (с <li>),
  <details> (с <summary>), <mark>, <br>, <hr>
"""

import asyncio
import html as _html
import logging

log = logging.getLogger(__name__)


async def send_rich(client, peer_id, html_text, reply_to=None,
                    hide_via=True, bot_username=None, timeout=30):
    """Отправляет rich-сообщение через инлайн-бота.

    client       — TelegramClient юзербота
    peer_id      — куда отправить
    html_text    — HTML с rich-тегами
    reply_to     — на какое сообщение ответить (id или Message)
    hide_via     — скрыть подпись «via @bot»
    bot_username — username инлайн-бота (по умолчанию из kernel.inline_bot)

    Возвращает отправленное сообщение (Message) или None при ошибке.
    """
    from telethon.tl.functions.messages import (
        GetInlineBotResultsRequest, SendInlineBotResultRequest,
    )
    from telethon.tl.types import (
        InputBotInlineMessageRichMessage, InputRichMessageHTML,
        BotInlineResult, BotInlineMessageRichMessage,
    )

    # 1. Находим бота
    kernel = getattr(client, "kernel", None)
    if bot_username is None and kernel is not None:
        inline = getattr(kernel, "inline_bot", None)
        if inline is not None:
            bot_username = getattr(inline, "username", None)
    if not bot_username:
        raise RuntimeError("inline-бот не настроен — rich недоступен")
    bot_username = bot_username.lstrip("@")

    # 2. Кэшируем HTML для бота: бот отдаст его по маркеру
    marker = _render_marker(html_text)
    cache = _get_cache(kernel)
    cache[marker] = html_text

    # 3. Inline-запрос
    query_text = f"rich_{marker}"
    try:
        results = await asyncio.wait_for(client(GetInlineBotResultsRequest(
            bot=await client.get_input_entity(bot_username),
            peer=await client.get_input_entity(peer_id),
            query=query_text,
            offset="",
        )), timeout=timeout)
    except asyncio.TimeoutError:
        log.error("inline-бот не ответил за %ss — rich не отправлен", timeout)
        cache.pop(marker, None)
        return None

    # 4. Находим наш rich-результат
    result = None
    for res in getattr(results, "results", None) or []:
        sm = getattr(res, "send_message", None)
        if isinstance(sm, BotInlineMessageRichMessage):
            result = res
            break
    if result is None:
        log.error("inline-бот не вернул rich-результат (видимо, бот не запущен)")
        cache.pop(marker, None)
        return None

    # 5. Отправляем результат от имени пользователя
    reply_arg = None
    if reply_to is not None:
        reply_arg = reply_to.id if hasattr(reply_to, "id") else int(reply_to)
    try:
        updates = await asyncio.wait_for(client(SendInlineBotResultRequest(
            peer=await client.get_input_entity(peer_id),
            query_id=results.query_id,
            id=result.id,
            reply_to=reply_arg,
            hide_via=hide_via,
        )), timeout=timeout)
    finally:
        cache.pop(marker, None)

    # 6. Достаём Message из Updates
    return _extract_message(client, updates)


def _get_cache(kernel):
    """Возвращает словарь кэша rich-сообщений (создаёт при необходимости)."""
    if kernel is None:
        return {}
    cache = getattr(kernel, "_rich_cache", None)
    if cache is None:
        cache = {}
        try:
            kernel._rich_cache = cache
        except Exception:
            pass
    return cache


def _render_marker(html_text):
    """Уникальный идентификатор rich-сообщения — чтобы найти его в выдаче."""
    import hashlib
    import time
    payload = f"{time.time()}|{len(html_text)}|{html_text[:32]}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _extract_message(client, updates):
    """Достаёт Message из Updates, которые вернул SendInlineBotResultRequest."""
    from telethon.tl.custom import Message
    msgs = []
    for upd in getattr(updates, "updates", None) or []:
        for attr in ("message", "messages"):
            val = getattr(upd, attr, None)
            if not val:
                continue
            items = val if isinstance(val, list) else [val]
            for item in items:
                # голый TL Message (нет .to_dict у клиента) — оборачиваем
                if isinstance(item, Message):
                    msgs.append(item)
                else:
                    msgs.append(Message(item, client, None, None))
    if not msgs:
        return None
    return msgs[-1]

# ── Утилиты для построения HTML ───────────────────────────────────────────


def table(headers, rows, title=None):
    """Собирает HTML-таблицу.

    headers  — список строк (шапка) или None
    rows     — список списков ячеек
    title    — параграф-заголовок перед таблицей
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


def _escape(value):
    return _html.escape(str(value)) if value is not None else ""
