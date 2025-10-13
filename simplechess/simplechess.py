import sys
import logging
import discord
import chess.engine
from typing import List, Optional, Union
from datetime import datetime

from redbot.core import commands, app_commands, bank
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path

from simplechess.base import BaseChessCog
from simplechess.chessgame import ChessGame
from simplechess.views.bots_view import BotsView
from simplechess.views.game_view import GameView
from simplechess.views.replace_view import ReplaceView

log = logging.getLogger("red.crab-cogs.simplechess")

TIME_LIMIT = 5 # minutes
DEFAULT_DIFFICULTY = 5 # depth
STARTING = "Starting game..."


class SimpleChess(BaseChessCog):
    """Play Chess against your friends or the bot, or make bots play against each other."""

    def __init__(self, bot: Red):
        super().__init__(bot)

    async def cog_load(self):
        _, engine = await chess.engine.popen_uci([sys.executable, '-u', str(bundled_data_path(self) / "sunfish.py")])
        self.engine = engine
        await self.engine.ping()

        all_channels = await self.config.all_channels()
        for channel_id, config in all_channels.items():
            try:
                channel = self.bot.get_channel(channel_id)
                if not config["game"] or not isinstance(channel, discord.TextChannel):
                    continue
                players: List[discord.Member] = [channel.guild.get_member(user_id) for user_id in config["players"]] # type: ignore
                if any(player is None for player in players):
                    continue
                game = ChessGame(self, players, channel, config["game"], config["depth"], config["bet"])
                self.games[channel.id] = game
                view = BotsView(game) if all(player.bot for player in players) else GameView(game)
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
        if self.engine:
            await self.engine.quit()

    async def is_economy_enabled(self, guild: discord.Guild) -> bool:
        economy = self.bot.get_cog("Economy")
        return economy is not None and not await self.bot.cog_disabled_in_guild(economy, guild)


    async def chess_new(self, ctx: Union[commands.Context, discord.Interaction], opponent: Optional[discord.Member], depth: Optional[int] = None, bet: Optional[int] = 0):
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        assert ctx.guild and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
        opponent = opponent or ctx.guild.me
        players = [author, opponent] if opponent.bot else [opponent, author]
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message

        if bet is not None and not await self.is_economy_enabled(ctx.guild):
            return await reply("You can't bet currency as economy is not enabled in the bot. Please use this command again without a bet.", ephemeral=True)
        if bet is not None and opponent.bot:
            payout = await self.config.guild(ctx.guild).payout()
            return await reply(f"You can't bet against the bot. Instead, a prize of {payout} will be issued if you win. Please use this command again without a bet.", ephemeral=True)

        if opponent.bot:
            bet = await self.config.guild(ctx.guild).payout()

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
                    nonlocal ctx, players, author, old_game, old_message, opponent
                    assert opponent and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
                    await old_game.cancel(author)
                    await old_game.update_message()
                    game = ChessGame(self, players, ctx.channel, depth=depth, bet=bet or 0)
                    if opponent.bot:
                        game.accept()
                        await game.init()
                    self.games[ctx.channel.id] = game
                    await game.update_message()

                content = f"Someone else is playing Chess in this channel, here: {old_message.jump_url}, but {minutes_passed} minutes have passed since their last interaction. Do you want to start a new game?"
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
        game = ChessGame(self, players, ctx.channel, depth=depth, bet=bet or 0)
        if opponent.bot:
            game.accept()
            await game.init()
        self.games[ctx.channel.id] = game

        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(STARTING, ephemeral=True)
        elif ctx.interaction:
            await ctx.interaction.response.send_message(STARTING, ephemeral=True)

        await game.update_message()


    async def chess_bots(self, ctx: commands.Context, opponent: discord.Member, depth: Optional[int] = None):
        assert ctx.guild and isinstance(ctx.channel, discord.TextChannel)
        if not opponent.bot or opponent == ctx.guild.me:
            return await ctx.send("Opponent must be a bot different from myself.")
        
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
            
            return await ctx.send("There's an ongoing chess game in this channel, we can't interrupt it.")
            
        game = ChessGame(self, [ctx.guild.me, opponent], ctx.channel, depth=depth)
        game.accept()
        self.games[ctx.channel.id] = game

        if ctx.interaction:
            await ctx.interaction.response.send_message(STARTING, ephemeral=True)
        await game.update_message()


    @commands.command(name="chess")
    @commands.guild_only()
    async def chess_new_cmd(self, ctx: commands.Context, opponent: Optional[discord.Member] = None, bet: Optional[int] = None):
        """Play a game of Chess against a friend or the bot."""
        await self.chess_new(ctx, opponent, DEFAULT_DIFFICULTY, bet)

    @commands.command(name="chessbots")
    @commands.guild_only()
    async def chess_bots_cmd(self, ctx: commands.Context, opponent: discord.Member):
        """Make bots play Chess against each other."""
        await self.chess_bots(ctx, opponent, DEFAULT_DIFFICULTY)


    app_chess = app_commands.Group(name="chess", description="Play Chess on Discord!")

    @app_chess.command(name="new")
    @app_commands.describe(opponent="Invite someone to play, or play against the bot by default.",
                           bet="Against a player, optionally bet currency.",
                           difficulty="Against the bot. Hard by default.")
    @app_commands.choices(difficulty=[app_commands.Choice(name="Easy", value="1"),
                                      app_commands.Choice(name="Medium", value="3"),
                                      app_commands.Choice(name="Hard", value="5"),
                                      app_commands.Choice(name="Hardest", value="0")])
    @app_commands.guild_only()
    async def chess_new_app(self,
                            interaction: discord.Interaction,
                            opponent: Optional[discord.Member] = None,
                            bet: Optional[int] = None,
                            difficulty: str = f"{DEFAULT_DIFFICULTY}"):
        """Play a game of Chess against a friend or the bot."""
        ctx = await commands.Context.from_interaction(interaction)
        command = self.bot.get_command("chess")
        assert command
        if not await command.can_run(ctx, check_all_parents=True, change_permission_state=False):
            return await interaction.response.send_message("You're not allowed to do that here.", ephemeral=True)
        await self.chess_new(ctx, opponent, int(difficulty) or None, bet)

    @app_chess.command(name="bots")
    @app_commands.describe(opponent="A different bot for this one to play against.")
    @app_commands.guild_only()
    async def chess_bots_app(self, interaction: discord.Interaction, opponent: discord.Member):
        """Make this bot play Chess against another bot."""
        ctx = await commands.Context.from_interaction(interaction)
        command = self.bot.get_command("chessbots")
        assert command
        if not await command.can_run(ctx, check_all_parents=True, change_permission_state=False):
            return await interaction.response.send_message("You're not allowed to do that here.", ephemeral=True)
        await self.chess_bots(ctx, opponent, DEFAULT_DIFFICULTY)


    @commands.group(name="setchess", aliases=["chesset",  "chessset"])  # type: ignore
    @commands.admin_or_permissions(manage_guild=True)
    async def setchess(self, ctx: commands.Context):
        """Settings for Chess."""
        pass

    @setchess.command(name="payout", aliases=["prize"])
    @commands.admin_or_permissions(manage_guild=True)
    async def setchess_payout(self, ctx: commands.Context, payout: Optional[int]):
        """Show or set the payout when winning Chess against the bot."""
        assert ctx.guild
        currency = await bank.get_currency_name(ctx.guild)
        if payout is None:
            payout = await self.config.guild(ctx.guild).payout()
            return await ctx.send(f"Current payout for Chess is {payout} {currency}.")
        if payout < 0:
            return await ctx.send("Payout must be a positive number or 0.")
        await self.config.guild(ctx.guild).payout.set(payout)
        await ctx.send(f"New payout for Chess is {payout} {currency}.")
