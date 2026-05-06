import discord
from typing import List


def is_nsfw(channel: discord.abc.Messageable):
    if isinstance(channel, discord.TextChannel):
        return channel.nsfw
    elif isinstance(channel, discord.Thread) and channel.parent:
        return channel.parent.nsfw
    else:
        return False

def display_tags(tags: List[str]) -> str:
    return " ".join(f"`{tag}`" for tag in tags)
