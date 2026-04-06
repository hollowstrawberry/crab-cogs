from typing import OrderedDict

import discord

from gelbooru.constants import RATING_GENERAL, RATING_PATTERN, TAG_BLACKLIST


def is_nsfw(channel: discord.abc.Messageable):
    if isinstance(channel, discord.TextChannel):
        return channel.nsfw
    elif isinstance(channel, discord.Thread) and channel.parent:
        return channel.parent.nsfw
    else:
        return False

def prepare_query(query: str, nsfw: bool) -> str:
    if not nsfw:
        query = RATING_PATTERN.sub("", query) + f" {RATING_GENERAL}"
    query = query.replace(",", " ")
    tags = OrderedDict.fromkeys([tag for tag in query.split(' ') if tag and tag not in TAG_BLACKLIST])
    tags.update(OrderedDict.fromkeys([f"-{tag}" for tag in TAG_BLACKLIST]))
    return " ".join(tags)
