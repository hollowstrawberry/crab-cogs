import asyncio
import logging
import discord
import chess
import chess.svg
from io import BytesIO
from typing import List, Optional, Tuple
from datetime import datetime
from redbot.core import bank

from simplechess.base import BaseChessCog, BaseChessGame
from simplechess.utils import svg_to_png
from simplechess.views.bots_view import BotsView
from simplechess.views.invite_view import InviteView
from simplechess.views.game_view import GameView
from simplechess.views.rematch_view import RematchView
from simplechess.views.thinking_view import ThinkingView

log = logging.getLogger("red.crab-cogs.simplechess")

COLOR_WHITE = 0xffffff
COLOR_BLACK = 0x000000
COLOR_TIE = 0x78B159


class ChessGame(BaseChessGame):
    def __init__(self,
                 cog: BaseChessCog,
                 players: List[discord.Member],
                 channel: discord.TextChannel,
                 initial_state: str = None,
                 depth: Optional[int] = None,
                 bet: int = 0
                 ):
        super().__init__(cog, players, channel, initial_state, depth, bet)
        self.cancelled = False
        self.surrendered: Optional[discord.Member] = None
        self.last_board = self.board.copy()
        self.winner: Optional[discord.Member] = None
        self.tie = False

    def is_cancelled(self):
        return self.cancelled

    def is_finished(self):
        return self.is_cancelled() or self.board.is_game_over()
    
    def last_capture(self) -> Optional[chess.Piece]:
        if not self.board.move_stack or not self.last_board.is_capture(self.board.peek()):
            return None
        return self.last_board.piece_at(self.board.peek().to_square)
    
    def is_premature_surrender(self):
        return self.surrendered and self.board.fullmove_number <= 3
    
    async def cancel(self, member: Optional[discord.Member]):
        if member in self.players:
            self.surrendered = member
        self.cancelled = True
        await self.save_state()
    
    async def do_move(self, move: chess.Move):
        if self.board.move_stack:
            self.last_board.push(self.board.peek())
        self.board.push(move)
        self.last_interacted = datetime.now()
        await self.save_state()

    async def save_state(self):
        if self.is_finished():
            if self.cog.games.get(self.channel.id) == self:
                del self.cog.games[self.channel.id]
            await self.cog.config.channel(self.channel).clear()
            
            if self.surrendered and not self.is_premature_surrender():
                self.winner = self.players[1] if self.players.index(self.surrendered) == 0 else self.players[0]
            else:
                outcome = self.board.outcome()
                self.winner = self.member(outcome.winner) if outcome is not None and outcome.winner is not None else None
                self.tie = outcome is not None and outcome.winner is None

            await self._on_win(self.winner)
            
        else:
            await self.cog.config.channel(self.channel).game.set(self.board.fen())
            await self.cog.config.channel(self.channel).depth.set(self.limit.depth)
            await self.cog.config.channel(self.channel).players.set([player.id for player in self.players])
            await self.cog.config.channel(self.channel).bet.set(self.bet)

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
        arrows = [(lastmove.from_square, lastmove.to_square)] if lastmove and not is_finished else []
        check = self.board.king(self.board.turn) if self.board.is_check() and not is_finished else None
        svg = chess.svg.board(self.board, lastmove=lastmove, check=check, arrows=arrows, size=512)
        b = await asyncio.to_thread(svg_to_png, svg)
        return BytesIO(b or b'')

    async def update_message(self, interaction: Optional[discord.Interaction] = None):
        content = f"{self.players[0].mention} you're being invited to play chess." if not self.accepted else ""

        if all(m.bot for m in self.players):
            view = BotsView(self) if not self.is_finished() \
                else discord.ui.View(timeout=0)
        else:
            view = InviteView(self, await bank.get_currency_name(self.channel.guild)) if not self.accepted \
                else RematchView(self, await bank.get_currency_name(self.channel.guild)) if self.is_finished() \
                else ThinkingView() if self.member(self.board.turn).bot and not all(member.bot for member in self.players) \
                else GameView(self)

        embed = discord.Embed()

        if self.winner is not None:
            if self.surrendered:
                embed.title = f"{self.winner.display_name} is the winner via surrender!"
            else:
                embed.title = f"{self.winner.display_name} is the winner!"
            embed.set_thumbnail(url=self.winner.display_avatar.url)
        elif self.cancelled:
            embed.title = "The game was cancelled."
        elif self.tie:
            embed.title = "The game ended in a tie!"
        elif self.accepted:
            current = self.member(self.board.turn)
            embed.title = f"{current.display_name}'s turn"
            embed.set_thumbnail(url=current.display_avatar.url)
        else:
            embed.title="Waiting for confirmation..."

        if self.tie or self.is_premature_surrender():
            embed.color = COLOR_TIE
        elif self.winner is not None:
            embed.color = COLOR_WHITE if self.winner == self.member(chess.WHITE) else COLOR_BLACK
        else:
            embed.color = COLOR_WHITE if self.board.turn == chess.WHITE else COLOR_BLACK
        
        embed.description = ""
        currency_name = await bank.get_currency_name(self.channel.guild)
        economy_enabled = await self.cog.is_economy_enabled(self.channel.guild)
        last_capture = self.last_capture()

        if self.winner == self.member(chess.BLACK):
            embed.description += "👑 "
        embed.description += f"`⬛` {self.players[1].mention}"
        if last_capture and last_capture.color == chess.WHITE and not self.is_finished():
            embed.description += f" captured **{last_capture.unicode_symbol(invert_color=True)}**"
        elif self.winner is not None and self.bet > 0 and not self.players[1].bot and economy_enabled:
            embed.description += f" gains {self.bet} {currency_name}!" if self.winner == self.member(chess.BLACK) else f" loses {self.bet} {currency_name}…"

        embed.description += "\n"

        if self.winner == self.member(chess.WHITE):
            embed.description += "👑 "
        embed.description += f"`⬜` {self.players[0].mention}"
        if last_capture and last_capture.color == chess.BLACK and not self.is_finished():
            embed.description += f" captured **{last_capture.unicode_symbol()}**"
        elif self.winner is not None and self.bet > 0 and not self.member(chess.WHITE).bot and economy_enabled:
            embed.description += f" gains {self.bet} {currency_name}!" if self.winner == self.member(chess.WHITE) else f" loses {self.bet} {currency_name}…"

        filename = "board.png"
        file = discord.File(await self.generate_board_image(), filename)

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
