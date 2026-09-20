"""Тестовый модуль нового стиля NovaUB.

Команды объявляются декораторами — никакой register() не нужен.
Ядро само собирает команды, алиасы, описания, уровни доступа и кулдауны.
"""

from core.commands import command, inline, hook

__meta__ = {
    "name":        "NovaTest",
    "version":     "1.0.0",
    "author":      "NovaUB",
    "description": "Проверка нового стиля модулей.",
    "requires":    [],
}


@command(
    "ntest",
    aliases=["нт", "проверка"],
    desc="Проверка нового стиля команд",
    usage=".ntest",
    example=".ntest",
    cooldown=3,
    level="public",
)
async def ntest_cmd(client, message, args):
    """Тестовая команда"""
    await message.edit(
        "<blockquote><tg-emoji emoji-id=5897962422169243693>👻</tg-emoji> "
        "<b>NovaUB новый стиль работает!</b></blockquote>",
        parse_mode="html",
    )


@command("ntestowner", desc="Только владелец", level="owner")
async def ntestowner_cmd(client, message, args):
    await message.edit("<b>ok</b>", parse_mode="html")


@inline("ntest")
async def inline_ntest(event):
    builder = event.builder
    await event.answer([
        builder.article(
            title="NovaUB",
            description="Новый стиль модулей",
            text="<blockquote><b>NovaUB</b></blockquote>",
            parse_mode="html",
        )
    ])


@hook("startup")
async def on_startup(kernel):
    print("[NovaTest] startup hook")


@hook("shutdown")
async def on_shutdown(kernel):
    print("[NovaTest] shutdown hook")
