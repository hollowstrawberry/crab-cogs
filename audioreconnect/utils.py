import types
import logging
import asyncio
import discord
import lavalink
import itertools
from typing import Optional
from dataclasses import dataclass
from redbot.core.bot import Red
from redbot.core._cli import ExitCodes
from redbot.cogs.audio.apis.persist_queue_wrapper import QueueInterface

log = logging.getLogger("red.crab-cogs.audioreconnect")

QUEUE_API: Optional[QueueInterface] = None
QUEUE_API_METHODS = {
    # technically we only need to override fetch_all to disable the persist_queue behavior
    # but might as well get rid of the overhead of useless database operations
    "fetch_all": None,
    "played": None,
    "enqueued": None,
    "drop": None,
    "delete_scheduled": None,
}

def all_lavalink_players():
    nodes = lavalink.get_all_nodes()
    return list(itertools.chain(*[list(node.players) for node in nodes]))

def pickle_track(track: lavalink.Track):
    state = track.__dict__.copy()
    if isinstance(state.get('requester'), (discord.Member, discord.User)):
        state['requester'] = state['requester'].id
    return (lavalink.Track.__new__, (lavalink.Track,), state)

def is_shutting_down(bot: Red) -> bool:
    # yes we will rely on internal values, I don't like it but it's the cleanest way
    return bot._shutdown_mode in (ExitCodes.SHUTDOWN, ExitCodes.RESTART)

async def dummy_method(self, *args, **kwargs):
    return []

async def neuter_persistent_queue(queue_api: QueueInterface):
    # I know this cog relies a lot on internal behavior, but I think it's worth it.
    # Plus this behavior hasn't changed at all in over 4 years as of 3.5.24
    global QUEUE_API, QUEUE_API_METHODS
    QUEUE_API = queue_api
    dummy = types.MethodType(dummy_method, QUEUE_API)
    for method in QUEUE_API_METHODS:
        QUEUE_API_METHODS[method] = getattr(QUEUE_API, method)
        setattr(QUEUE_API, method, dummy)
    try:
        # I want to prevent desyncs if my cog gets manually disabled
        await asyncio.to_thread(QUEUE_API.database.cursor().execute, QUEUE_API.statement.drop_table)
    except Exception as error:
        log.warning(f"Failed to clear existing persist_queue database. {error.__class__.__name__}: {error}")
    log.info("Blocked builtin persist_queue behavior")

async def heal_persistent_queue():
    global QUEUE_API, QUEUE_API_METHODS
    if not QUEUE_API:
        return
    for method in QUEUE_API_METHODS:
        setattr(QUEUE_API, method, QUEUE_API_METHODS[method])
        QUEUE_API_METHODS[method] = None
    try:
        await asyncio.to_thread(QUEUE_API.database.cursor().execute, QUEUE_API.statement.create_table)
    except Exception as error:
        log.error(f"Failed to recreate persist_queue database. {error.__class__.__name__}: {error}")
    QUEUE_API = None
    log.info("Restored builtin persist_queue behavior")


@dataclass
class QueueState:
    guild_id: int
    position: int = 0
    queue_id: tuple[Optional[str], ...] = ()
    queue_pickle: Optional[str] = None
