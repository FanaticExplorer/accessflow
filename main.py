import os

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
        for key, field in self.fields:
            message = message.replace(f"{{{key}}}", field.value or "")
        await interaction.response.send_message(message, ephemeral=True)


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


class AccessFlowBot(discord.Bot):
    def __init__(self):
        super().__init__(intents=intents)

    async def setup_hook(self):
        self.add_view(StartFlowView())


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
        color=discord.Color(int(start.embed.color.lstrip("#"), 16)),
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
