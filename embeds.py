import re
from datetime import datetime, timedelta, timezone
from typing import Literal

import discord

from settings import QuestionSettings, Settings, load_settings

settings: Settings = load_settings()


def question_answer_key(question: QuestionSettings, index: int) -> str:
    return question.custom_id or f"q{index}"


def parse_color(value: str) -> discord.Color:
    return discord.Color(int(value.lstrip("#"), 16))


def sanitize_channel_name(name: str) -> str:
    name = re.sub(r"[^a-z0-9_-]", "", name.lower().replace(" ", "-"))
    return name[:100] or "ticket"


# (=^･ｪ･^=)
def build_start_embed() -> discord.Embed:
    start = settings.start_screen
    embed = discord.Embed(
        title=start.welcome.title,
        description=start.welcome.description,
        color=parse_color(start.welcome.color),
    )
    if start.welcome.image:
        embed.set_image(url=start.welcome.image)
    if start.welcome.footer:
        embed.set_footer(text=start.welcome.footer)
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
        "accepted": start.application.accepted_footer,
        "denied": start.application.denied_footer,
        "deleted": start.application.deleted_footer,
    }[status]
    text = template.replace("{user}", user)
    now = datetime.now(parse_timezone(settings.config.start_screen.timezone))
    label = settings.config.start_screen.timezone
    return f"{text}\n{now.strftime('%Y-%m-%d %H:%M')} {label}"


def build_user_copy_embed(answers: dict[str, str]) -> discord.Embed:
    copy = settings.start_screen.application.copy_embed
    embed = discord.Embed(title=copy.title, color=parse_color(copy.color))
    for index, question in enumerate(settings.questions):
        embed.add_field(
            name=question.label,
            value=answers.get(question_answer_key(question, index), "") or "—",
            inline=False,
        )
    return embed


def build_review_embed(
    user: discord.User | discord.Member, answers: dict[str, str]
) -> discord.Embed:
    start = settings.start_screen
    embed = discord.Embed(
        title=start.application.embed.title,
        color=parse_color(start.application.embed.color),
    )
    embed.set_author(name=f"{user.name} ({user.id})")
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(
        name=start.application.user_label,
        value=f"{user.name} {user.mention}",
        inline=False,
    )
    embed.add_field(
        name=start.application.created_label,
        value=_timestamps(user.created_at),
        inline=False,
    )
    joined = user.joined_at if isinstance(user, discord.Member) else None
    embed.add_field(
        name=start.application.joined_label,
        value=_timestamps(joined),
        inline=False,
    )
    for index, question in enumerate(settings.questions):
        embed.add_field(
            name=question.label,
            value=answers.get(question_answer_key(question, index), "") or "—",
            inline=False,
        )
    return embed
