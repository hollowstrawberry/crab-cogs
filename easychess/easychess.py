import logging
import discord
from typing import Dict, Optional, Union
from datetime import datetime
from redbot.core import commands, Config
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

    @commands.group(name="chess", invoke_without_command=True)
    @commands.guild_only()
    async def chess(self, ctx: commands.Context, move: Optional[str]):
        current_game = self.games.get(ctx.channel.id, None)
        prefixes = await self.bot.get_valid_prefixes(ctx.guild)
        if not current_game:
            return await ctx.reply(f"Start a new game with `{prefixes[0]}chess new` (and optionally ping an opponent)", ephemeral=True)
        if not move:
            return await ctx.reply(f"Send chess moves in standard formats, example: `{prefixes[0]}chess Nc3` or `{prefixes[0]}chess b1c3`", ephemeral=True)
        if ctx.author not in current_game.players:
            return await ctx.reply(f"You're not a player in the current chess game!", ephemeral=True)
        if ctx.author != current_game.member(current_game.board.turn):
            return await ctx.reply(f"It's not your turn!", ephemeral=True)

        success, message = current_game.move_user(move)
        if not success:
            return await ctx.reply(message, ephemeral=True)
        await current_game.update_message()

        if current_game.member(current_game.board.turn).bot:
            await current_game.move_engine()
            await current_game.update_message()

    @chess.command(name="new")
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
            await ctx.response.send_message("Starting game...")
        await game.update_message()
