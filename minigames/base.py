import discord
from abc import ABC, abstractmethod
from typing import List, Optional, Type, Union
from datetime import datetime
from redbot.core import commands, bank


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
                await bank.withdraw_credits(player, self.bet)

    async def on_win(self, winner: Optional[discord.Member]) -> None:
        if self.payout_done:
            return
        self.payout_done = True
        if not await self.cog.is_economy_enabled(self.channel.guild):
            return
        await self.init()
        if winner is None and any(player.bot for player in self.players):
            return
        for player in self.players:
            if not player.bot and (winner is None or winner == player):
                prize = self.bet if any(player.bot for player in self.players) else self.bet * 2
                await bank.deposit_credits(player, prize)
