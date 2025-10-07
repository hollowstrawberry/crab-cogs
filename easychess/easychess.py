import logging
import discord
from typing import Dict, Optional, Union
from datetime import datetime
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red

from easychess.base import BaseChessCog
from easychess.chessgame import ChessGame
from easychess.views.replace_view import ReplaceView

log = logging.getLogger("red.crab-cogs.easychess")

TIME_LIMIT = 5 # minutes


class EasyChess(BaseChessCog):
    """Play Chess against your friends or the bot."""

    def __init__(self, bot: Red):
        super().__init__(bot)
        self.allowedguilds = set()
        self.games: Dict[int, ChessGame] = {}
        self.config = Config.get_conf(self, identifier=766969962064)
        self.config.register_guild()


    @commands.command(name="chess")
    async def chess_new(self, ctx: Union[commands.Context, discord.Interaction], opponent: Optional[discord.Member] = None):
        """Play a game of Chess against a friend or the bot."""
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        assert ctx.guild and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
        opponent = opponent or ctx.guild.me
        players = [author, opponent] if opponent.bot else [opponent, author]

        # Game already exists
        if ctx.channel.id in self.games and not self.games[ctx.channel.id].is_finished():
            old_game = self.games[ctx.channel.id]
            old_message = await ctx.channel.fetch_message(old_game.message.id) if old_game.message else None # re-fetch
            reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message

            if old_message:
                if (datetime.now() - old_game.last_interacted).total_seconds() > 60 * TIME_LIMIT:
                    async def callback():
                        nonlocal ctx, players, old_game, author, opponent
                        assert opponent and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel) 
                        game = ChessGame(self, players, ctx.channel)
                        if opponent.bot:
                            game.accept()
                        self.games[ctx.channel.id] = game
                        await game.update_message()

                    content = f"Someone else is playing Chess in this channel, here: {old_message.jump_url}, but more than {TIME_LIMIT} minutes have passed since their last interaction. Do you want to start a new game?"
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
        game = ChessGame(self, players, ctx.channel)
        if opponent.bot:
            game.accept()
        self.games[ctx.channel.id] = game

        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message("Starting game...", ephemeral=True)
        elif ctx.interaction:
            await ctx.interaction.response.send_message("Starting game...", ephemeral=True)

        await game.update_message()


    @commands.command(name="chessbots")
    async def chess_bots(self, ctx: commands.Context, opponent: discord.Member):
        """Make bots play Chess against each other"""
        assert ctx.guild and isinstance(ctx.channel, discord.TextChannel)
        if not opponent.bot or opponent == ctx.guild.me:
            return await ctx.send("Opponent must be a bot different from myself.")
        
        if ctx.channel.id in self.games and not self.games[ctx.channel.id].is_finished():
            old_game = self.games[ctx.channel.id]
            old_message = await ctx.channel.fetch_message(old_game.message.id) if old_game.message else None # re-fetch
            if old_message:
                return await ctx.send("There's an ongoing chess game in this channel, we can't interrupt it.")
            
        game = ChessGame(self, [ctx.guild.me, opponent], ctx.channel)
        game.accept()
        self.games[ctx.channel.id] = game

        await game.update_message()


    app_chess = app_commands.Group(name="chess", description="Play Chess on Discord!")

    @app_chess.command(name="new")
    async def chess_new_app(self, interaction: discord.Interaction, opponent: Optional[discord.Member] = None):
        """Play a game of Chess against a friend or the bot."""
        ctx = await commands.Context.from_interaction(interaction)
        await self.chess_new(ctx, opponent)


    @app_chess.command(name="bots")
    async def chess_bots_app(self, interaction: discord.Interaction, opponent: Optional[discord.Member] = None):
        """Make this bot play Chess against another bot."""
        ctx = await commands.Context.from_interaction(interaction)
        await self.chess_bots(ctx, opponent)