import random
import logging
import discord
from enum import Enum
from typing import List, Optional, Tuple
from datetime import datetime
from minigames.minigame import Minigame
from minigames.board import Board, find_lines, try_complete_line
from minigames.views.game_view import GameView
from minigames.views.invite_view import InviteView

log = logging.getLogger("c4")


class Player(Enum):
    TIE = -2
    NONE = -1
    RED = 0
    BLUE = 1

COLORS = {
    -2: 0x78B159,
    -1: 0x31373D,
    0: 0xDD2E44,
    1: 0x55ACEE,
}
EMOJIS = {
    -1: "⚫",
    0: "🔴",
    1: "🔵",
}
IMAGES = {
    0: "https://raw.githubusercontent.com/hollowstrawberry/crab-cogs/refs/heads/testing/minigames/media/red.png",
    1: "https://raw.githubusercontent.com/hollowstrawberry/crab-cogs/refs/heads/testing/minigames/media/blue.png",
}

NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]


class ConnectFourGame(Minigame):
    def __init__(self, players: List[discord.Member], channel: discord.TextChannel):
        if len(players) != 2:
            raise ValueError("Game must have 2 players")
        super().__init__(players, channel)
        self.accepted = False
        self.board = Board(7, 6, Player.NONE)
        self.current = Player.RED
        self.winner = Player.NONE

    def do_turn(self, player: discord.Member, column: int):
        if player != self.member(self.current):
            raise ValueError(f"It's not {player.name}'s turn")
        if self.is_finished():
            raise ValueError("This game is finished")
        if column < 0 or column > 6:
            raise ValueError(f"Column must be a number between 0 and 6, not {column}")
        
        log.info(f"{column=}")
        row = self.get_highest_slot(column)
        if row is None:
            raise ValueError(f"Column is full")
        
        self.last_interacted = datetime.now()
        self.board[column, row] = self.current
        if self.check_win():
            self.winner = self.current
        elif all(slot != Player.NONE for slot in self.board._data):
            self.winner = Player.TIE
        else:
            self.current = self.opponent()

    def do_turn_ai(self):
        self.do_turn(self.member(self.current), self.get_random_unoccupied())

    def is_finished(self) -> bool:
        return self.winner != Player.NONE
    
    def end(self):
        self.winner = Player.TIE

    def accept(self, _):
        self.accepted = True

    def check_win(self) -> bool:
        return find_lines(self.board, self.current, 4)
    
    def member(self, player: Player) -> discord.Member:
        if player.value < 0:
            raise ValueError("Invalid player")
        return self.players[player.value]
    
    def opponent(self) -> Player:
        return Player.BLUE if self.current == Player.RED else Player.RED
    
    def get_highest_slot(self, column: int) -> Optional[int]:
        if column < 0 or column > 6:
            raise ValueError
        for row in range(5, -1, -1):
            if self.board[column, row] == Player.NONE:
                return row
        return None
    
    def get_available_columns(self): 
        return [col for col in range(7) if self.get_highest_slot(col) is not None]
    
    def get_random_unoccupied(self) -> int:
        available_columns = self.get_available_columns()
        if not available_columns:
            raise ValueError("No available columns")
        return random.choice(available_columns)
    
    def get_content(self) -> Optional[str]:
        if not self.accepted:
            return f"{self.players[0].mention} you've been invited to play Connect 4!"
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
        description += "\n"
        for i in range(7):
            description += NUMBERS[i]
        description += "\n"
        for y in range(6):
            for x in range(7):
                description += EMOJIS[self.board[x, y].value] # type: ignore
            description += "\n"
        color = COLORS[self.winner.value] if self.winner != Player.NONE else COLORS[self.current.value]
        embed = discord.Embed(title=title, description=description, color=color)
        if self.winner.value != Player.NONE:
            if self.winner.value >= 0:
                embed.set_thumbnail(url=self.member(self.winner).display_avatar.url)
        elif self.current.value >= 0 and self.accepted:
            embed.set_thumbnail(url=IMAGES[self.current.value])
        return embed


    def get_view(self) -> Optional[discord.ui.View]:
        if not self.accepted:
            return InviteView(self)
        if self.is_finished():
            return None
        if not self.is_finished():
            view = GameView(self)
            options = [discord.SelectOption(label=f"{col + 1}", value=f"{col}") for col in self.get_available_columns()]
            select = discord.ui.Select(row=0, options=options, placeholder="Choose column...", custom_id=f"minigames c4 {self.channel.id}")

            async def action(interaction: discord.Interaction):
                nonlocal self, view
                assert isinstance(interaction.user, discord.Member)
                if interaction.user not in self.players:
                    return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
                if interaction.user != self.member(self.current):
                    return await interaction.response.send_message("It's not your turn!", ephemeral=True)
                self.do_turn(interaction.user, interaction.data.values[0]) # type: ignore
                if not self.is_finished() and self.member(self.current).bot:
                    self.do_turn_ai()
                new_view = self.get_view()
                if self.is_finished():
                    view.stop()
                    if new_view:
                        new_view.stop()
                await interaction.response.edit_message(content=self.get_content(), embed=self.get_embed(), view=new_view)

            select.callback = action
            view.add_item(select)
            return view
