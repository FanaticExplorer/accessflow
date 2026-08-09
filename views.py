from typing import Literal

import discord
from discord.abc import Messageable
from loguru import logger

import db
from embeds import (
    build_decision_footer,
    build_review_embed,
    build_ticket_message_embed,
    build_user_copy_embed,
    sanitize_channel_name,
)
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
    with_buttons: bool = True,
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
    if with_buttons:
        return await channel.send(embed=embed, view=TicketView())
    return await channel.send(embed=embed)


async def _find_application(
    interaction: discord.Interaction,
) -> db.Application | None:
    application = None
    if interaction.message is not None:
        application = await db.get_by_message(interaction.message.id)
    if application is None and interaction.message is not None:
        application = await db.get_by_user_copy_message(interaction.message.id)
    if application is None and interaction.channel_id is not None:
        application = await db.get_by_ticket_channel(interaction.channel_id)
    return application


async def _sync_review_message(
    interaction: discord.Interaction,
    application: db.Application | None,
    message: discord.Message | None,
    footer: str,
) -> None:
    if application is None:
        return
    if message is not None and application.message_id == message.id:
        return
    review_channel_id = settings.config.start_screen.review.channel
    if review_channel_id is None:
        return
    channel = (
        interaction.guild.get_channel(review_channel_id)
        if interaction.guild is not None
        else None
    )
    if not isinstance(channel, Messageable):
        try:
            channel = await interaction.client.fetch_channel(review_channel_id)
        except discord.NotFound:
            return
    if not isinstance(channel, Messageable):
        return
    try:
        review_message = await channel.fetch_message(application.message_id)
    except (discord.NotFound, discord.Forbidden):
        return
    sync_view = ReviewView()
    sync_view.disable_all_items()
    if review_message.embeds:
        review_message.embeds[0].set_footer(text=footer)
        await review_message.edit(embed=review_message.embeds[0], view=sync_view)
    else:
        await review_message.edit(view=sync_view)
    sync_view = ReviewView()
    sync_view.disable_all_items()
    if review_message.embeds:
        review_message.embeds[0].set_footer(text=footer)
        await review_message.edit(embed=review_message.embeds[0], view=sync_view)
    else:
        await review_message.edit(view=sync_view)


async def _close_ticket_channel(
    interaction: discord.Interaction, application: db.Application
) -> None:
    channel_id = application.ticket_channel_id
    if channel_id is None or interaction.guild is None:
        return
    channel = interaction.guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        try:
            channel = await interaction.guild.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden):
            return
        if not isinstance(channel, discord.TextChannel):
            return
    try:
        await channel.delete(reason="Application decided")
    except (discord.NotFound, discord.Forbidden):
        return
    await db.clear_ticket_channel(application.message_id)


async def _grant_role(
    interaction: discord.Interaction, application: db.Application
) -> None:
    role_id = settings.config.start_screen.application.role_id
    if role_id is None or interaction.guild is None:
        return
    role = interaction.guild.get_role(role_id)
    if role is None:
        logger.warning("role {id} not found", id=role_id)
        return
    try:
        member = await interaction.guild.fetch_member(application.user_id)
        await member.add_roles(role, reason="Application accepted")
    except discord.NotFound:
        logger.warning("user {uid} not in guild", uid=application.user_id)
    except discord.Forbidden:
        logger.warning(
            "cannot grant role {id} to user {uid}", id=role_id, uid=application.user_id
        )


async def _notify_user(
    interaction: discord.Interaction,
    application: db.Application,
    status: Literal["accepted", "denied"],
    footer: str,
    reason: str | None,
) -> None:
    client = interaction.client
    user = client.get_user(application.user_id)
    if user is None:
        try:
            user = await client.fetch_user(application.user_id)
        except discord.NotFound:
            return
    copy_id = application.user_copy_message_id
    if copy_id is not None:
        try:
            dm = await user.create_dm()
            copy = await dm.fetch_message(copy_id)
        except (discord.Forbidden, discord.NotFound):
            copy = None
        if copy is not None:
            sync_view = ApplicationCopyView()
            sync_view.disable_all_items()
            if copy.embeds:
                copy.embeds[0].set_footer(text=footer)
                await copy.edit(embed=copy.embeds[0], view=sync_view)
            else:
                await copy.edit(view=sync_view)
    dm_settings = settings.start_screen.application.dm
    if status == "accepted":
        text = dm_settings.accepted.replace("{user}", application.username)
    elif reason:
        text = dm_settings.denied_with_reason.replace("{reason}", reason)
    else:
        text = dm_settings.denied
    try:
        await user.send(text)
    except discord.Forbidden:
        logger.warning(
            "cannot DM user {id} about {status}", id=application.user_id, status=status
        )


async def _decide(
    interaction: discord.Interaction,
    status: Literal["accepted", "denied", "deleted"],
    view: discord.ui.View | None,
    *,
    application: db.Application | None = None,
    reason: str | None = None,
) -> None:
    if application is None:
        application = await _find_application(interaction)
    if application is not None:
        await db.update_status(application.message_id, status)
    buttons = settings.start_screen.buttons
    reply = {
        "accepted": buttons.reply.accept,
        "denied": buttons.reply.deny,
        "deleted": buttons.reply.delete,
    }[status]
    message = interaction.message
    user = interaction.user.name if interaction.user else "unknown"
    footer = build_decision_footer(status, user)
    await interaction.response.defer(ephemeral=True)
    if message is not None:
        if view is None:
            review_channel_id = settings.config.start_screen.review.channel
            if review_channel_id is not None and message.channel.id == review_channel_id:
                view = ReviewView()
            else:
                view = TicketView()
        view.disable_all_items()
        if message.embeds:
            message.embeds[0].set_footer(text=footer)
            await message.edit(embed=message.embeds[0], view=view)
        else:
            await message.edit(view=view)
    await _sync_review_message(interaction, application, message, footer)
    await interaction.followup.send(reply, ephemeral=True)
    if application is not None:
        if status == "accepted":
            await _grant_role(interaction, application)
        if status in ("accepted", "denied"):
            await _notify_user(interaction, application, status, footer, reason)
        if status != "deleted":
            await _close_ticket_channel(interaction, application)


class DenyReasonModal(discord.ui.Modal):
    def __init__(self, message_id: int):
        modal = settings.start_screen.application.deny_modal
        super().__init__(title=modal.title, custom_id=f"deny_reason:{message_id}")
        self.add_item(
            discord.ui.InputText(
                label=modal.label,
                placeholder=modal.placeholder or None,
                style=discord.InputTextStyle.long,
                required=True,
                max_length=1000,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        reason = self.children[0].value or ""
        message_id = int((interaction.custom_id or "").split(":", 1)[1])
        application = await db.get_by_message(message_id)
        await _decide(
            interaction, "denied", None, application=application, reason=reason
        )


# (=^-ω-^=)
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
        if interaction.user is not None and await db.get_active_by_user(
            interaction.user.id
        ):
            await interaction.response.send_message(
                settings.start_screen.existing_application_message, ephemeral=True
            )
            return
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
        username = interaction.user.name
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
        review_channel_id = settings.config.start_screen.review.channel
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
        if settings.config.start_screen.application.send_copy:
            try:
                copy_embed = build_user_copy_embed(answers)
                if settings.config.start_screen.application.allow_delete:
                    copy = await interaction.user.send(
                        embed=copy_embed, view=ApplicationCopyView()
                    )
                else:
                    copy = await interaction.user.send(embed=copy_embed)
            except discord.Forbidden:
                logger.warning("cannot DM application copy to user {id}", id=user_id)
            else:
                await db.set_user_copy_message(sent.id, copy.id)


class StartFlowView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label=settings.start_screen.button_label,
        custom_id="start_flow:get_started",
        style=discord.ButtonStyle.primary,
    )
    async def get_started(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.user is not None and await db.get_active_by_user(
            interaction.user.id
        ):
            await interaction.response.send_message(
                settings.start_screen.existing_application_message, ephemeral=True
            )
            return
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
        await _decide(interaction, "accepted", ReviewView())

    @discord.ui.button(
        label=settings.start_screen.buttons.deny,
        custom_id="review:deny",
        style=discord.ButtonStyle.danger,
    )
    async def deny(self, button: discord.ui.Button, interaction: discord.Interaction):
        if settings.config.start_screen.application.require_deny_reason:
            application = await _find_application(interaction)
            if application is not None:
                await interaction.response.send_modal(
                    DenyReasonModal(application.message_id)
                )
                return
        await _decide(interaction, "denied", ReviewView())

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
        sent = await create_ticket_channel(
            interaction,
            build_ticket_message_embed(applicant),
            applicant,
            with_buttons=settings.config.start_screen.review.ticket_buttons,
        )
        if sent is not None:
            if application is not None:
                await db.set_ticket_channel(application.message_id, sent.channel.id)
            await interaction.followup.send(
                f"Ticket created: <#{sent.channel.id}>", ephemeral=True
            )


class ApplicationCopyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label=settings.start_screen.buttons.delete,
        custom_id="application:delete",
        style=discord.ButtonStyle.danger,
    )
    async def delete(self, button: discord.ui.Button, interaction: discord.Interaction):
        await _decide(interaction, "deleted", ApplicationCopyView())


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label=settings.start_screen.buttons.accept,
        custom_id="ticket:accept",
        style=discord.ButtonStyle.success,
    )
    async def accept(self, button: discord.ui.Button, interaction: discord.Interaction):
        await _decide(interaction, "accepted", TicketView())

    @discord.ui.button(
        label=settings.start_screen.buttons.deny,
        custom_id="ticket:deny",
        style=discord.ButtonStyle.danger,
    )
    async def deny(self, button: discord.ui.Button, interaction: discord.Interaction):
        if settings.config.start_screen.application.require_deny_reason:
            application = await _find_application(interaction)
            if application is not None:
                await interaction.response.send_modal(
                    DenyReasonModal(application.message_id)
                )
                return
        await _decide(interaction, "denied", TicketView())
