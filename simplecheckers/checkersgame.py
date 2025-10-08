import asyncio
import logging
import re
import discord
import draughts
from io import BytesIO
from typing import List, Optional, Tuple
from datetime import datetime

from simplecheckers.base import BaseCheckersCog, BaseCheckersGame
from simplecheckers.utils import create_svg, svg_to_png
from simplecheckers.views.invite_view import InviteView
from simplecheckers.views.game_view import GameView
from simplecheckers.views.rematch_view import RematchView

log = logging.getLogger("red.crab-cogs.simplecheckers")

COLOR_WHITE = 0xffffff
COLOR_BLACK = 0x000000
COLOR_TIE = 0x78B159


class CheckersGame(BaseCheckersGame):
    def __init__(self, cog: BaseCheckersCog, players: List[discord.Member], channel: discord.TextChannel, variant: str, initial_state: str = None):
        super().__init__(cog, players, channel, variant, initial_state)
        self.accepted = initial_state is not None
        self.cancelled = False
        self.surrendered: Optional[discord.Member] = None
        self.time = 0
    
    def accept(self):
        self.accepted = True

    def is_cancelled(self):
        return self.cancelled

    def is_finished(self):
        return self.is_cancelled() or self.board.is_over()
    
    def is_premature_surrender(self):
        return self.surrendered and self.time <= 5
    
    async def cancel(self, member: Optional[discord.Member]):
        if member in self.players:
            self.surrendered = member
        self.cancelled = True
        await self.update_state()
    
    async def do_move(self, move: draughts.Move):
        self.board.push(move)
        self.time += 1
        self.last_interacted = datetime.now()
        await self.update_state()

    async def update_state(self):
        if self.is_finished():
            if self.cog.games.get(self.channel.id) == self:
                del self.cog.games[self.channel.id]
            await self.cog.config.channel(self.channel).clear()
        else:
            await self.cog.config.channel(self.channel).game.set(self.board.fen)
            await self.cog.config.channel(self.channel).players.set([player.id for player in self.players])

    async def move_user(self, hub_move: str) -> Tuple[bool, str]:
        move = draughts.Move(self.board, hub_move=hub_move)
        if move not in self.board.legal_moves():
            return False, "That move is invalid, try something else."
        await self.do_move(move)
        return True, ""
            
    async def generate_board_image(self) -> BytesIO:
        svg = create_svg(self.board)
        b = await asyncio.to_thread(svg_to_png, svg)
        return BytesIO(b or b'')

    async def update_message(self, interaction: Optional[discord.Interaction] = None):
        content = f"{self.players[0].mention} you're being invited to play chess." if not self.accepted else ""
        embed = discord.Embed()
        
        view = InviteView(self) if not self.accepted \
            else RematchView(self) if self.is_finished() \
            else GameView(self)

        filename = "board.png"
        file = discord.File(await self.generate_board_image(), filename)

        winner = self.board.winner()
        winner_member = self.member(winner) if winner is not None else None
        if winner is None:
            if self.surrendered and not self.is_premature_surrender():
                winner_member = self.players[1] if self.players.index(self.surrendered) == 0 else self.players[0]
                embed.title = f"{winner_member.display_name} is the winner via surrender!"
                embed.set_thumbnail(url=winner_member.display_avatar.url)
            elif self.cancelled:
                embed.title = "The game was cancelled."
            elif self.accepted:
                turn = self.member(self.board.turn)
                embed.title = f"{turn.display_name}'s turn"
                embed.set_thumbnail(url=turn.display_avatar.url)
            else:
                embed.title="Waiting for confirmation..."
        elif winner_member is not None:
            embed.title = f"{winner_member.display_name} is the winner!"
            embed.set_thumbnail(url=winner_member.display_avatar.url)
        else:
            embed.title = "The game ended in a tie!"

        if winner == 0 or self.is_cancelled() and (winner_member is None or self.is_premature_surrender()):
            embed.color = COLOR_TIE
        elif winner:
            embed.color = COLOR_WHITE if winner == draughts.WHITE else COLOR_BLACK
        else:
            embed.color = COLOR_WHITE if self.board.turn == draughts.WHITE else COLOR_BLACK
        
        embed.description = ""
        if winner == draughts.BLACK or self.surrendered == self.players[0] and not self.is_premature_surrender():
            embed.description += "👑 "
        embed.description += f"`⬛` {self.players[1].mention}"

        if winner == draughts.WHITE or self.surrendered == self.players[1] and not self.is_premature_surrender():
            embed.description += "👑 "
        embed.description += f"\n`⬜` {self.players[0].mention}"

        embed.set_image(url=f"attachment://{filename}")
        embed.set_footer(text=f"Turn {int(self.time // 2)}")

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
