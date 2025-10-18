import random
import discord
from enum import Enum
from typing import List, Optional, Tuple
from datetime import datetime
from redbot.core import bank
from redbot.core.utils.chat_formatting import humanize_number

from minigames.base import BaseMinigameCog, Minigame
from minigames.board import Board, find_lines, try_complete_line
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
    def __init__(self, cog: BaseMinigameCog, players: List[discord.Member], channel: discord.TextChannel, bet: int):
        if len(players) != 2:
            raise ValueError("Game must have 2 players")
        super().__init__(cog, players, channel, bet)
        self.accepted = False
        self.board = Board(3, 3, Player.NONE)
        self.current = Player.CROSS
        self.winner = Player.NONE
        self.time = 0
        self.cancelled = False

    async def do_turn(self, player: discord.Member, slot: int):
        if player != self.member(self.current):
            raise ValueError(f"It's not {player.name}'s turn")
        if self.is_finished():
            raise ValueError("This game is finished")
        if slot < 0 or slot > 8:
            raise ValueError(f"Slot must be a number between 0 and 8, not {slot}")
        if self.board._data[slot] != Player.NONE:
            raise ValueError(f"Board slot {slot} is already occupied")
        
        self.last_interacted = datetime.now()
        self.time += 1
        self.board._data[slot] = self.current
        if self.check_win():
            self.winner = self.current
            await self.on_win(self.member(self.winner))
        elif self.is_finished():
            self.winner = Player.TIE
            await self.on_win(None)
        else:
            self.current = self.opponent(self.current)

    async def do_turn_ai(self):
        target = try_complete_line(self.board, self.current, Player.NONE, 3) \
            or try_complete_line(self.board, self.opponent(self.current), Player.NONE, 3) \
            or self.get_random_unoccupied()
        await self.do_turn(self.member(self.current), target[1]*3 + target[0])

    def is_finished(self) -> bool:
        return self.winner != Player.NONE or self.cancelled or self.time == 9
    
    def is_cancelled(self) -> bool:
        return self.cancelled
    
    async def cancel(self, player: discord.Member):
        self.cancelled = True
        if self.time == 0:
            self.winner = Player.TIE
        elif player not in self.players:
            self.winner = Player.NONE
        else:
            self.winner = Player.CIRCLE if self.players.index(player) == 0 else Player.CROSS
        await self.on_win(self.member(self.winner) if self.winner.value >= 0 else None)

    def accept(self, _):
        self.accepted = True

    def check_win(self) -> bool:
        return find_lines(self.board, self.current, 3)
    
    def member(self, player: Player) -> discord.Member:
        if player.value < 0:
            raise ValueError("Invalid player")
        return self.players[player.value]
    
    @classmethod
    def opponent(cls, current: Player) -> Player:
        return Player.CIRCLE if current == Player.CROSS else Player.CROSS
    
    def get_random_unoccupied(self) -> Tuple[int, int]:
        empty_slots = []
        for y in range(3):
            for x in range(3):
                if self.board[x, y] == Player.NONE:
                    empty_slots.append((x, y))
        if not empty_slots:
            raise ValueError("No empty slots")
        return random.choice(empty_slots)
    

    async def get_content(self) -> Optional[str]:
        if not self.accepted:
            return f"{self.players[0].mention} you've been invited to play Tic-Tac-Toe!"
        else:
            return None


    async def get_embed(self) -> discord.Embed:
        title = "Pending invitation..." if not self.accepted \
                else f"{self.member(self.current).display_name}'s turn" if not self.is_finished() \
                else "The game was cancelled!" if self.cancelled and self.winner.value < 0 \
                else "It's a tie!" if self.winner == Player.TIE \
                else f"{self.member(self.winner).display_name} is the winner via surrender!" if self.cancelled \
                else f"{self.member(self.winner).display_name} is the winner!"
        
        description = ""
        for i, player in enumerate(self.players):
            if self.winner.value == i:
                description += "👑 "
            elif not self.is_finished() and self.current.value == i and self.accepted:
                description += "►"
            description += f"{EMOJIS[Player(i)]} - {player.mention}"
            if self.winner.value >= 0 and self.bet > 0 and not player.bot and await self.cog.is_economy_enabled(self.channel.guild):
                currency_name = await bank.get_currency_name(self.channel.guild)
                if self.winner.value == i:
                    description += f" +{humanize_number(self.bet)} {currency_name}"
                elif not self.member(self.opponent(Player(i))).bot:
                    description += f" -{humanize_number(self.bet)} {currency_name}"
            description += "\n"

        color = COLORS[self.winner] if self.winner != Player.NONE else COLORS[self.current]

        embed = discord.Embed(title=title, description=description, color=color)

        if self.is_finished():
            if self.winner.value >= 0:
                embed.set_thumbnail(url=self.member(self.winner).display_avatar.url)
        elif self.accepted:
            embed.set_thumbnail(url=IMAGES[self.current])

        return embed


    async def get_view(self) -> discord.ui.View:
        if not self.accepted:
            return InviteView(self, await bank.get_currency_name(self.channel.guild))

        view = MinigameView(self) if not self.is_finished() else RematchView(self, await bank.get_currency_name(self.channel.guild))
        for i in range(9):
            slot: Player = self.board._data[i] # type: ignore
            button = discord.ui.Button(
                emoji=EMOJIS[slot],
                disabled= slot != Player.NONE or self.is_finished(),
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
                await self.do_turn(interaction.user, i)
                if not self.is_finished() and self.member(self.current).bot:
                    await self.do_turn_ai()
                if self.is_finished():
                    view.stop()
                new_view = await self.get_view()
                await interaction.response.edit_message(content=await self.get_content(), embed=await self.get_embed(), view=new_view)
                if isinstance(new_view, RematchView):
                    new_view.message = interaction.message

            button.callback = action
            view.add_item(button)

        return view
