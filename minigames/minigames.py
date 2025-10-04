import logging
import discord
from typing import Dict, List, Optional, Type, Union
from datetime import datetime
from redbot.core import commands, Config
from redbot.core.bot import Red

from minigames.base import Minigame, BaseMinigameCog
from minigames.connect4 import ConnectFourGame
from minigames.tictactoe import TicTacToeGame
from minigames.views.replace_view import ReplaceView

log = logging.getLogger("red.crab-cogs.minigames")

TIME_LIMIT = 5 # minutes


class Minigames(BaseMinigameCog):
    """Games to play against your friends or the bot, like Tic-Tac-Toe and Connect 4."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.allowedguilds = set()
        self.games: Dict[int, Minigame] = {}
        self.config = Config.get_conf(self, identifier=7669699620)
        self.config.register_guild()

    @commands.hybrid_command(name="tictactoe", aliases=["ttt"])
    @commands.guild_only()
    async def tictactoe(self, ctx: commands.Context, opponent: Optional[discord.Member] = None):
        """
        Play a game of Tic-Tac-Toe against the bot or another user.
        """
        assert ctx.guild and isinstance(ctx.author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
        opponent = opponent or ctx.guild.me
        players = [ctx.author, opponent] if opponent.bot else [opponent, ctx.author]
        await self.base_minigame_cmd(TicTacToeGame, ctx, players, opponent.bot)

    @commands.hybrid_command(name="connect4", aliases=["c4"])
    @commands.guild_only()
    async def connectfour(self, ctx: commands.Context, opponent: Optional[discord.Member] = None):
        """
        Play a game of Connect 4 against the bot or another user.
        """
        assert ctx.guild and isinstance(ctx.author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
        opponent = opponent or ctx.guild.me
        players = [ctx.author, opponent] if opponent.bot else [opponent, ctx.author]
        await self.base_minigame_cmd(ConnectFourGame, ctx, players, opponent.bot)


    async def base_minigame_cmd(self,
                                game_cls: Type[Minigame],
                                ctx: Union[commands.Context, discord.Interaction],
                                players: List[discord.Member],
                                against_bot: bool,
                                ):
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message
        assert ctx.guild and isinstance(ctx.channel, discord.TextChannel) and isinstance(author, discord.Member)
        
        # Game already exists
        if ctx.channel.id in self.games and not self.games[ctx.channel.id].is_finished():
            old_game = self.games[ctx.channel.id]
            old_message = await ctx.channel.fetch_message(old_game.message.id) if old_game.message else None # re-fetch

            if old_message:
                if (datetime.now() - old_game.last_interacted).total_seconds() > 60 * TIME_LIMIT:
                    async def callback():
                        nonlocal ctx, players, old_game, against_bot
                        assert isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel) 
                        game = game_cls(self, players, ctx.channel)
                        if against_bot:
                            game.accept(author)
                        self.games[ctx.channel.id] = game
                        message = await ctx.channel.send(content=game.get_content(), embed=game.get_embed(), view=game.get_view())
                        game.message = message
                        if old_game.message:
                            try:
                                await old_game.message.delete()
                            except discord.NotFound:
                                pass

                    content = f"Someone else is playing a game in this channel, here: {old_message.jump_url}, but more than {TIME_LIMIT} minutes have passed since their last interaction. Do you want to start a new game?"
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
        game = game_cls(self, players, ctx.channel)
        if against_bot:
            game.accept(author)
        self.games[ctx.channel.id] = game
        message = await reply(content=game.get_content(), embed=game.get_embed(), view=game.get_view())
        game.message = message if isinstance(ctx, commands.Context) else await ctx.original_response() # type: ignore
