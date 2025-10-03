import discord
from typing import List, Optional
from abc import ABC, abstractmethod
from datetime import datetime


class Minigame(ABC):
    def __init__(self, players: List[discord.Member], channel: discord.TextChannel):
        self.players = players
        self.channel = channel
        self.message: Optional[discord.Message] = None
        self.last_interacted: datetime = datetime.now()

    @abstractmethod
    def is_finished(self) -> bool:
        pass
