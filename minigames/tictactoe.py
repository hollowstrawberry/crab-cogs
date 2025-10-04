import random
import discord
from enum import Enum
from typing import List, Optional, Tuple
from datetime import datetime

from minigames.base import Minigame
from minigames.board import Board, find_lines, try_complete_line
from minigames.constants import TwoPlayerGameCommand
from minigames.views.minigame_view import MinigameView
from minigames.views.invite_view import InviteView
from minigames.views.rematch_view import RematchView


class Player(Enum):
    TIE = -2
    NONE = -1
    CROSS = 0
    CIRCLE = 1

COLORS = {
    Player.TIE: 0x78B159,
    Player.NONE: 0x31373D,
    Player.CROSS: 0xDD2E44,
    Player.CIRCLE: 0xDD2E44,
}
EMOJIS = {
    Player.NONE: "▪️",
    Player.CROSS: "❌",
    Player.CIRCLE: "⭕",
}
IMAGES = {
    Player.CROSS: "https://raw.githubusercontent.com/hollowstrawberry/crab-cogs/refs/heads/testing/minigames/media/x.png",
    Player.CIRCLE: "https://raw.githubusercontent.com/hollowstrawberry/crab-cogs/refs/heads/testing/minigames/media/o.png",
}

class TicTacToeGame(Minigame):
    def __init__(self, players: List[discord.Member], channel: discord.TextChannel, command: TwoPlayerGameCommand):
        if len(players) != 2:
            raise ValueError("Game must have 2 players")
        super().__init__(players, channel, command)
        self.accepted = False
        self.board = Board(3, 3, Player.NONE)
        self.current = Player.CROSS
        self.winner = Player.NONE
        self.cancelled = False

    def do_turn(self, player: discord.Member, slot: int):
        if player != self.member(self.current):
            raise ValueError(f"It's not {player.name}'s turn")
        if self.is_finished():
            raise ValueError("This game is finished")
        if slot < 0 or slot > 8:
            raise ValueError(f"Slot must be a number between 0 and 8, not {slot}")
        if self.board._data[slot] != Player.NONE:
            raise ValueError(f"Board slot {slot} is already occupied")
        
        self.last_interacted = datetime.now()
        self.board._data[slot] = self.current
        if self.check_win():
            self.winner = self.current
        elif all(slot != Player.NONE for slot in self.board._data):
            self.winner = Player.TIE
        else:
            self.current = self.opponent()

    def do_turn_ai(self):
        target = try_complete_line(self.board, self.current, Player.NONE, 3) \
            or try_complete_line(self.board, self.opponent(), Player.NONE, 3) \
            or self.get_random_unoccupied()
        self.do_turn(self.member(self.current), target[1]*3 + target[0])

    def is_finished(self) -> bool:
        return self.winner != Player.NONE or self.cancelled
    
    def is_cancelled(self) -> bool:
        return self.cancelled
    
    def end(self, player: discord.Member):
        self.cancelled = True
        if player not in self.players:
            self.winner = Player.NONE
        else:
            self.winner = Player.CIRCLE if self.players.index(player) == 0 else Player.CROSS

    def accept(self, _):
        self.accepted = True

    def check_win(self) -> bool:
        return find_lines(self.board, self.current, 3)
    
    def member(self, player: Player) -> discord.Member:
        if player.value < 0:
            raise ValueError("Invalid player")
        return self.players[player.value]
    
    def opponent(self) -> Player:
        return Player.CIRCLE if self.current == Player.CROSS else Player.CROSS
    
    def get_random_unoccupied(self) -> Tuple[int, int]:
        empty_slots = []
        for y in range(3):
            for x in range(3):
                if self.board[x, y] == Player.NONE:
                    empty_slots.append((x, y))
        if not empty_slots:
            raise ValueError("No empty slots")
        return random.choice(empty_slots)
    
    def get_content(self) -> Optional[str]:
        if not self.accepted:
            return f"{self.players[0].mention} you've been invited to play Tic-Tac-Toe!"
        else:
            return None

    def get_embed(self) -> discord.Embed:
        title = "Pending invitation..." if not self.accepted \
                else f"{self.member(self.current).display_name}'s turn" if not self.is_finished() \
                else "The game was cancelled!" if self.cancelled and self.winner == Player.NONE \
                else "It's a tie!" if self.winner == Player.TIE \
                else f"{self.member(self.winner).display_name} is the winner via surrender!" if self.cancelled \
                else f"{self.member(self.winner).display_name} is the winner!"
        
        description = ""
        for i, player in enumerate(self.players):
            if self.winner.value == i:
                description += "👑 "
            elif self.winner == Player.NONE and self.current.value == i and self.accepted:
                description += "►"
            description += f"{EMOJIS[Player(i)]} - {player.mention}\n"
        color = COLORS[self.winner] if self.winner != Player.NONE else COLORS[self.current]
        embed = discord.Embed(title=title, description=description, color=color)
        if self.winner != Player.NONE:
            if self.winner.value >= 0:
                embed.set_thumbnail(url=self.member(self.winner).display_avatar.url)
        elif self.current.value >= 0 and self.accepted:
            embed.set_thumbnail(url=IMAGES[self.current])
        return embed


    def get_view(self) -> discord.ui.View:
        if not self.accepted:
            return InviteView(self)

        assert self.command

        view = RematchView(self) if self.is_finished() else MinigameView(self)
        for i in range(9):
            slot: Player = self.board._data[i] # type: ignore
            button = discord.ui.Button(
                emoji=EMOJIS[slot],
                disabled= slot != Player.NONE or self.winner != Player.NONE,
                custom_id=f"minigames ttt {self.channel.id} {i}",
                row=i//3,
                style=discord.ButtonStyle.secondary,
            )

            async def action(interaction: discord.Interaction, i=i):
                nonlocal self, view
                assert isinstance(interaction.user, discord.Member)
                if interaction.user not in self.players:
                    return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
                if interaction.user != self.member(self.current):
                    return await interaction.response.send_message("It's not your turn!", ephemeral=True)
                self.do_turn(interaction.user, i)
                if not self.is_finished() and self.member(self.current).bot:
                    self.do_turn_ai()
                if self.is_finished():
                    view.stop()
                new_view = self.get_view()
                await interaction.response.edit_message(content=self.get_content(), embed=self.get_embed(), view=new_view)
                if isinstance(new_view, RematchView):
                    new_view.message = interaction.message

            button.callback = action
            view.add_item(button)

        return view
