import re

import discord

from settings import Settings, load_settings

settings: Settings = load_settings()


def parse_color(value: str) -> discord.Color:
    return discord.Color(int(value.lstrip("#"), 16))


def sanitize_channel_name(name: str) -> str:
    name = re.sub(r"[^a-z0-9_-]", "", name.lower().replace(" ", "-"))
    return name[:100] or "ticket"


def build_start_embed() -> discord.Embed:
    start = settings.start_screen
    embed = discord.Embed(
        title=start.embed.title,
        description=start.embed.description,
        color=parse_color(start.embed.color),
    )
    if start.embed.image:
        embed.set_image(url=start.embed.image)
    return embed


def build_review_embed(
    user: discord.User | discord.Member, answers: dict[str, str]
) -> discord.Embed:
    start = settings.start_screen
    embed = discord.Embed(title=start.review.title, color=parse_color(start.review.color))
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    for question in settings.questions:
        embed.add_field(
            name=question.label, value=answers.get(question.key, "") or "—", inline=False
        )
    return embed
