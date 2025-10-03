import discord
from datetime import datetime
from typing import Dict, Optional
from redbot.core import commands, Config
from redbot.core.bot import Red
from minigames.minigame import Minigame
from minigames.replace_view import ReplaceView
from minigames.tictactoe import TicTacToeGame

TIME_LIMIT = 0


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
        
        # Game already exists
        if ctx.channel.id in self.games and not self.games[ctx.channel.id].is_finished():
            old_game = self.games[ctx.channel.id]
            if (datetime.now() - old_game.last_interacted).total_seconds() > 60 * TIME_LIMIT:
                async def callback():
                    nonlocal ctx, opponent, players, old_game
                    assert opponent and isinstance(ctx.channel, discord.TextChannel)
                    game = TicTacToeGame(players, ctx.channel)
                    if opponent.bot:
                        game.accepted = True
                    self.games[ctx.channel.id] = game
                    message = await ctx.send(content=game.get_content(), embed=game.get_embed(), view=game.get_view())
                    game.message = message
                    if old_game.message:
                        try:
                            await old_game.message.delete()
                        except discord.NotFound:
                            pass

                content = f"Someone else is playing a game in this channel, but more than {TIME_LIMIT} minutes have passed. Do you want to start a new game?"
                embed = discord.Embed(title="Confirmation", description=content, color=await self.bot.get_embed_color(ctx))
                return await ctx.reply(embed=embed, view=ReplaceView(self, callback, ctx.author, ctx.channel), ephemeral=True)
            
            else:
                return await ctx.reply("Someone else is already playing a game in this channel!", ephemeral=True)
            
        game = TicTacToeGame(players, ctx.channel)
        if opponent.bot:
            game.accepted = True
        self.games[ctx.channel.id] = game
        message = await ctx.reply(content=game.get_content(), embed=game.get_embed(), view=game.get_view(), allowed_mentions=discord.AllowedMentions.none())
        game.message = message
