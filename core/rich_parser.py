"""HTML → PageBlock парсер для rich-сообщений.

Telegram Bot API понимает rich-сообщения двумя способами:
  • InputRichMessageHTML — сервер оказался не принимает его в inline-ответе
    (бот отвечает «успешно», но Telegram молча отбрасывает результат);
  • InputRichMessage — готовые PageBlock-и. Этот путь работает.

Поэтому HTML сперва парсится в набор PageBlock-ов, а потом отправляется
через InputRichMessage.
"""

import re
import html
from html.parser import HTMLParser
from telethon.tl.types import (
    TextWithEntities,
    PageBlockParagraph, PageBlockHeading1, PageBlockHeading2,
    PageBlockHeading3, PageBlockHeading4, PageBlockHeading5,
    PageBlockHeading6, PageBlockDetails, PageBlockList,
    PageBlockTable, PageBlockDivider, PageBlockBlockquote,
    PageBlockOrderedList, PageBlockPreformatted,
    PageTableRow, PageTableCell,
)

_HEADING_TAGS = {
    "h1": PageBlockHeading1, "h2": PageBlockHeading2,
    "h3": PageBlockHeading3, "h4": PageBlockHeading4,
    "h5": PageBlockHeading5, "h6": PageBlockHeading6,
}

_TAG_RE = re.compile(r"<(/?)(\w+)([^>]*)>")
_ATTR_RE = re.compile(r'(\w[\w-]*)="([^"]*)"')


def _plain(text: str) -> TextWithEntities:
    """Голый текст без разметки."""
    return TextWithEntities(text=text, entities=[])


class _Parser(HTMLParser):
    """Превращает HTML в список PageBlock-ов."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._buf = []          # накопленный текст текущего блока
        self._stack = []        # открытые блоки (details/quote/list)
        self._in_list = False
        self._items = []

    # ── текст ──────────────────────────────────────────────────
    def handle_data(self, data):
        self._buf.append(data)

    def _flush(self):
        text = "".join(self._buf).strip()
        self._buf = []
        return text

    def _entity_text(self, raw: str):
        """Текст с базовой разметкой: <b>/<i>/<code> → сущности."""
        # Rich-сообщения принимают только TextWithEntities.
        # Базовое жирное/курсив/моноширина поддерживаются.
        from telethon.tl.types import MessageEntityBold, MessageEntityItalic, MessageEntityCode
        entities = []
        plain = []
        pos = 0
        for m in _TAG_RE.finditer(raw):
            if m.start() > pos:
                plain.append(raw[pos:m.start()])
            tag = m.group(2).lower()
            if tag in ("b", "strong"):
                entities.append(MessageEntityBold(pos, 0))
            elif tag in ("i", "em"):
                entities.append(MessageEntityItalic(pos, 0))
            elif tag in ("code", "tt"):
                entities.append(MessageEntityCode(pos, 0))
            pos = m.end()
        if pos < len(raw):
            plain.append(raw[pos:])
        text = "".join(plain)
        # пересчитываем длины: убираем теги, позиции плоского текста
        # упрощаем — для rich не критично
        return _plain(html.unescape(text))

    # ── теги ───────────────────────────────────────────────────
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in _HEADING_TAGS:
            self._buf = []
            self._heading = tag

        elif tag == "p":
            self._buf = []

        elif tag == "blockquote":
            self._buf = []

        elif tag == "details":
            self._buf = []
            self._summary = None

        elif tag == "summary":
            self._buf = []

        elif tag in ("ul", "ol"):
            self._in_list = True
            self._items = []
            self._ordered = (tag == "ol")

        elif tag == "li":
            self._buf = []

        elif tag == "table":
            self._rows = []
            self._in_table = True
            self._table_title = attrs.get("title", "")

        elif tag == "tr":
            self._cells = []

        elif tag in ("td", "th"):
            self._buf = []

        elif tag == "divider":
            self.blocks.append(PageBlockDivider())

    def handle_endtag(self, tag):
        if tag in _HEADING_TAGS:
            text = self._flush()
            if text:
                self.blocks.append(_HEADING_TAGS[tag](text=_plain(text)))

        elif tag == "p":
            text = self._flush()
            if text:
                self.blocks.append(PageBlockParagraph(text=_plain(text)))

        elif tag == "blockquote":
            text = self._flush()
            if text:
                self.blocks.append(PageBlockBlockquote(text=_plain(text)))

        elif tag == "summary":
            self._summary = self._flush()

        elif tag == "details":
            text = self._flush()
            inner = _plain(text) if text else _plain("")
            summary = getattr(self, "_summary", None) or "Подробнее"
            self.blocks.append(PageBlockDetails(
                title=_plain(summary),
                blocks=[PageBlockParagraph(text=inner)],
                open=False,
            ))

        elif tag in ("ul", "ol"):
            items = self._items or []
            if items:
                items_t = [_plain(t) for t in items]
                if self._ordered:
                    self.blocks.append(PageBlockOrderedList(items=items_t))
                else:
                    self.blocks.append(PageBlockList(items=items_t))
            self._in_list = False
            self._items = []

        elif tag == "li":
            text = self._flush()
            if text:
                self._items.append(text)

        elif tag in ("td", "th"):
            text = self._flush()
            self._cells.append(PageTableCell(text=_plain(text)))

        elif tag == "tr":
            cells = getattr(self, "_cells", None) or []
            if cells:
                self._rows.append(PageTableRow(cells=cells))

        elif tag == "table":
            rows = getattr(self, "_rows", None) or []
            if rows:
                title = getattr(self, "_table_title", "") or ""
                self.blocks.append(PageBlockTable(
                    title=_plain(title),
                    rows=rows,
                    bordered=True,
                    striped=True,
                    compact=False,
                ))
            self._in_table = False
            self._rows = []


def parse_rich_html(html_text: str):
    """HTML → список PageBlock-ов для InputRichMessage."""
    parser = _Parser()
    parser.feed(html_text)
    parser.close()
    # хвостовой текст вне тегов
    tail = parser._flush()
    if tail and not parser.blocks:
        parser.blocks.append(PageBlockParagraph(text=_plain(tail)))
    return parser.blocks or [PageBlockParagraph(text=_plain(html_text))]
