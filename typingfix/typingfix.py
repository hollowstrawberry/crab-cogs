import logging
import asyncio
from typing import Callable, Optional
from discord.context_managers import Typing
from redbot.core import commands

log = logging.getLogger("red.crab-cogs.typingfix")

INTERVAL = 5.0
TIMEOUT = 2.0

async def patched_typer(self: Typing):
    try:
        channel = await self._get_channel()
        await asyncio.wait_for(channel._state.http.send_typing(channel.id), timeout=TIMEOUT)
    except Exception:
        pass

async def patched_aenter(self: Typing):
    async def do_typing():
        try:
            channel = await self._get_channel()
            while True:
                await asyncio.wait_for(channel._state.http.send_typing(channel.id), timeout=TIMEOUT)
                await asyncio.sleep(INTERVAL)
        except (asyncio.CancelledError, Exception):
            pass
    self.task = self.loop.create_task(do_typing())


class TypingFix(commands.Cog):
    """Lets the bot work normally even if "bot is typing..." breaks on Discord's end."""

    original_typer: Optional[Callable] = None
    original_aenter: Optional[Callable] = None
    
    def cog_load(self):
        self.original_typer, Typing.wrapped_typer = Typing.wrapped_typer, patched_typer
        self.original_aenter, Typing.__aenter__ = Typing.__aenter__, patched_aenter
        log.info("Patched the typing indicator")
        
    def cog_unload(self):
        Typing.wrapped_typer = self.original_typer
        Typing.__aenter__ = self.original_aenter
        log.info("Unpatched the typing indicator")
