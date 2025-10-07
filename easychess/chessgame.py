import sys
import asyncio
import logging
import discord
from io import BytesIO
from typing import List, Optional, Tuple
from datetime import datetime
from redbot.core.data_manager import bundled_data_path

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
    def __init__(self, cog: BaseChessCog, players: List[discord.Member], channel: discord.TextChannel, initial_state: str = None):
        super().__init__(cog, players, channel, initial_state)
        self.limit = chess.engine.Limit(time=1.0)
        self.accepted = initial_state is not None
        self.cancelled = False
        self.surrendered: Optional[discord.Member] = None
    
    async def start_engine(self) -> chess.engine.UciProtocol:
        _, engine = await chess.engine.popen_uci([sys.executable, '-u', str(bundled_data_path(self.cog) / "sunfish.py")])
        return engine
    
    def accept(self):
        self.accepted = True

    def is_cancelled(self):
        return self.cancelled

    def is_finished(self):
        return self.is_cancelled() or self.board.is_game_over()
    
    async def cancel(self, member: Optional[discord.Member]):
        if member in self.players:
            self.surrendered = member
        self.cancelled = True
        await self.update_state()
    
    async def do_move(self, move: chess.Move):
        self.board.push(move)
        self.last_interacted = datetime.now()
        await self.update_state()

    async def update_state(self):
        if self.is_finished():
            log.info(f"is finished {self.cancelled=}")
            if self.cog.games.get(self.channel.id) == self:
                del self.cog.games[self.channel.id]
            await self.cog.config.channel(self.channel).game.set(None)
            await self.cog.config.channel(self.channel).players.set([])
            if self.engine:
                try:
                    await self.engine.quit()
                except chess.engine.EngineTerminatedError:
                    pass
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
        if not self.engine:
            self.engine = await self.start_engine()
        log.info(f"{self.engine=}")
        result = await self.engine.play(self.board, limit=self.limit)
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
