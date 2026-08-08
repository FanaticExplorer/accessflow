import os

import discord
from discord.abc import Messageable
from loguru import logger

import db
from embeds import build_start_embed
from settings import Settings, load_settings
from views import ReviewView, StartFlowView, TicketView

settings: Settings = load_settings()
intents = discord.Intents.default()


class AccessFlowBot(discord.Bot):
    def __init__(self):
        super().__init__(intents=intents)
        self._views_registered = False

    async def before_identify_hook(
        self, shard_id: int | None, *, initial: bool = False
    ) -> None:
        if initial and not self._views_registered:
            self._views_registered = True
            await db.init_db()
            self.add_view(StartFlowView())
            self.add_view(ReviewView())
            self.add_view(TicketView())
        await super().before_identify_hook(shard_id, initial=initial)

    async def close(self) -> None:
        await db.close_db()
        await super().close()


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
    if isinstance(ctx.channel, Messageable):
        await ctx.channel.send(embed=build_start_embed(), view=StartFlowView())


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set")
    bot.run(token)


if __name__ == "__main__":
    main()
