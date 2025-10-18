import random
import discord
from enum import Enum
from typing import List, Optional
from datetime import datetime
from redbot.core import bank
from redbot.core.utils.chat_formatting import humanize_number

from minigames.base import BaseMinigameCog, Minigame
from minigames.board import Board, find_lines
from minigames.views.minigame_view import MinigameView
from minigames.views.invite_view import InviteView
from minigames.views.rematch_view import RematchView


class Player(Enum):
    TIE = -2
    NONE = -1
    RED = 0
    BLUE = 1


COLORS = {
    Player.TIE: 0x78B159,
    Player.NONE: 0x31373D,
    Player.RED: 0xDD2E44,
    Player.BLUE: 0x55ACEE,
}
EMOJIS = {
    Player.NONE: "⚫",
    Player.RED: "🔴",
    Player.BLUE: "🔵",
}
IMAGES = {
    Player.RED: "https://raw.githubusercontent.com/hollowstrawberry/crab-cogs/refs/heads/testing/minigames/media/red.png",
    Player.BLUE: "https://raw.githubusercontent.com/hollowstrawberry/crab-cogs/refs/heads/testing/minigames/media/blue.png",
}
NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]


class ConnectFourGame(Minigame):
    def __init__(self, cog: BaseMinigameCog, players: List[discord.Member], channel: discord.TextChannel, bet: int):
        if len(players) != 2:
            raise ValueError("Game must have 2 players")
        super().__init__(cog, players, channel, bet)
        self.accepted = False
        self.board = Board(7, 6, Player.NONE)
        self.current = Player.RED
        self.winner = Player.NONE
        self.time = 0
        self.cancelled = False

    async def do_turn(self, player: discord.Member, column: int):
        if player != self.member(self.current):
            raise ValueError(f"It's not {player.name}'s turn")
        if self.is_finished():
            raise ValueError("This game is finished")
        if column < 0 or column > self.board.width - 1:
            raise ValueError(f"Column must be a number between 0 and {self.board.width - 1}, not {column}")
        
        row = self.get_highest_slot(self.board, column)
        if row is None:
            raise ValueError("Column is full")
        
        self.last_interacted = datetime.now()
        self.time += 1
        self.board[column, row] = self.current
        if self.check_win(self.board, self.current, self.time):
            self.winner = self.current
            await self.on_win(self.member(self.winner))
        elif self.is_finished():
            self.winner = Player.TIE
            await self.on_win(None)
        else:
            self.current = self.opponent(self.current)

    async def do_turn_ai(self):
        moves = {}
        avoid_moves = []
        columns = self.available_columns(self.board)
        if len(columns) == 1:
            moves[columns[0]] = 0
        else:
            for column in columns: # All moves it can make
                temp_board = self.board.copy()
                self.drop_piece(temp_board, column, self.current)
                if self.check_win(temp_board, self.current, self.time + 1): # Can win instantly
                    moves = {column: 0}
                    avoid_moves = []
                    break
                # The AI plays defensively, so it mostly avoids possible futures where it may lose
                lose_count = self.may_lose_count(temp_board, self.current, self.opponent(self.current), self.time + 1, depth=3)
                moves[column] = lose_count
                if self.may_lose_count(temp_board, self.current, self.opponent(self.current), self.time + 1, depth=1) > 0: # Can lose next turn
                    avoid_moves.append(column)
        if len(avoid_moves) < len(moves):
            for move in avoid_moves:
                moves.pop(move)
        least_loses = min(moves.values())
        final_options = [col for col, val in moves.items() if val == least_loses]
        move = random.choice(final_options)
        await self.do_turn(self.member(self.current), move)

    def is_finished(self) -> bool:
        return self.winner != Player.NONE or self.cancelled or self.time == len(self.board._data)
    
    def is_cancelled(self) -> bool:
        return self.cancelled
    
    async def cancel(self, player: discord.Member):
        self.cancelled = True
        if self.time == 0:
            self.winner = Player.TIE
        elif player not in self.players:
            self.winner = Player.NONE
        else:
            self.winner = Player.BLUE if self.players.index(player) == 0 else Player.RED
        await self.on_win(self.member(self.winner) if self.winner.value >= 0 else None)

    def accept(self, _):
        self.accepted = True
    
    def member(self, player: Player) -> discord.Member:
        if player.value < 0:
            raise ValueError("Invalid player")
        return self.players[player.value]
    
    @classmethod
    def opponent(cls, current: Player) -> Player:
        return Player.BLUE if current == Player.RED else Player.RED
    
    @classmethod
    def check_win(cls, board: Board, color: Player, time: int) -> bool:
        return find_lines(board, color, 4)
    
    @classmethod
    def get_highest_slot(cls, board: Board, column: int) -> Optional[int]:
        if column < 0 or column > board.width - 1:
            raise ValueError("Invalid column")
        for row in range(board.height - 1, -1, -1):
            if board[column, row] == Player.NONE:
                return row
        return None
    
    @classmethod
    def drop_piece(cls, board: Board, column: int, color: Player):
        if column < 0 or column > board.width - 1:
            raise ValueError("Invalid column")
        row = cls.get_highest_slot(board, column)
        if row is None:
            raise ValueError("Column is full")
        board[column, row] = color
    
    @classmethod
    def available_columns(cls, board: Board): 
        return [col for col in range(board.width) if cls.get_highest_slot(board, col) is not None]
    
    @classmethod
    def get_random_unoccupied(cls, board: Board) -> int:
        available_columns = cls.available_columns(board)
        if not available_columns:
            raise ValueError("No available columns")
        return random.choice(available_columns)
    
    @classmethod
    def may_lose_count(cls, board: Board, color: Player, current: Player, time: int, depth: int):
        count = 0
        if depth <= 0 or time == len(board._data):
            return count
        for column in cls.available_columns(board):
            temp_board = board.copy()
            cls.drop_piece(temp_board, column, current)
            if current != color and cls.check_win(temp_board, current, time + 1):
                count += 1
            elif current != color or not cls.check_win(temp_board, current, time + 1):
                count += cls.may_lose_count(temp_board, color, cls.opponent(current), time + 1, depth - 1)
        return count


    async def get_content(self) -> Optional[str]:
        if not self.accepted:
            return f"{self.players[0].mention} you've been invited to play Connect 4!"
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
        description += "\n"
        if not self.is_finished():
            for i in range(self.board.width):
                description += NUMBERS[i]
            description += "\n"
        for y in range(self.board.height):
            for x in range(self.board.width):
                description += EMOJIS[self.board[x, y]] # type: ignore
            description += "\n"

        color = COLORS[self.winner] if self.winner != Player.NONE else COLORS[self.current]

        embed = discord.Embed(title=title, description=description, color=color)

        if self.is_finished():
            if self.winner.value >= 0:
                embed.set_thumbnail(url=self.member(self.winner).display_avatar.url)
        elif self.accepted:
            embed.set_thumbnail(url=IMAGES[self.current])

        return embed


    async def get_view(self) -> Optional[discord.ui.View]:
        if not self.accepted:
            return InviteView(self, await bank.get_currency_name(self.channel.guild))
        if self.is_finished():
            return RematchView(self, await bank.get_currency_name(self.channel.guild))

        view = MinigameView(self)
        options = [discord.SelectOption(label=f"{col + 1}", value=f"{col}") for col in self.available_columns(self.board)]
        select = discord.ui.Select(row=0, options=options, placeholder="Choose column to drop a piece...", custom_id=f"minigames c4 {self.channel.id}")

        async def action(interaction: discord.Interaction):
            nonlocal self, view
            assert isinstance(interaction.user, discord.Member)
            if interaction.user not in self.players:
                return await interaction.response.send_message("You're not playing this game!", ephemeral=True)
            if interaction.user != self.member(self.current):
                return await interaction.response.send_message("It's not your turn!", ephemeral=True)
            await self.do_turn(interaction.user, int(interaction.data['values'][0])) # type: ignore
            if not self.is_finished() and self.member(self.current).bot:
                await self.do_turn_ai()
            if self.is_finished():
                view.stop()
            new_view = await self.get_view()
            await interaction.response.edit_message(content=await self.get_content(), embed=await self.get_embed(), view=new_view)
            if isinstance(new_view, RematchView):
                new_view.message = interaction.message

        select.callback = action
        view.add_item(select)
        return view
