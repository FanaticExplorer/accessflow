import os
import re

import discord
from discord.abc import Messageable
from loguru import logger

from settings import QuestionSettings, Settings, load_settings

settings: Settings = load_settings()
intents = discord.Intents.default()

_INPUT_STYLES = {
    "short": discord.InputTextStyle.short,
    "long": discord.InputTextStyle.long,
}


def _parse_color(value: str) -> discord.Color:
    return discord.Color(int(value.lstrip("#"), 16))


def _sanitize_channel_name(name: str) -> str:
    name = re.sub(r"[^a-z0-9_-]", "", name.lower().replace(" ", "-"))
    return name[:100] or "ticket"


def build_review_embed(
    user: discord.User | discord.Member, answers: dict[str, str]
) -> discord.Embed:
    start = settings.start_screen
    embed = discord.Embed(title=start.review.title, color=_parse_color(start.review.color))
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    for question in settings.questions:
        embed.add_field(
            name=question.label, value=answers.get(question.key, "") or "—", inline=False
        )
    return embed


async def create_ticket_channel(
    interaction: discord.Interaction,
    embed: discord.Embed | None,
    applicant_name: str,
) -> discord.TextChannel | None:
    guild = interaction.guild
    if guild is None:
        return None
    ticket = settings.config.start_screen.ticket
    category = guild.get_channel(ticket.category)
    if not isinstance(category, discord.CategoryChannel):
        await interaction.followup.send(
            "Ticket category is not configured correctly.", ephemeral=True
        )
        return None
    name = _sanitize_channel_name(f"{ticket.name_prefix}{applicant_name}")
    try:
        channel = await guild.create_text_channel(name, category=category)
    except discord.Forbidden:
        await interaction.followup.send(
            "I don't have permission to create channels here.", ephemeral=True
        )
        return None
    if embed is not None:
        await channel.send(embed=embed, view=TicketView())
    return channel


class StartFlowModal(discord.ui.Modal):
    def __init__(self, questions: list[QuestionSettings], title: str):
        self.fields: list[tuple[str, discord.ui.InputText]] = []
        inputs: list[discord.ui.InputText] = []
        for question in questions:
            field = discord.ui.InputText(
                label=question.label,
                placeholder=question.placeholder or None,
                style=_INPUT_STYLES[question.style],
                required=question.required,
                min_length=question.min_length,
                max_length=question.max_length,
                value=question.value,
                custom_id=question.custom_id,
                row=question.row,
            )
            self.fields.append((question.key, field))
            inputs.append(field)
        super().__init__(*inputs, title=title)

    async def callback(self, interaction: discord.Interaction):
        message = settings.start_screen.confirmation_message
        answers: dict[str, str] = {}
        for key, field in self.fields:
            value = field.value or ""
            answers[key] = value
            message = message.replace(f"{{{key}}}", value)
        await interaction.response.send_message(message, ephemeral=True)
        if interaction.guild is None or interaction.user is None:
            return
        embed = build_review_embed(interaction.user, answers)
        if settings.config.start_screen.mode == "direct":
            channel = await create_ticket_channel(
                interaction, embed, interaction.user.display_name
            )
            if channel is not None:
                await interaction.followup.send(
                    f"Ticket created: {channel.mention}", ephemeral=True
                )
            return
        review_channel_id = settings.config.start_screen.review_channel
        if review_channel_id is None:
            return
        review_channel = interaction.guild.get_channel(review_channel_id)
        if not isinstance(review_channel, Messageable):
            logger.warning("review channel {id} not found", id=review_channel_id)
            return
        await review_channel.send(embed=embed, view=ReviewView())


class StartFlowView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label=settings.start_screen.button_label,
        custom_id="start_flow:get_started",
        style=discord.ButtonStyle.primary,
    )
    async def get_started(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(
            StartFlowModal(settings.questions, settings.start_screen.modal_title)
        )


class ReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label=settings.start_screen.buttons.accept,
        custom_id="review:accept",
        style=discord.ButtonStyle.success,
    )
    async def accept(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            settings.start_screen.buttons.accept_reply, ephemeral=True
        )

    @discord.ui.button(
        label=settings.start_screen.buttons.deny,
        custom_id="review:deny",
        style=discord.ButtonStyle.danger,
    )
    async def deny(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            settings.start_screen.buttons.deny_reply, ephemeral=True
        )

    @discord.ui.button(
        label=settings.start_screen.buttons.open_ticket,
        custom_id="review:open_ticket",
        style=discord.ButtonStyle.primary,
    )
    async def open_ticket(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        review_embed = interaction.message.embeds[0] if interaction.message else None
        applicant = (
            review_embed.author.name
            if review_embed and review_embed.author
            else (interaction.user.name if interaction.user else "ticket")
        )
        channel = await create_ticket_channel(interaction, review_embed, applicant)
        if channel is not None:
            await interaction.followup.send(
                f"Ticket created: {channel.mention}", ephemeral=True
            )


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label=settings.start_screen.buttons.accept,
        custom_id="ticket:accept",
        style=discord.ButtonStyle.success,
    )
    async def accept(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            settings.start_screen.buttons.accept_reply, ephemeral=True
        )

    @discord.ui.button(
        label=settings.start_screen.buttons.deny,
        custom_id="ticket:deny",
        style=discord.ButtonStyle.danger,
    )
    async def deny(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(
            settings.start_screen.buttons.deny_reply, ephemeral=True
        )


class AccessFlowBot(discord.Bot):
    def __init__(self):
        super().__init__(intents=intents)
        self._views_registered = False

    async def before_identify_hook(
        self, shard_id: int | None, *, initial: bool = False
    ) -> None:
        if initial and not self._views_registered:
            self._views_registered = True
            self.add_view(StartFlowView())
            self.add_view(ReviewView())
            self.add_view(TicketView())
        await super().before_identify_hook(shard_id, initial=initial)


bot = AccessFlowBot()


@bot.event
async def on_ready():
    logger.info("Logged in as {user}", user=bot.user)


@bot.slash_command(name="start_screen", description="Generate an embed with start message")
@discord.default_permissions(administrator=True)
@discord.guild_only()
async def start_screen(ctx: discord.ApplicationContext):
    start = settings.start_screen
    await ctx.respond(start.ack_message, ephemeral=True)
    embed = discord.Embed(
        title=start.embed.title,
        description=start.embed.description,
        color=_parse_color(start.embed.color),
    )
    if start.embed.image:
        embed.set_image(url=start.embed.image)
    if isinstance(ctx.channel, Messageable):
        await ctx.channel.send(embed=embed, view=StartFlowView())


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set")
    bot.run(token)


if __name__ == "__main__":
    main()
