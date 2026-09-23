"""HTML → PageBlock парсер для rich-сообщений.

Telegram Bot API понимает rich-сообщения двумя способами:
  • InputRichMessageHTML — сервер его не принимает в inline-ответе
    (бот отвечает «успешно», но Telegram молча отбрасывает результат);
  • InputRichMessage — готовые PageBlock-и. Этот путь работает.

Поэтому HTML сперва парсится в набор PageBlock-ов, а потом отправляется
через InputRichMessage.

Важный нюанс: текст в PageBlock-ах — это TypeRichText, а не
TextWithEntities. То есть TextPlain / TextBold / TextItalic / TextConcat,
а не MessageEntity-подобная структура.
"""

import re
from html.parser import HTMLParser
from telethon.tl.types import (
    TextPlain, TextFixed, TextBold, TextItalic, TextConcat,
    PageBlockParagraph, PageBlockHeading1, PageBlockHeading2,
    PageBlockHeading3, PageBlockHeading4, PageBlockHeading5,
    PageBlockHeading6, PageBlockDetails, PageBlockList,
    PageBlockTable, PageBlockDivider, PageBlockBlockquote,
    PageBlockOrderedList, PageBlockPreformatted,
    PageTableRow, PageTableCell,
    PageListItemText, PageListOrderedItemText,
)

_HEADING_TAGS = {
    "h1": PageBlockHeading1, "h2": PageBlockHeading2,
    "h3": PageBlockHeading3, "h4": PageBlockHeading4,
    "h5": PageBlockHeading5, "h6": PageBlockHeading6,
}

# Форматирование внутри инлайн-текста: <b> <i> <code>
_FMT_RE = re.compile(r"<(/?)(b|strong|i|em|code|tt)(\s[^>]*)?>")
# Все HTML-теги (для вырезания при получении «голого» текста)
_ANY_TAG_RE = re.compile(r"<[^>]*>")


def _plain(raw: str) -> TextPlain:
    """Голый текст, теги вырезаются."""
    return TextPlain(text=_ANY_TAG_RE.sub("", raw))


def _rich_text(raw: str):
    """Инлайн-текст с <b>/<i>/<code> → TextConcat из TextPlain/TextBold/..."""
    # Разбиваем на сегменты [текст, «открылся тег X», «закрылся тег X»]
    pos = 0
    parts = []          # [(text, {bold,italic,fixed})]
    open_stack = []     # [(kind, start_index_in_parts)]

    def _emit(text: str, flags: set):
        if text:
            parts.append((text, flags))

    for m in _FMT_RE.finditer(raw):
        if m.start() > pos:
            _emit(raw[pos:m.start()], set(k for k, _s in open_stack))
        closing, kind, _a = m.group(1), m.group(2).lower(), m.group(3)
        if closing:
            # снять последний открытый того же вида
            for i in range(len(open_stack) - 1, -1, -1):
                if open_stack[i][0] == kind:
                    open_stack.pop(i)
                    break
        else:
            open_stack.append((kind, len(parts)))
        pos = m.end()
    if pos < len(raw):
        _emit(raw[pos:], set(k for k, _s in open_stack))

    if not parts:
        return TextPlain(text="")
    if len(parts) == 1:
        text, flags = parts[0]
        if not flags:
            return TextPlain(text=text)
        return _wrap(text, flags)
    return TextConcat(texts=[_wrap(t, f) for t, f in parts])


def _wrap(text: str, flags: set):
    cls = None
    if "b" in flags:
        cls = TextBold
    elif "i" in flags:
        cls = TextItalic
    elif "code" in flags:
        cls = TextFixed
    if cls is None:
        return TextPlain(text=text)
    return cls(text=text)


class _Parser(HTMLParser):
    """Превращает HTML в список PageBlock-ов."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._buf = []             # сырой буфер текущего блока (с тегами)
        self._expect = None        # какой блок сейчас собираем
        self._summary = None       # <details>
        self._items = []           # списки
        self._ordered = False
        self._rows = []            # таблица
        self._cells = []
        self._table_title = ""
        self._cell_is_header = False
        self._block_stack = []     # вложенные блоки (внутри <details>)

    def handle_data(self, data):
        self._buf.append(data)

    def _flush_raw(self) -> str:
        raw = "".join(self._buf)
        self._buf = []
        return raw

    def _flush_plain(self) -> str:
        return _ANY_TAG_RE.sub("", self._flush_raw()).strip()

    def _add_block(self, block):
        if self._block_stack:
            self._block_stack[-1].append(block)
        else:
            self.blocks.append(block)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in _HEADING_TAGS or tag in ("p", "blockquote"):
            self._buf = []
            self._expect = tag

        elif tag == "details":
            self._buf = []
            self._expect = "details"
            self._summary = None
            self._block_stack.append([])

        elif tag == "summary":
            self._buf = []

        elif tag in ("ul", "ol"):
            self._buf = []
            self._expect = tag
            self._ordered = (tag == "ol")
            self._items = []

        elif tag == "li":
            self._buf = []

        elif tag == "table":
            self._buf = []
            self._expect = "table"
            self._rows = []
            self._cells = []
            self._table_title = attrs.get("title", "")

        elif tag == "tr":
            self._cells = []

        elif tag in ("td", "th"):
            self._buf = []
            self._cell_is_header = (tag == "th")

        elif tag == "divider":
            self._add_block(PageBlockDivider())

    def handle_endtag(self, tag):
        if tag in _HEADING_TAGS:
            text = self._flush_plain()
            if text:
                self._add_block(_HEADING_TAGS[tag](text=_plain(text)))

        elif tag == "p":
            text = self._flush_plain()
            if text:
                self._add_block(PageBlockParagraph(text=_rich_text(text)))

        elif tag == "blockquote":
            text = self._flush_plain()
            if text:
                self._add_block(PageBlockBlockquote(
                    text=_rich_text(text), caption=TextPlain(text="")))

        elif tag == "summary":
            self._summary = self._flush_plain()

        elif tag == "details":
            inner = self._block_stack.pop() if self._block_stack else []
            text = self._flush_plain()
            if text and not inner:
                inner = [PageBlockParagraph(text=_plain(text))]
            if not inner:
                inner = [PageBlockParagraph(text=TextPlain(text=""))]
            summary = self._summary or "Подробнее"
            self._add_block(PageBlockDetails(
                title=_plain(summary),
                blocks=inner,
                open=False,
            ))

        elif tag in ("ul", "ol"):
            if self._items:
                if self._ordered:
                    items = [PageListOrderedItemText(text=_plain(t))
                             for t in self._items if t]
                    if items:
                        self._add_block(PageBlockOrderedList(items=items))
                else:
                    items = [PageListItemText(text=_plain(t))
                             for t in self._items if t]
                    if items:
                        self._add_block(PageBlockList(items=items))
            self._expect = None

        elif tag == "li":
            text = self._flush_plain()
            if text:
                self._items.append(text)

        elif tag in ("td", "th"):
            text = self._flush_plain()
            self._cells.append(PageTableCell(
                text=_plain(text) if text else None,
                header=self._cell_is_header or None,
            ))

        elif tag == "tr":
            if self._cells:
                self._rows.append(PageTableRow(cells=self._cells))
            self._cells = []

        elif tag == "table":
            if self._rows:
                self._add_block(PageBlockTable(
                    title=_plain(self._table_title or ""),
                    rows=self._rows,
                    striped=True,
                ))
            self._expect = None


def parse_rich_html(html_text: str):
    """HTML → список PageBlock-ов для InputRichMessage."""
    parser = _Parser()
    parser.feed(html_text)
    parser.close()
    tail = parser._flush_plain()
    if tail and not parser.blocks:
        parser.blocks.append(PageBlockParagraph(text=_plain(tail)))
    return parser.blocks or [PageBlockParagraph(text=_plain(html_text))]
