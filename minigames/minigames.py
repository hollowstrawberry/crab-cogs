import discord
from typing import Dict, List, Optional, Type
from datetime import datetime
from redbot.core import commands, Config
from redbot.core.bot import Red

from minigames.connect4 import ConnectFourGame
from minigames.base import Minigame
from minigames.views.replace_view import ReplaceView
from minigames.tictactoe import TicTacToeGame

TIME_LIMIT = 0 # minutes


class Minigames(commands.Cog):
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


    async def base_minigame_cmd(self, game_cls: Type[Minigame], ctx: commands.Context, players: List[discord.Member], against_bot: bool):
        assert ctx.guild and isinstance(ctx.author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
        
        # Game already exists
        if ctx.channel.id in self.games and not self.games[ctx.channel.id].is_finished():
            old_game = self.games[ctx.channel.id]

            if (datetime.now() - old_game.last_interacted).total_seconds() > 60 * TIME_LIMIT:
                async def callback():
                    nonlocal ctx, players, old_game, against_bot
                    assert isinstance(ctx.author, discord.Member) and isinstance(ctx.channel, discord.TextChannel) 
                    game = game_cls(players, ctx.channel)
                    if against_bot:
                        game.accept(ctx.author)
                    self.games[ctx.channel.id] = game
                    message = await ctx.send(content=game.get_content(), embed=game.get_embed(), view=game.get_view())
                    game.message = message
                    if old_game.message:
                        try:
                            await old_game.message.delete()
                        except discord.NotFound:
                            pass

                content = f"Someone else is playing a game in this channel, but more than {TIME_LIMIT} minutes have passed since their last interaction. Do you want to start a new game?"
                embed = discord.Embed(title="Confirmation", description=content, color=await self.bot.get_embed_color(ctx))
                view = ReplaceView(self, callback, ctx.author, ctx.channel)
                view.message = await ctx.reply(embed=embed, view=view, ephemeral=True)
                return
            
            else:
                # re-fetch message to make sure it wasn't deleted
                old_message = await ctx.channel.fetch_message(old_game.message.id) if old_game.message else None
                if old_message:
                    content = f"There is still an active game in this channel, here: {old_message.jump_url}\nTry again in a few minutes"
                    permissions = ctx.channel.permissions_for(ctx.author)
                    content += " or consider creating a thread." if permissions.create_public_threads or permissions.create_private_threads else "."
                    await ctx.reply(content, ephemeral=True)
                    return
        
        # New game
        game = game_cls(players, ctx.channel)
        if against_bot:
            game.accept(ctx.author)
        self.games[ctx.channel.id] = game
        message = await ctx.reply(content=game.get_content(), embed=game.get_embed(), view=game.get_view())
        game.message = message
