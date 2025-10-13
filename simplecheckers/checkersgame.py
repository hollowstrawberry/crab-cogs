import asyncio
import logging
import discord
import draughts
from io import BytesIO
from typing import List, Optional, Tuple
from datetime import datetime
from redbot.core import bank
from redbot.core.data_manager import bundled_data_path

from simplecheckers.base import BaseCheckersCog, BaseCheckersGame
from simplecheckers.agent import MinimaxAgent
from simplecheckers.utils import board_to_png
from simplecheckers.views.bots_view import BotsView
from simplecheckers.views.invite_view import InviteView
from simplecheckers.views.game_view import GameView
from simplecheckers.views.rematch_view import RematchView
from simplecheckers.views.thinking_view import ThinkingView

log = logging.getLogger("red.crab-cogs.simplecheckers")

COLOR_WHITE = 0xDD2E44
COLOR_BLACK = 0x000000
COLOR_TIE = 0x78B159


class CheckersGame(BaseCheckersGame):
    def __init__(self,
                 cog: BaseCheckersCog,
                 players: List[discord.Member],
                 channel: discord.TextChannel,
                 variant: str,
                 initial_state: str = None,
                 initial_time: int = 0,
                 bet: int = 0
                 ):
        super().__init__(cog, players, channel, variant, initial_state, initial_time, bet)
        self.cancelled = False
        self.surrendered: Optional[discord.Member] = None
        self.last_arrows: List[int] = []
        self.winner: Optional[discord.Member] = None
        self.tie = False
    
    def is_cancelled(self):
        return self.cancelled

    def is_finished(self):
        return self.is_cancelled() or self.board.is_over()
    
    def is_premature_surrender(self):
        return self.surrendered and self.time <= 5

    def count_pieces(self, color: int):
        board_str = str(self.board)
        if color == draughts.WHITE:
            return board_str.count("w") + board_str.count("W")
        else:
            return board_str.count("b") + board_str.count("B")
        
    def check_ai_surrender(self):
        if self.time >= 100 and all(p.bot for p in self.players):
            white_pieces = self.count_pieces(draughts.WHITE)
            black_pieces = self.count_pieces(draughts.BLACK)
            if white_pieces <= 3 and white_pieces < black_pieces:
                self.surrendered = self.member(draughts.WHITE)
                self.cancelled = True
            elif black_pieces <= 3 and black_pieces < white_pieces:
                self.surrendered = self.member(draughts.BLACK)
                self.cancelled = True

    async def cancel(self, member: Optional[discord.Member]):
        self.cancelled = True
        if member in self.players:
            self.surrendered = member
        await self.save_state()
            
    async def save_state(self):
        if self.is_finished():
            if self.cog.games.get(self.channel.id) == self:
                del self.cog.games[self.channel.id]
            await self.cog.config.channel(self.channel).clear()

            if self.surrendered and not self.is_premature_surrender():
                self.winner = self.players[1] if self.players.index(self.surrendered) == 0 else self.players[0]
            else:
                winner = self.board.winner()
                self.winner = self.member(winner) if winner is not None and winner > 0 else None
                self.tie = winner == 0

            await self._on_win(self.winner)

        else:
            await self.cog.config.channel(self.channel).game.set(self.board.fen)
            await self.cog.config.channel(self.channel).variant.set(self.board.variant)
            await self.cog.config.channel(self.channel).players.set([player.id for player in self.players])
            await self.cog.config.channel(self.channel).time.set(self.time)
            await self.cog.config.channel(self.channel).bet.set(self.bet)

    async def move_user(self, move_str: str) -> Tuple[bool, str]:
        try:
            move_lst = [int(m) for m in move_str.split()]
            move = draughts.Move(self.board, steps_move=move_lst)
            self.board.push(move)
        except (ValueError, KeyError, IndexError):
            moves = self.board.legal_moves()
            moves_str = " / ".join(f"`{' '.join(str(n) for n in m.steps_move)}`" for m in moves)
            if len(moves) == 1:
                response = f"That move is invalid, the only valid move is: {moves_str}"
            else:
                response = f"That move is invalid, valid moves are:\n{moves_str}"
            if any(move.has_captures for move in moves):
                response += "\nRemember, captures are mandatory in standard rules of checkers!"
            return False, response
        self.last_arrows = move_lst
        self.time += 1
        self.last_interacted = datetime.now()
        self.check_ai_surrender()
        await self.save_state()
        return True, ""
    
    async def move_engine(self):
        agent = MinimaxAgent(self.board.turn)
        move = await asyncio.to_thread(agent.choose_move, self.board, 6, 1.0)
        if not move:
            raise ValueError("Agent failed to make a move")
        move_str = " ".join(str(n) for n in move.steps_move)
        success, message = await self.move_user(move_str)
        if not success:
            log.error(f"Invalid agent move {move_str}")
            raise ValueError(message)
            
    async def generate_board_image(self) -> BytesIO:
        overlay_path = str(bundled_data_path(self.cog) / "overlay.png")
        arrows = self.last_arrows if not self.is_cancelled() else []
        b = await asyncio.to_thread(board_to_png, self.board, overlay_path, arrows)
        return BytesIO(b)

    async def update_message(self, interaction: Optional[discord.Interaction] = None):
        if not self.accepted:
            content = f"{self.players[0].mention} you're being invited to play checkers."
        else:
            content = ""

        embed = discord.Embed()
        
        if all(m.bot for m in self.players):
            view = BotsView(self) if not self.is_finished() \
                else discord.ui.View(timeout=0)
        else:
            view = InviteView(self, await bank.get_currency_name(self.channel.guild)) if not self.accepted \
                else RematchView(self, await bank.get_currency_name(self.channel.guild)) if self.is_finished() \
                else ThinkingView(self) if self.member(self.board.turn).bot \
                else GameView(self)

        filename = "board.png"
        file = discord.File(await self.generate_board_image(), filename)

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
            embed.color = COLOR_BLACK if self.winner == self.member(draughts.BLACK) else COLOR_WHITE
        else:
            embed.color = COLOR_BLACK if self.board.turn == draughts.BLACK else COLOR_WHITE
        
        embed.description = ""
        currency_name = await bank.get_currency_name(self.channel.guild)
        economy_enabled = await self.cog.is_economy_enabled(self.channel.guild)

        if self.winner == self.member(draughts.BLACK):
            embed.description += "👑 "
        embed.description += f"`⚫` {self.member(draughts.BLACK).mention}"
        if self.winner is not None and self.bet > 0 and not self.member(draughts.BLACK).bot and economy_enabled:
            embed.description += f" gains {self.bet} {currency_name}!" if self.winner == self.member(draughts.BLACK) else f" loses {self.bet} {currency_name}…"

        embed.description += "\n"

        if self.winner == self.member(draughts.WHITE):
            embed.description += "👑 "
        embed.description += f"`🔴` {self.member(draughts.WHITE).mention}"
        if self.winner is not None and self.bet > 0 and not self.member(draughts.WHITE).bot and economy_enabled:
            embed.description += f" gains {self.bet} {currency_name}!" if self.winner == self.member(draughts.WHITE) else f" loses {self.bet} {currency_name}…"

        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text=f"Turn {self.time // 2 + 1}")

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
