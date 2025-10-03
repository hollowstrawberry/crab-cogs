import random
import logging
import discord
from enum import Enum
from typing import List, Optional, Tuple
from datetime import datetime
from minigames.minigame import Minigame
from minigames.board import Board, find_lines, try_complete_line

log = logging.getLogger("ttt")

EMOJIS = {
    -1: "▪️",
    0: "❌",
    1: "⭕",
}
IMAGES = {
    0: "https://raw.githubusercontent.com/hollowstrawberry/Pac-Man-Bot/refs/heads/master/_Resources/Emotes/TTTx.png",
    1: "https://raw.githubusercontent.com/hollowstrawberry/Pac-Man-Bot/refs/heads/master/_Resources/Emotes/TTTo.png",
}
COLOR = 0xDD2E44


class Player(Enum):
    TIE = -2
    NONE = -1
    CROSS = 0
    CIRCLE = 1


class TicTacToeGame(Minigame):
    def __init__(self, players: List[discord.Member], channel: discord.TextChannel):
        if len(players) != 2:
            raise ValueError("Game must have 2 players")
        super().__init__(players, channel)
        self.accepted = False
        self.board = Board(3, 3, Player.NONE)
        self.current = Player.CROSS
        self.winner = Player.NONE

    def do_turn(self, player: discord.Member, slot: int):
        if player != self.member(self.current):
            raise ValueError(f"It's not {player.name}'s turn")
        if self.is_finished():
            raise ValueError("This game is finished")
        if slot < 0 or slot > 8:
            raise ValueError(f"Action must be a number between 0 and 8, not {slot}")
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
        return self.winner != Player.NONE

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
                else f"{self.member(self.current).display_name}'s turn" if self.winner == Player.NONE \
                else "It's a tie!" if self.winner == Player.TIE \
                else f"{self.member(self.current).display_name} is the winner!"
        description = ""
        for i, player in enumerate(self.players):
            if self.winner.value == i:
                description += "👑 "
            elif self.winner.value == Player.NONE and self.current.value == i and self.accepted:
                description += "➡️ "
            description += f"{EMOJIS[i]} - {player.mention}\n"
        embed = discord.Embed(title=title, description=description, color=COLOR)
        if self.winner.value >= 0:
            embed.set_thumbnail(url=self.member(self.winner).display_avatar.url)
        elif self.current.value >= 0 and self.accepted:
            embed.set_thumbnail(url=IMAGES[self.current.value])
        return embed

    def get_view(self) -> discord.ui.View:
        view = discord.ui.View(timeout=None)

        if not self.accepted:
            button = discord.ui.Button(label="Accept", style=discord.ButtonStyle.primary)

            async def accept(interaction: discord.Interaction):
                if interaction.user != self.players[0]:
                    return await interaction.response.send_message("You're not the target of this invitation!", ephemeral=True)
                self.accepted = True
                await interaction.response.edit_message(content=self.get_content(), embed=self.get_embed(), view=self.get_view())

            button.callback = accept
            view.add_item(button)

        else:
            for i in range(9):
                slot: Player = self.board._data[i] # type: ignore
                button = discord.ui.Button(
                    emoji=EMOJIS[slot.value],
                    disabled=slot!=Player.NONE,
                    custom_id=f"minigames ttt {self.channel.id} {i}",
                    row=i//3,
                    style=discord.ButtonStyle.secondary,
                )

                async def callback(interaction: discord.Interaction, i=i):
                    assert isinstance(interaction.user, discord.Member)
                    if interaction.user not in self.players:
                        return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
                    if interaction.user != self.member(self.current):
                        return await interaction.response.send_message("It's not your turn!", ephemeral=True)
                    self.do_turn(interaction.user, i)
                    if not self.is_finished() and self.member(self.current).bot:
                        self.do_turn_ai()
                    await interaction.response.edit_message(content=self.get_content(), embed=self.get_embed(), view=self.get_view())
                    if self.is_finished():
                        view.stop()

                button.callback = callback
                view.add_item(button)

        return view
