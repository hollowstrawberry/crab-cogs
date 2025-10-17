import draughts
import discord
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime
from redbot.core import Config, commands, bank, errors
from redbot.core.bot import Red


class BaseCasinoCog(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.games: Dict[int, BaseCasinoGame] = {}
        self.config = Config.get_conf(self, identifier=766962065)
        default_currency = {
            "bjmin": 10,
            "bjmax": 1000,
            "bjtime": 5,
        }
        self.config.register_guild(**default_currency)
        self.config.register_global(**default_currency)


class BaseCasinoGame(ABC):
    def __init__(self,
                 cog: BaseCasinoCog,
                 players: List[discord.Member],
                 channel: discord.TextChannel):
        self.cog = cog
        self.players = players
        self.channel = channel
        self.last_interacted: datetime = datetime.now()
        self.message: Optional[discord.Message] = None
        self.view: Optional[discord.ui.View] = None
        self.init_done = False
        self.payout_done = False

    @abstractmethod
    def is_finished(self) -> bool:
        pass

    @abstractmethod
    def is_cancelled(self) -> bool:
        pass

    @abstractmethod
    async def cancel(self, member: Optional[discord.Member]) -> None:
        pass

    @abstractmethod
    async def move_user(self, move: str) -> Tuple[bool, str]:
        pass

    @abstractmethod
    async def move_engine(self) -> None:
        pass

    @abstractmethod
    async def update_message(self, interaction: Optional[discord.Interaction] = None) -> None:
        pass

    @abstractmethod
    async def save_state(self) -> None:
        pass

    def member(self, color: int):
        return self.players[0] if color == draughts.BLACK else self.players[1]
    
    async def start(self) -> None:
        self.accepted = True
        await self._init()
    
    async def _init(self) -> None:
        if self.init_done:
            return
        self.init_done = True
        if all(not player.bot for player in self.players):  # pvp
            for player in self.players:
                try:
                    await bank.withdraw_credits(player, self.bet)
                except ValueError:
                    pass  # Shouldn't happen, but I choose to let it continue if it breaks
        await self.save_state()

    async def _on_win(self, winner: Optional[discord.Member]) -> None:
        if self.payout_done:
            return
        self.payout_done = True
        against_bot = any(player.bot for player in self.players)
        if winner is None and against_bot:
            return
        await self._init() # failsafe
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
