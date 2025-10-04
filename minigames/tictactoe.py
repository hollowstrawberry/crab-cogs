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
    0: "https://raw.githubusercontent.com/hollowstrawberry/crab-cogs/refs/heads/testing/minigames/media/x.png",
    1: "https://raw.githubusercontent.com/hollowstrawberry/crab-cogs/refs/heads/testing/minigames/media/o.png",
}
COLOR = 0xDD2E44
TIE_COLOR = 0x78B159


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
        color = TIE_COLOR if self.winner == Player.TIE else COLOR
        embed = discord.Embed(title=title, description=description, color=color)
        if self.winner.value != Player.NONE:
            if self.winner.value >= 0:
                embed.set_thumbnail(url=self.member(self.winner).display_avatar.url)
        elif self.current.value >= 0 and self.accepted:
            embed.set_thumbnail(url=IMAGES[self.current.value])
        return embed


    def get_view(self) -> discord.ui.View:
        view = discord.ui.View(timeout=None)

        if not self.accepted:
            async def accept(interaction: discord.Interaction):
                nonlocal self
                if interaction.user != self.players[0]:
                    return await interaction.response.send_message("You're not the target of this invitation!", ephemeral=True)
                self.accepted = True
                await interaction.response.edit_message(content=self.get_content(), embed=self.get_embed(), view=self.get_view())

            async def cancel(interaction: discord.Interaction):
                nonlocal self, view
                if interaction.user not in self.players:
                    return await interaction.response.send_message("You're not the target of this invitation!", ephemeral=True)
                self.winner = Player.TIE
                view.stop()
                assert interaction.message
                await interaction.message.delete()

            accept_button = discord.ui.Button(label="Accept", style=discord.ButtonStyle.primary)
            cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
            accept_button.callback = accept
            cancel_button.callback = cancel
            view.add_item(accept_button)
            view.add_item(cancel_button)

        else:
            for i in range(9):
                slot: Player = self.board._data[i] # type: ignore
                button = discord.ui.Button(
                    emoji=EMOJIS[slot.value],
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
                    new_view = self.get_view()
                    if self.is_finished():
                        view.stop()
                        new_view.stop()
                    await interaction.response.edit_message(content=self.get_content(), embed=self.get_embed(), view=new_view)

                button.callback = action
                view.add_item(button)

            if not self.is_finished():
                async def bump(interaction: discord.Interaction):
                    nonlocal self, view
                    assert interaction.message
                    if interaction.user not in self.players:
                        return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
                    await interaction.message.delete()
                    self.message = await interaction.message.channel.send(content=self.get_content(), embed=self.get_embed(), view=self.get_view())
                
                async def end(interaction: discord.Interaction):
                    nonlocal self, view
                    assert interaction.channel and isinstance(interaction.user, discord.Member)
                    if interaction.user not in self.players and not interaction.channel.permissions_for(interaction.user).manage_messages:
                        return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
                    self.winner = Player.TIE
                    new_view = self.get_view()
                    new_view.stop()
                    view.stop()
                    await interaction.response.edit_message(content=self.get_content(), embed=self.get_embed(), view=new_view)

                bump_button = discord.ui.Button(emoji="⬇️", label="Bump", style=discord.ButtonStyle.primary, row=1)
                end_button = discord.ui.Button(emoji="🛑", label="End", style=discord.ButtonStyle.danger, row=1)
                bump_button.callback = bump
                end_button.callback = end
                view.add_item(bump_button)
                view.add_item(end_button)

        return view
