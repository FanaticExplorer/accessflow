import re
from datetime import datetime, timedelta, timezone
from typing import Literal

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


def build_ticket_message_embed(applicant: str) -> discord.Embed:
    tm = settings.start_screen.review.ticket
    embed = discord.Embed(
        title=tm.title.replace("{user}", applicant),
        description=tm.description.replace("{user}", applicant),
        color=parse_color(tm.color),
    )
    if tm.image:
        embed.set_image(url=tm.image)
    return embed


def _timestamps(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    ts = int(dt.timestamp())
    return f"<t:{ts}:f>\n<t:{ts}:R>"


def parse_timezone(value: str) -> timezone:
    if value == "UTC":
        return timezone.utc
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", value)
    if match is None:
        raise ValueError(f"invalid timezone {value!r}")
    sign = 1 if match.group(1) == "+" else -1
    offset = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    return timezone(sign * offset)


def build_decision_footer(
    status: Literal["accepted", "denied", "deleted"], user: str
) -> str:
    start = settings.start_screen
    template = {
        "accepted": start.review.accepted_footer,
        "denied": start.review.denied_footer,
        "deleted": start.review.deleted_footer,
    }[status]
    text = template.replace("{user}", user)
    now = datetime.now(parse_timezone(settings.config.start_screen.timezone))
    label = settings.config.start_screen.timezone
    return f"{text}\n{now.strftime('%Y-%m-%d %H:%M')} {label}"


def build_user_copy_embed(answers: dict[str, str]) -> discord.Embed:
    copy = settings.start_screen.review.copy_embed
    embed = discord.Embed(title=copy.title, color=parse_color(copy.color))
    for question in settings.questions:
        embed.add_field(
            name=question.label, value=answers.get(question.key, "") or "—", inline=False
        )
    return embed


def build_review_embed(
    user: discord.User | discord.Member, answers: dict[str, str]
) -> discord.Embed:
    start = settings.start_screen
    embed = discord.Embed(title=start.review.title, color=parse_color(start.review.color))
    embed.set_author(name=f"{user.display_name} ({user.id})")
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(
        name=start.review.user_label,
        value=f"{user.display_name} {user.mention}",
        inline=False,
    )
    embed.add_field(
        name=start.review.created_label,
        value=_timestamps(user.created_at),
        inline=False,
    )
    joined = user.joined_at if isinstance(user, discord.Member) else None
    embed.add_field(
        name=start.review.joined_label,
        value=_timestamps(joined),
        inline=False,
    )
    for question in settings.questions:
        embed.add_field(
            name=question.label, value=answers.get(question.key, "") or "—", inline=False
        )
    return embed
