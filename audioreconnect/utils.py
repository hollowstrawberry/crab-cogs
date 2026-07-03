import types
import logging
import asyncio
import discord
import lavalink
from typing import Optional
from dataclasses import dataclass
from redbot.core.bot import Red
from redbot.core._cli import ExitCodes
from redbot.cogs.audio.apis.persist_queue_wrapper import QueueInterface

log = logging.getLogger("red.crab-cogs.audioreconnect")

QUEUE_API_METHODS = { # the queue api is a singleton
    "fetch_all": None,
    "played": None,
    "enqueued": None,
    "drop": None,
    "delete_scheduled": None,
}

async def dummy_method(self, *args, **kwargs):
    return []

def pickle_track(track: lavalink.Track):
    state = track.__dict__.copy()
    if isinstance(state.get('requester'), (discord.Member, discord.User)):
        state['requester'] = state['requester'].id
    return (lavalink.Track.__new__, (lavalink.Track,), state)

def is_shutting_down(bot: Red) -> bool:
    return bot._shutdown_mode in (ExitCodes.SHUTDOWN, ExitCodes.RESTART)

async def neuter_persistent_queue(queue_api: QueueInterface):
    dummy = types.MethodType(dummy_method, queue_api)
    for method in QUEUE_API_METHODS:
        QUEUE_API_METHODS[method] = getattr(queue_api, method)
        setattr(queue_api, method, dummy)
    try:
        await asyncio.to_thread(queue_api.database.cursor().execute, queue_api.statement.drop_table)
    except Exception as error:
        log.warning(f"Failed to clear existing persist_queue database. {error.__class__.__name__}: {error}")
    log.info("Blocked builtin persist_queue behavior")

async def heal_persistent_queue(queue_api: QueueInterface):
    for method in QUEUE_API_METHODS:
        if QUEUE_API_METHODS[method] is not None:
            setattr(queue_api, method, QUEUE_API_METHODS[method])
            QUEUE_API_METHODS[method] = None
    try:
        await asyncio.to_thread(queue_api.database.cursor().execute, queue_api.statement.create_table)
    except Exception as error:
        log.error(f"Failed to recreate persist_queue database. {error.__class__.__name__}: {error}")
    log.info("Restored builtin persist_queue behavior")


@dataclass
class QueueState:
    guild_id: int
    position: int = 0
    queue_id: tuple[Optional[str], ...] = ()
    queue_pickle: Optional[str] = None
