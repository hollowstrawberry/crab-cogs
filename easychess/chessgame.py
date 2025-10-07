import asyncio
import logging
import discord
from io import BytesIO
from typing import List, Optional, Tuple
from datetime import datetime

import chess
import chess.engine
import chess.svg

from easychess.base import BaseChessCog, BaseChessGame
from easychess.utils import svg_to_png
from easychess.views.bots_view import BotsView
from easychess.views.invite_view import InviteView
from easychess.views.game_view import GameView
from easychess.views.rematch_view import RematchView
from easychess.views.thinking_view import ThinkingView

log = logging.getLogger("red.crab-cogs.easychess")

COLOR_WHITE = 0xffffff
COLOR_BLACK = 0x000000
COLOR_TIE = 0x78B159


class ChessGame(BaseChessGame):
    def __init__(self, cog: BaseChessCog, players: List[discord.Member], channel: discord.TextChannel, initial_state: str = None, depth: Optional[int] = None):
        super().__init__(cog, players, channel, initial_state)
        self.limit = chess.engine.Limit(time=1.0, depth=depth)
        self.accepted = initial_state is not None
        self.cancelled = False
        self.surrendered: Optional[discord.Member] = None
        self.last_board = self.board.copy()
    
    def accept(self):
        self.accepted = True

    def is_cancelled(self):
        return self.cancelled

    def is_finished(self):
        return self.is_cancelled() or self.board.is_game_over()
    
    def last_capture(self) -> Optional[chess.Piece]:
        if not self.board.move_stack or not self.last_board.is_capture(self.board.peek()):
            return None
        return self.last_board.piece_at(self.board.peek().to_square)
    
    async def cancel(self, member: Optional[discord.Member]):
        if member in self.players:
            self.surrendered = member
        self.cancelled = True
        await self.update_state()
    
    async def do_move(self, move: chess.Move):
        if self.board.move_stack:
            self.last_board.push(self.board.peek())
        self.board.push(move)
        self.last_interacted = datetime.now()
        await self.update_state()

    async def update_state(self):
        if self.is_finished():
            if self.cog.games.get(self.channel.id) == self:
                del self.cog.games[self.channel.id]
            await self.cog.config.channel(self.channel).clear()
        else:
            await self.cog.config.channel(self.channel).game.set(self.board.fen())
            await self.cog.config.channel(self.channel).players.set([player.id for player in self.players])

    async def move_user(self, san_or_uci: str) -> Tuple[bool, str]:
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
        
        await self.do_move(move)
        return True, ""
    
    async def move_engine(self):
        assert self.cog.engine
        result = await self.cog.engine.play(self.board, limit=self.limit)
        if result.move:
            await self.do_move(result.move)
        else:
            raise ValueError("Engine failed to make a move")
        
    async def generate_board_image(self) -> BytesIO:
        is_finished = self.is_finished()
        lastmove = self.board.peek() if self.board.move_stack and not is_finished else None
        check = self.board.king(self.board.turn) if self.board.is_check() and not is_finished else None
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
        last_capture = self.last_capture()
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

        if outcome and outcome.winner is None or self.is_cancelled():
            embed.color = COLOR_TIE
        elif winner:
            embed.color = COLOR_WHITE if self.players.index(winner) == 0 else COLOR_BLACK
        else:
            embed.color = COLOR_WHITE if self.board.turn == chess.WHITE else COLOR_BLACK
        
        embed.description = ""
        if winner == self.players[1] or self.surrendered == self.players[0]:
            embed.description += "👑 "
        embed.description += f"`⬛` {self.players[1].mention}"
        if last_capture and last_capture.color == chess.WHITE and not outcome and not self.is_cancelled():
            embed.description += f" captured **{last_capture.unicode_symbol(invert_color=True)}**"

        if winner == self.players[0] or self.surrendered == self.players[1]:
            embed.description += "👑 "
        embed.description += f"\n`⬜` {self.players[0].mention}"
        if last_capture and last_capture.color == chess.BLACK and not outcome and not self.is_cancelled():
            embed.description += f" captured **{last_capture.unicode_symbol()}**"

        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text=f"Turn {self.board.fullmove_number}")

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

        self.view = view
        await self.cog.config.channel(self.channel).message.set(self.message.id if self.message else 0)
