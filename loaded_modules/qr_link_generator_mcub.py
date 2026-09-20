# requires: qrcode[pil]
# author: @ItzNeedlemouseNB (ported to MCUB)
# version: 1.0.0
# description: Генерирует QR-код по ссылке.

from io import BytesIO
from urllib.parse import urlparse

import qrcode


def register(kernel):

    def _extract_url(text: str) -> str:
        if not text:
            return ""
        candidate = text.strip().split()[0].strip()
        if candidate.startswith("www."):
            candidate = f"https://{candidate}"
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
        return ""

    async def _get_link(event) -> str:
        from utils import get_args_raw
        args = get_args_raw(event)
        if args:
            link = _extract_url(args)
            if link:
                return link

        reply = await event.get_reply_message()
        if not reply:
            return ""

        sources = []
        if getattr(reply, "raw_text", None):
            sources.append(reply.raw_text)
        if getattr(reply, "message", None):
            sources.append(reply.message)

        entities = getattr(reply, "entities", None) or []
        for entity in entities:
            url = getattr(entity, "url", None)
            if url:
                sources.append(url)

        for source in sources:
            link = _extract_url(source)
            if link:
                return link

        return ""

    def _build_qr(link: str) -> BytesIO:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(link)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        buffer.name = "qr.png"
        buffer.seek(0)
        return buffer

    @kernel.register.command("qrlink")
    async def qrlink_cmd(event):
        """<ссылка> — Сгенерировать QR-код по ссылке из аргументов или из replied-сообщения"""
        link = await _get_link(event)
        if not link:
            await event.edit("<b>Укажи ссылку в команде или ответь на сообщение со ссылкой.</b>")
            return

        if not _extract_url(link):
            await event.edit("<b>Это не похоже на корректную ссылку.</b>")
            return

        await event.edit("<b>Генерирую QR-код...</b>")

        try:
            qr_file = _build_qr(link)
            from telethon.utils import get_peer_id
            chat_id = event.chat_id
            reply_to = getattr(event.message, "reply_to_msg_id", None)
            await kernel.client.send_file(
                chat_id,
                qr_file,
                caption=f"<b>QR-код для:</b> <code>{link}</code>",
                parse_mode="html",
                reply_to=reply_to,
            )
            await event.delete()
        except Exception as e:
            await kernel.handle_error(e, source="qrlink_cmd", event=event)
            await event.edit("<b>Не удалось сгенерировать QR-код.</b>")
