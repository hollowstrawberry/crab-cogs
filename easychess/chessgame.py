import asyncio
from io import BytesIO
import sys
import chess
import chess.engine
import chess.svg
import discord
from typing import List, Optional, Tuple
from redbot.core.data_manager import bundled_data_path

from easychess.base import BaseChessCog, BaseChessGame
from easychess.utils import svg_to_png
from easychess.views.bots_view import BotsView
from easychess.views.invite_view import InviteView
from easychess.views.game_view import GameView
from easychess.views.rematch_view import RematchView
from easychess.views.thinking_view import ThinkingView


COLOR_WHITE = 0xffffff
COLOR_BLACK = 0x000000
COLOR_TIE = 0x78B159


class ChessGame(BaseChessGame):
    def __init__(self, cog: BaseChessCog, players: List[discord.Member], channel: discord.TextChannel):
        super().__init__(cog, players, channel)
        self.limit = chess.engine.Limit(time=1.0)
        self.engine: Optional[chess.engine.UciProtocol] = None
        self.accepted = False
        self.cancelled = False
        self.surrendered: Optional[discord.Member] = None
    
    async def start_engine(self) -> chess.engine.UciProtocol:
        _, engine = await chess.engine.popen_uci([sys.executable, '-u', str(bundled_data_path(self.cog) / "sunfish.py")])
        return engine
    
    def accept(self):
        self.accepted = True

    def cancel(self, member: Optional[discord.Member]):
        if member in self.players:
            self.surrendered = member
        self.cancelled = True

    def is_cancelled(self):
        return self.cancelled

    def is_finished(self):
        return self.is_cancelled() or self.board.is_game_over()

    def move_user(self, san_or_uci: str) -> Tuple[bool, str]:
        try:
            try:
                move = self.board.parse_san(san_or_uci)
            except chess.InvalidMoveError:
                move = self.board.parse_uci(san_or_uci)
        except chess.InvalidMoveError:
            return False, "That move is not written correctly. Try again."
        except chess.IllegalMoveError:
            return False, "That move is illegal in the current state of the board. Try a different move."
        except chess.AmbiguousMoveError:
            return False, "That move may be interpreted in more than one way. Be specific."
        
        self.board.push(move)
        return True, ""
    
    async def move_engine(self):
        if not self.engine:
            self.engine = await self.start_engine()
        result = await self.engine.play(self.board, limit=self.limit)
        if result.move:
            self.board.push(result.move)
        else:
            raise ValueError("Engine failed to make a move")
        
    async def generate_board_image(self) -> BytesIO:
        lastmove = self.board.peek() if self.board.move_stack and not self.is_finished() else None
        check = self.board.king(self.board.turn) if self.board.is_check() else None
        svg = chess.svg.board(self.board, lastmove=lastmove, check=check, size=512)
        b = await asyncio.to_thread(svg_to_png, svg)
        return BytesIO(b or b'')

    async def update_message(self, interaction: Optional[discord.Interaction] = None):
        content = f"{self.players[0].mention} you're being invited to play chess." if not self.accepted else ""
        embed = discord.Embed()
        
        if all(m.bot for m in self.players):
            view = BotsView(self) if not self.is_finished() \
                else discord.ui.View(timeout=0)
        else:
            view = InviteView(self) if not self.accepted \
                else RematchView(self) if self.is_finished() \
                else ThinkingView() if self.member(self.board.turn).bot and not all(member.bot for member in self.players) \
                else GameView(self)
        filename = "board.png"
        file = discord.File(await self.generate_board_image(), filename)

        outcome = self.board.outcome()
        winner = None
        if outcome is None:
            if self.surrendered:
                winner = self.players[1] if self.players.index(self.surrendered) == 0 else self.players[0]
                embed.title = f"{winner.display_name} is the winner via surrender!"
                embed.set_thumbnail(url=winner.display_avatar.url)
            elif self.cancelled:
                embed.title = "The game was cancelled."
            elif self.accepted:
                turn = self.member(self.board.turn)
                embed.title = f"{turn.display_name}'s turn"
                embed.set_thumbnail(url=turn.display_avatar.url)
            else:
                embed.title="Waiting for confirmation..."
        elif outcome.winner is not None:
            winner = self.member(outcome.winner)
            embed.title = f"{winner.display_name} is the winner!"
            embed.set_thumbnail(url=winner.display_avatar.url)
        else:
            embed.title = "The game ended in a tie!"

        if outcome and outcome.winner is None:
            embed.color = COLOR_TIE
        elif winner:
            embed.color = COLOR_WHITE if self.players.index(winner) == 0 else COLOR_BLACK
        else:
            embed.color = COLOR_WHITE if self.board.turn == chess.WHITE else COLOR_BLACK
        
        embed.description = ""
        if winner == self.players[1]  or self.surrendered == self.players[0]:
            embed.description += "👑 "
        embed.description += f"`⬛` {self.players[1].mention}\n"
        if winner == self.players[0] or self.surrendered == self.players[1]:
            embed.description += "👑 "
        embed.description += f"`⬜` {self.players[0].mention}\n"


        embed.set_image(url=f"attachment://{filename}")

        if interaction:
            await interaction.edit_original_response(content=content, embed=embed, attachments=[file], view=view)
        else:
            old_message = self.message
            self.message = await self.channel.send(content=content, embed=embed, file=file, view=view)
            if old_message:
                try:
                    await old_message.delete()
                except discord.NotFound:
                    pass
