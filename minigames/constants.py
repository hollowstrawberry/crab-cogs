import discord
from discord.ext import commands
from typing import Any, Awaitable, Callable, Optional

TwoPlayerGameCommand = Callable[[commands.Context, Optional[discord.Member]], Awaitable[Any]]
