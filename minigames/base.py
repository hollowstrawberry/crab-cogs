import discord
from abc import ABC, abstractmethod
from typing import List, Optional, Type, Union
from datetime import datetime
from redbot.core import commands, bank, errors


class BaseMinigameCog(commands.Cog):
    @abstractmethod
    async def is_economy_enabled(self, guild: discord.Guild) -> bool:
        pass

    @abstractmethod
    async def base_minigame_cmd(self,
                                game_cls: Type["Minigame"],
                                ctx: Union[commands.Context, discord.Interaction],
                                players: List[discord.Member],
                                against_bot: bool,
                                bet: Optional[int]
                                ) -> None:
        pass
        

class Minigame(ABC):
    def __init__(self, cog: BaseMinigameCog, players: List[discord.Member], channel: discord.TextChannel, bet: int):
        self.cog = cog
        self.bet = bet
        self.players = players
        self.channel = channel
        self.message: Optional[discord.Message] = None
        self.last_interacted: datetime = datetime.now()
        self.init_done = False
        self.payout_done = False

    @abstractmethod
    def is_finished(self) -> bool:
        pass

    @abstractmethod
    def is_cancelled(self) -> bool:
        pass

    @abstractmethod
    async def cancel(self, player: Optional[discord.Member]) -> None:
        pass

    @abstractmethod
    def accept(self, player: discord.Member) -> None:
        pass

    @abstractmethod
    async def get_content(self) -> Optional[str]:
        pass

    @abstractmethod
    async def get_embed(self) -> discord.Embed:
        pass

    @abstractmethod
    async def get_view(self) -> discord.ui.View:
        pass

    async def init(self) -> None:
        if self.init_done:
            return
        self.init_done = True
        if not await self.cog.is_economy_enabled(self.channel.guild):
            return
        if all(not player.bot for player in self.players):  # pvp
            for player in self.players:
                try:
                    await bank.withdraw_credits(player, self.bet)
                except ValueError:
                    pass  # Shouldn't happen, but I choose to let it continue if it breaks

    async def on_win(self, winner: Optional[discord.Member]) -> None:
        if self.payout_done:
            return
        self.payout_done = True
        if not await self.cog.is_economy_enabled(self.channel.guild):
            return
        against_bot = any(player.bot for player in self.players)
        if winner is None and against_bot:
            return
        await self.init() # failsafe
        if winner is None:
            for player in self.players:
                try:
                    await bank.deposit_credits(player, self.bet)
                except errors.BalanceTooHigh as error:
                    await bank.set_balance(player, error.max_balance)
        else:
            if not winner.bot:
                prize = self.bet if against_bot else self.bet * 2
                try:
                    await bank.deposit_credits(winner, prize)
                except errors.BalanceTooHigh as error:
                    await bank.set_balance(winner, error.max_balance)
