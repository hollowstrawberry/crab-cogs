import io
import re
import aiohttp
from dataclasses import dataclass
from itertools import zip_longest
from redbot.core import commands
from typing import *


@dataclass(init=True, order=True)
class StolenEmoji:
    animated: bool
    name: str
    id: int

    @property
    def link(self):
        return f"https://cdn.discordapp.com/emojis/{self.id}.{'gif' if self.animated else 'png'}"


class EmojiSteal(commands.Cog):
    """Steals emojis sent by other people and optionally uploads them to your own server."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @staticmethod
    def get_emojis(content: str) -> Optional[List[StolenEmoji]]:
        results = re.findall(r"<(a?):(\w+):(\d{10,20})>", content)
        return [StolenEmoji(*result) for result in results]

    async def ctx_steal(self, ctx: commands.Context, message) -> Optional[List[StolenEmoji]]:
        if not message:
            reference = ctx.message.reference
            if not reference:
                await ctx.send("Reply to a message with this command to steal an emoji")
                return None
            message = reference.cached_message or await ctx.channel.fetch_message(reference.message_id)
        if not message:
            await ctx.send("I couldn't grab that message, sorry")
            return None
        if not (emojis := self.get_emojis(message.content)):
            await ctx.send("Can't find an emoji in that message")
            return None
        return emojis

    @commands.group(aliases=["emojisteal", "stealemoji", "stealemojis"], invoke_without_command=True)
    async def steal(self, ctx: commands.Context, message=None):
        """Steals the emojis of the message you reply to. Can also upload them with [p]steal upload."""
        if not (emojis := await self.ctx_steal(ctx, messsge)):
            return
        await ctx.send('\n'.join(emoji.link for emoji in emojis))

    @steal.command()
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def upload(self, ctx: commands.Context, *names: str):
        """Steals emojis you reply to and uploads them to this server."""
        if not (emojis := await self.ctx_steal(ctx)):
            return
        names = [''.join(re.findall(r"\w+", name)) for name in names]
        names = [name if len(name) >= 2 else None for name in names]
        async with aiohttp.ClientSession() as session:
            for emoji, name in zip_longest(emojis, names):
                if not emoji:
                    break
                try:
                    async with session.get(emoji.link) as resp:
                        image = io.BytesIO(await resp.read()).read()
                except Exception as error:
                    await ctx.send(f"Couldn't download {emoji.name}, {type(error).__name__}: {error}")
                    return
                try:
                    added = await ctx.guild.create_custom_emoji(name=name or emoji.name, image=image)
                except Exception as error:
                    await ctx.send(f"Couldn't upload {emoji.name}, {type(error).__name__}: {error}")
                    return
                try:
                    await ctx.message.add_reaction(added)
                except:
                    pass

    @commands.command(aliases=["emojilink", "getemoji", "getimage"])
    async def getlink(self, ctx: commands.Context, *, emoji: Union[int, str]):
        """Get the image link for custom emojis or an emoji ID."""
        if isinstance(emoji, int):
            emojis = [StolenEmoji(False, "e", emoji), StolenEmoji(True, "e", emoji)]
        elif not (emojis := self.get_emojis(emoji)):
            await ctx.send("Invalid emoji or emoji ID")
            return
        await ctx.send('\n'.join(emoji.link for emoji in emojis))
