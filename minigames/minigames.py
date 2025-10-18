import logging
import discord
from typing import Dict, List, Optional, Type, Union
from datetime import datetime
from redbot.core import commands, app_commands, bank, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta

from minigames.base import Minigame, BaseMinigameCog
from minigames.connect4 import ConnectFourGame
from minigames.tictactoe import TicTacToeGame
from minigames.views.replace_view import ReplaceView

log = logging.getLogger("red.crab-cogs.minigames")

TIME_LIMIT = 5 # minutes


class Minigames(BaseMinigameCog):
    """
    Play Connect 4 and Tic-Tac-Toe against your friends or the bot.
    Earn currency and make bets with other players.
    """

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.allowedguilds = set()
        self.games: Dict[int, Minigame] = {}
        self.config = Config.get_conf(self, identifier=7669699620)
        default_config = {
            "connect4_payout": 100,
            "tictactoe_payout": 10
        }
        self.config.register_guild(**default_config)
        self.config.register_global(**default_config)

    async def is_economy_enabled(self, guild: discord.Guild) -> bool:
        economy = self.bot.get_cog("Economy")
        return economy is not None and not await self.bot.cog_disabled_in_guild(economy, guild)

    @commands.hybrid_command(name="tictactoe", aliases=["ttt"])
    @app_commands.describe(opponent="Invite another user to play.", bet="Optionally, bet an amount of currency.")
    @commands.guild_only()
    async def tictactoe(self, ctx: commands.Context, opponent: Optional[discord.Member] = None, bet: Optional[int] = None):
        """
        Play a game of Tic-Tac-Toe against the bot or another user.
        """
        assert ctx.guild and isinstance(ctx.author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
        opponent = opponent or ctx.guild.me
        players = [ctx.author, opponent] if opponent.bot else [opponent, ctx.author]
        await self.base_minigame_cmd(TicTacToeGame, ctx, players, opponent.bot, bet)

    @commands.hybrid_command(name="connect4", aliases=["c4"])
    @app_commands.describe(opponent="Invite another user to play.", bet="Optionally, bet an amount of currency.")
    @commands.guild_only()
    async def connectfour(self, ctx: commands.Context, opponent: Optional[discord.Member] = None, bet: Optional[int] = None):
        """
        Play a game of Connect 4 against the bot or another user.
        """
        assert ctx.guild and isinstance(ctx.author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
        opponent = opponent or ctx.guild.me
        players = [ctx.author, opponent] if opponent.bot else [opponent, ctx.author]
        await self.base_minigame_cmd(ConnectFourGame, ctx, players, opponent.bot, bet)


    async def base_minigame_cmd(self,
                                game_cls: Type[Minigame],
                                ctx: Union[commands.Context, discord.Interaction],
                                players: List[discord.Member],
                                against_bot: bool,
                                bet: Optional[int],
                                ):
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message
        assert ctx.guild and isinstance(ctx.channel, discord.TextChannel) and isinstance(author, discord.Member)

        if game_cls == TicTacToeGame:
            if await bank.is_global():
                payout = await self.config.tictactoe_payout()
            else:
                payout = await self.config.guild(ctx.guild).tictactoe_payout()
        elif game_cls == ConnectFourGame:
            if await bank.is_global():
                payout = await self.config.connect4_payout()
            else:
                payout = await self.config.guild(ctx.guild).connect4_payout()
        else:
            payout = None

        if bet is not None and not await self.is_economy_enabled(ctx.guild):
            return await reply("You can't bet currency as economy is not enabled in the bot. Please use this command again without a bet.", ephemeral=True)
        if bet is not None and against_bot:
            currency_name = await bank.get_currency_name(ctx.guild)
            return await reply(f"You can't bet against the bot. Instead, a prize of {payout} {currency_name} will be issued if you win. Please use this command again without a bet.", ephemeral=True)
        if bet is not None and not await bank.can_spend(author, bet):
            currency_name = await bank.get_currency_name(ctx.guild)
            return await reply(f"You don't have enough {currency_name} to make that bet.")

        if against_bot:
            bet = payout

        # Game already exists
        if ctx.channel.id in self.games and not self.games[ctx.channel.id].is_finished():
            old_game = self.games[ctx.channel.id]
            old_message = await ctx.channel.fetch_message(old_game.message.id) if old_game.message else None # re-fetch
            # Games only exist as long as their message is alive
            if old_message:
                seconds_passed = int((datetime.now() - old_game.last_interacted).total_seconds())
                if seconds_passed // 60 >= TIME_LIMIT:
                    async def callback():
                        nonlocal ctx, players, old_game, against_bot
                        assert isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel) 
                        await old_game.cancel(author)
                        game = game_cls(self, players, ctx.channel, bet or 0)
                        if against_bot:
                            game.accept(author)
                            await game.init()
                        self.games[ctx.channel.id] = game
                        message = await ctx.channel.send(content=await game.get_content(), embed=await game.get_embed(), view=await game.get_view())
                        game.message = message
                        if old_game.message:
                            try:
                                await old_game.message.delete()
                            except discord.NotFound:
                                pass

                    content = f"Someone else is playing a game in this channel, here: {old_message.jump_url}, " \
                              f"but {humanize_timedelta(seconds=seconds_passed)} have passed since their last interaction. Do you want to start a new game?"
                    embed = discord.Embed(title="Confirmation", description=content, color=await self.bot.get_embed_color(ctx.channel))
                    view = ReplaceView(self, callback, author)
                    message = await reply(embed=embed, view=view)
                    view.message = message if isinstance(ctx, commands.Context) else await ctx.original_response() # type: ignore
                    return
                
                else:
                    content = f"There is still an active game in this channel, here: {old_message.jump_url}\nTry again in a few minutes"
                    permissions = ctx.channel.permissions_for(author)
                    content += " or consider creating a thread." if permissions.create_public_threads or permissions.create_private_threads else "."
                    await reply(content, ephemeral=True)
                    return
        
        # New game
        game = game_cls(self, players, ctx.channel, bet or 0)
        if against_bot:
            game.accept(author)
            await game.init()
        self.games[ctx.channel.id] = game
        message = await reply(content=await game.get_content(), embed=await game.get_embed(), view=await game.get_view())
        game.message = message if isinstance(ctx, commands.Context) else await ctx.original_response() # type: ignore


    @commands.group(name="connect4set", aliases=["setconnect4", "c4set", "connectfourset"])  # type: ignore
    @commands.admin_or_permissions(manage_guild=True)
    @bank.is_owner_if_bank_global()
    async def setconnect4(self, _: commands.Context):
        """Settings for Connect 4."""
        pass

    @setconnect4.command(name="payout", aliases=["prize"])
    async def setconnect4_payout(self, ctx: commands.Context, payout: Optional[int]):
        """Show or set the payout when winning Connect 4 against the bot."""
        assert ctx.guild
        is_global = await bank.is_global()
        config_payout = self.config.connect4_payout if is_global else self.config.guild(ctx.guild).connect4_payout
        currency = await bank.get_currency_name(None if is_global else ctx.guild)
        if payout is None:
            payout = await config_payout()
            return await ctx.send(f"Current payout for Connect 4 is {payout} {currency}.")
        if payout < 0:
            return await ctx.send("Payout must be a positive number or 0.")
        await config_payout.set(payout)
        await ctx.send(f"New payout for Connect 4 is {payout} {currency}.")


    @commands.group(name="tictactoeset", aliases=["settictactoe", "tttset"])  # type: ignore
    @commands.admin_or_permissions(manage_guild=True)
    @bank.is_owner_if_bank_global()
    async def settictactoe(self, _: commands.Context):
        """Settings for Tic-Tac-Toe."""
        pass

    @settictactoe.command(name="payout", aliases=["prize"])
    async def settictactoe_payout(self, ctx: commands.Context, payout: Optional[int]):
        """Show or set the payout when winning Tic-Tac-Toe against the bot."""
        assert ctx.guild
        is_global = await bank.is_global()
        config_payout = self.config.tictactoe_payout if is_global else self.config.guild(ctx.guild).tictactoe_payout
        currency = await bank.get_currency_name(None if is_global else ctx.guild)
        if payout is None:
            payout = await config_payout()
            return await ctx.send(f"Current payout for Tic-Tac-Toe is {payout} {currency}.")
        if payout < 0:
            return await ctx.send("Payout must be a positive number or 0.")
        await config_payout.set(payout)
        await ctx.send(f"New payout for Tic-Tac-Toe is {payout} {currency}.")
