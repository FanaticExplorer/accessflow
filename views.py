from typing import Literal

import discord
from discord.abc import Messageable
from loguru import logger

import db
from embeds import build_review_embed, sanitize_channel_name
from settings import QuestionSettings, Settings, load_settings

settings: Settings = load_settings()

_INPUT_STYLES = {
    "short": discord.InputTextStyle.short,
    "long": discord.InputTextStyle.long,
}


async def create_ticket_channel(
    interaction: discord.Interaction,
    embed: discord.Embed | None,
    applicant_name: str,
) -> discord.Message | None:
    guild = interaction.guild
    if guild is None:
        return None
    ticket = settings.config.start_screen.ticket
    category = None
    if ticket.category is not None:
        category = guild.get_channel(ticket.category)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send(
                "Ticket category is not configured correctly.", ephemeral=True
            )
            return None
    name = sanitize_channel_name(f"{ticket.name_prefix}{applicant_name}")
    try:
        channel = await guild.create_text_channel(name, category=category)
    except discord.Forbidden:
        await interaction.followup.send(
            "I don't have permission to create channels here.", ephemeral=True
        )
        return None
    if embed is None:
        return None
    return await channel.send(embed=embed, view=TicketView())


async def _record_decision(
    interaction: discord.Interaction, status: Literal["accepted", "denied"]
) -> None:
    application = None
    if interaction.message is not None:
        application = await db.get_by_message(interaction.message.id)
    if application is None and interaction.channel_id is not None:
        application = await db.get_by_ticket_channel(interaction.channel_id)
    if application is not None:
        await db.update_status(application.message_id, status)


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
        user_id = interaction.user.id
        username = interaction.user.display_name
        if settings.config.start_screen.mode == "direct":
            sent = await create_ticket_channel(interaction, embed, username)
            if sent is not None:
                await db.save_application(
                    message_id=sent.id,
                    user_id=user_id,
                    username=username,
                    answers=answers,
                    ticket_channel_id=sent.channel.id,
                )
                await interaction.followup.send(
                    f"Ticket created: <#{sent.channel.id}>", ephemeral=True
                )
            return
        review_channel_id = settings.config.start_screen.review_channel
        if review_channel_id is None:
            return
        review_channel = interaction.guild.get_channel(review_channel_id)
        if not isinstance(review_channel, Messageable):
            logger.warning("review channel {id} not found", id=review_channel_id)
            return
        sent = await review_channel.send(embed=embed, view=ReviewView())
        await db.save_application(
            message_id=sent.id,
            user_id=user_id,
            username=username,
            answers=answers,
        )


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
        await _record_decision(interaction, "accepted")
        await interaction.response.send_message(
            settings.start_screen.buttons.accept_reply, ephemeral=True
        )

    @discord.ui.button(
        label=settings.start_screen.buttons.deny,
        custom_id="review:deny",
        style=discord.ButtonStyle.danger,
    )
    async def deny(self, button: discord.ui.Button, interaction: discord.Interaction):
        await _record_decision(interaction, "denied")
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
        message = interaction.message
        review_embed = message.embeds[0] if message is not None else None
        application = await db.get_by_message(message.id) if message is not None else None
        if application is not None:
            applicant = application.username
        elif review_embed is not None and review_embed.author is not None:
            applicant = review_embed.author.name
        else:
            applicant = interaction.user.name if interaction.user else "ticket"
        sent = await create_ticket_channel(interaction, review_embed, applicant)
        if sent is not None:
            if application is not None:
                await db.set_ticket_channel(application.message_id, sent.channel.id)
            await interaction.followup.send(
                f"Ticket created: <#{sent.channel.id}>", ephemeral=True
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
        await _record_decision(interaction, "accepted")
        await interaction.response.send_message(
            settings.start_screen.buttons.accept_reply, ephemeral=True
        )

    @discord.ui.button(
        label=settings.start_screen.buttons.deny,
        custom_id="ticket:deny",
        style=discord.ButtonStyle.danger,
    )
    async def deny(self, button: discord.ui.Button, interaction: discord.Interaction):
        await _record_decision(interaction, "denied")
        await interaction.response.send_message(
            settings.start_screen.buttons.deny_reply, ephemeral=True
        )
