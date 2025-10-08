import logging
import discord
from typing import List, Union
from datetime import datetime

from redbot.core import commands
from redbot.core.bot import Red

from simplecheckers.base import BaseCheckersCog
from simplecheckers.checkersgame import CheckersGame
from simplecheckers.views.game_view import GameView
from simplecheckers.views.replace_view import ReplaceView

log = logging.getLogger("red.crab-cogs.simplecheckers")

TIME_LIMIT = 5 # minutes
VARIANT = "english"


class SimpleCheckers(BaseCheckersCog):
    """Play Checkers/Draughts against your friends."""

    def __init__(self, bot: Red):
        super().__init__(bot)

    async def cog_load(self):
        all_channels = await self.config.all_channels()
        for channel_id, config in all_channels.items():
            try:
                channel = self.bot.get_channel(channel_id)
                if not config["game"] or not isinstance(channel, discord.TextChannel):
                    continue
                players: List[discord.Member] = [channel.guild.get_member(user_id) for user_id in config["players"]] # type: ignore
                if any(player is None for player in players):
                    continue
                game = CheckersGame(self, players, channel, config["game"])
                self.games[channel.id] = game
                view = GameView(game)
                self.bot.add_view(view)
                game.view = view
                try:
                    game.message = await channel.fetch_message(config["message"])
                except discord.NotFound:
                    pass
            except Exception: # don't interrupt load sequence
                log.error(f"Parsing game in {channel_id}", exc_info=True)

    async def cog_unload(self):
        for game in self.games.values():
            if game.view:
                game.view.stop()


    async def checkers_new(self, ctx: Union[commands.Context, discord.Interaction], opponent: discord.Member):
        """Play a game of Checkers against a friend."""
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        assert ctx.guild and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
        
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message
        if opponent.bot:
            return await reply("You can't play against a bot, maybe one day!", ephemeral=True)
        players = [opponent, author]

        # Game already exists
        if ctx.channel.id in self.games and not self.games[ctx.channel.id].is_finished():
            old_game = self.games[ctx.channel.id]
            try:
                old_message = await ctx.channel.fetch_message(old_game.message.id) if old_game.message else None # re-fetch
            except discord.NotFound:
                old_message = None

            if not old_message:
                await old_game.update_message()
                old_message = old_game.message
                assert old_message

            minutes_passed = int((datetime.now() - old_game.last_interacted).total_seconds() // 60)
            if minutes_passed >= TIME_LIMIT:
                async def callback():
                    nonlocal ctx, players, author, old_game
                    assert opponent and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
                    await old_game.cancel(author)
                    await old_game.update_message()
                    game = CheckersGame(self, players, ctx.channel, VARIANT)
                    self.games[ctx.channel.id] = game
                    await game.update_message()

                content = f"Someone else is playing Checkers in this channel, here: {old_message.jump_url}, but {minutes_passed} minutes have passed since their last interaction. Do you want to start a new game?"
                embed = discord.Embed(title="Confirmation", description=content, color=await self.bot.get_embed_color(ctx.channel))
                view = ReplaceView(self, callback, author)
                message = await reply(embed=embed, view=view, ephemeral=True)
                view.message = message if isinstance(ctx, commands.Context) else await ctx.original_response() # type: ignore
                return
            
            else:
                content = f"There is still an active game in this channel, here: {old_message.jump_url}\nTry again in a few minutes"
                permissions = ctx.channel.permissions_for(author)
                content += " or consider creating a thread." if permissions.create_public_threads or permissions.create_private_threads else "."
                await reply(content, ephemeral=True)
                return
        
        # New game
        game = CheckersGame(self, players, ctx.channel, VARIANT)
        if opponent.bot:
            game.accept()
        self.games[ctx.channel.id] = game

        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message("Starting game...", ephemeral=True)
        elif ctx.interaction:
            await ctx.interaction.response.send_message("Starting game...", ephemeral=True)

        await game.update_message()


    @commands.hybrid_command(name="checkers")
    @commands.guild_only()
    async def checkers_new_cmd(self, ctx: commands.Context, opponent: discord.Member):
        """Play a game of Checkers against a friend."""
        await self.checkers_new(ctx, opponent)
