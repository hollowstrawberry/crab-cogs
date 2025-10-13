import logging
import discord
from typing import List, Optional, Union
from datetime import datetime

from redbot.core import commands, app_commands, bank
from redbot.core.bot import Red

from simplecheckers.base import BaseCheckersCog
from simplecheckers.checkersgame import CheckersGame
from simplecheckers.views.bots_view import BotsView
from simplecheckers.views.game_view import GameView
from simplecheckers.views.replace_view import ReplaceView

log = logging.getLogger("red.crab-cogs.simplecheckers")

TIME_LIMIT = 0 # minutes
VARIANT = "english"
STARTING = "Starting game..."


class SimpleCheckers(BaseCheckersCog):
    """Play Checkers/Draughts against your friends or the bot."""

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
                game = CheckersGame(self, players, channel, config["variant"], config["game"], config["time"], config["bet"])
                self.games[channel.id] = game
                view = BotsView(game) if all(p.bot for p in players) else GameView(game)
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

    async def is_economy_enabled(self, guild: discord.Guild) -> bool:
        economy = self.bot.get_cog("Economy")
        return economy is not None and not await self.bot.cog_disabled_in_guild(economy, guild)


    async def checkers_new(self, ctx: Union[commands.Context, discord.Interaction], opponent: Optional[discord.Member], bet: Optional[int]):
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        assert ctx.guild and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
        
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message
        opponent = opponent or ctx.guild.me
        players = [author, opponent] if opponent.bot else [opponent, author]

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
                    nonlocal ctx, players, author, opponent, old_game
                    assert opponent and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
                    await old_game.cancel(author)
                    await old_game.update_message()
                    game = CheckersGame(self, players, ctx.channel, VARIANT, bet=bet or 0)
                    if opponent.bot:
                        await game.start()
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
        game = CheckersGame(self, players, ctx.channel, VARIANT, bet=bet or 0)
        if opponent.bot:
            await game.start()
        self.games[ctx.channel.id] = game

        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(STARTING, ephemeral=True)
        elif ctx.interaction:
            await ctx.interaction.response.send_message(STARTING, ephemeral=True)

        await game.update_message()


    async def checkers_bots(self, ctx: commands.Context, opponent: discord.Member, depth: Optional[int] = None):
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
            
        game = CheckersGame(self, [ctx.guild.me, opponent], ctx.channel, VARIANT)
        await game.start()
        self.games[ctx.channel.id] = game

        if ctx.interaction:
            await ctx.interaction.response.send_message(STARTING, ephemeral=True)
        await game.update_message()


    @commands.command(name="checkers", aliases=["draughts"])
    @commands.guild_only()
    async def chess_new_cmd(self, ctx: commands.Context, opponent: Optional[discord.Member] = None, bet: Optional[int] = None):
        """Play a game of Checkers/Draughts against a friend or the bot."""
        assert ctx.guild
        await self.checkers_new(ctx, opponent, bet)

    @commands.command(name="checkersbots", aliases=["draughtsbots"])
    @commands.guild_only()
    async def chess_bots_cmd(self, ctx: commands.Context, opponent: discord.Member):
        """Make bots play Checkers/Draughts against each other."""
        await self.checkers_bots(ctx, opponent)


    app_chess = app_commands.Group(name="checkers", description="Play Checkers/Draughts on Discord!")

    @app_chess.command(name="new")
    @app_commands.describe(opponent="Invite someone to play, or play against the bot by default.", bet="Optionally, bet an amount of currency.")
    @app_commands.guild_only()
    async def chess_new_app(self, interaction: discord.Interaction, opponent: Optional[discord.Member] = None, bet: Optional[int] = None):
        """Play a game of Checkers against a friend or the bot."""
        ctx = await commands.Context.from_interaction(interaction)
        command = self.bot.get_command("checkers")
        assert command
        if not await command.can_run(ctx, check_all_parents=True, change_permission_state=False):
            return await interaction.response.send_message("You're not allowed to do that here.", ephemeral=True)
        await self.checkers_new(ctx, opponent, bet)

    @app_chess.command(name="only_bots")
    @app_commands.describe(bot_opponent="A different bot for this one to play against.")
    @app_commands.guild_only()
    async def chess_bots_app(self, interaction: discord.Interaction, bot_opponent: discord.Member):
        """Make this bot play Checkers against another bot."""
        ctx = await commands.Context.from_interaction(interaction)
        command = self.bot.get_command("checkersbots")
        assert command
        if not await command.can_run(ctx, check_all_parents=True, change_permission_state=False):
            return await interaction.response.send_message("You're not allowed to do that here.", ephemeral=True)
        await self.checkers_bots(ctx, bot_opponent)


    @commands.group(name="setcheckers", aliases=["checkersset", "setdraughts", "draughtsset", "checkerset", "draughtset"])  # type: ignore
    @commands.admin_or_permissions(manage_guild=True)
    async def setcheckers(self, ctx: commands.Context):
        """Settings for Checkers."""
        pass

    @setcheckers.command(name="payout", aliases=["prize"])
    @commands.admin_or_permissions(manage_guild=True)
    async def setcheckers_payout(self, ctx: commands.Context, payout: Optional[int]):
        """Show or set the payout when winning Checkers against the bot."""
        assert ctx.guild
        currency = await bank.get_currency_name(ctx.guild)
        if payout is None:
            payout = await self.config.guild(ctx.guild).payout()
            return await ctx.send(f"Current payout for Checkers is {payout} {currency}.")
        if payout < 0:
            return await ctx.send("Payout must be a positive number or 0.")
        await self.config.guild(ctx.guild).payout.set(payout)
        await ctx.send(f"New payout for Checkers is {payout} {currency}.")
