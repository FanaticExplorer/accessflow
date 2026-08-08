import os

import discord
from discord.abc import Messageable
from loguru import logger

intents = discord.Intents.default()


class StartFlowModal(discord.ui.Modal):
    def __init__(self):
        self.name = discord.ui.InputText(
            label="What should we call you?",
            placeholder="Your name or nickname",
        )
        self.interest = discord.ui.InputText(
            label="What are you interested in?",
            placeholder="e.g. Python, design, gaming",
            required=False,
        )
        self.note = discord.ui.InputText(
            label="Anything else we should know?",
            style=discord.InputTextStyle.long,
            required=False,
        )
        super().__init__(self.name, self.interest, self.note, title="Get Started")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Thanks, {self.name.value}! Your answers were saved.",
            ephemeral=True,
        )


class StartFlowView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Get Started",
        custom_id="start_flow:get_started",
        style=discord.ButtonStyle.primary,
    )
    async def get_started(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(StartFlowModal())


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
    await ctx.respond("Welcome message sent!", ephemeral=True)
    embed = discord.Embed(
        title="Welcome to the server",
        description="Press the button below and answer few questions to get started!",
        color=discord.Color.random()
    )
    if isinstance(ctx.channel, Messageable):
        await ctx.channel.send(embed=embed, view=StartFlowView())


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set")
    bot.run(token)


if __name__ == "__main__":
    main()
