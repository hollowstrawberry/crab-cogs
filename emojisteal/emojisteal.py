import io
import re
import aiohttp
from itertools import zip_longest
from redbot.core import commands
from typing import *

class EmojiSteal(commands.Cog):
    """Steals emojis sent by other people and optionally uploads them to your own server."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @staticmethod
    async def get_emojis(ctx: commands.Context) -> Optional[List[Tuple[str]]]:
        reference = ctx.message.reference
        if not reference:
            await ctx.send("Reply to a message with this command to steal an emoji")
            return
        message = reference.cached_message or await ctx.channel.fetch_message(reference.message_id)
        if not message:
            await ctx.send("I couldn't grab that message, sorry")
            return
        emojis = re.findall(r"<(a?):(\w+):(\d{10,20})>", message.content)
        if not emojis:
            await ctx.send("Can't find an emoji in that message")
            return
        return emojis

    @commands.group(invoke_without_command=True)
    async def steal(self, ctx: commands.Context):
        """Steals the emojis of the message you reply to."""
        if not (emojis := await self.get_emojis(ctx)):
            return
        links = [f"https://cdn.discordapp.com/emojis/{m[2]}.{'gif' if m[0] else 'png'}" for m in emojis]
        await ctx.send('\n'.join(links))

    @steal.command()
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def upload(self, ctx: commands.Context, *names: str):
        """Steals emojis you reply to and uploads them to this server."""
        if not ctx.message.author.guild_permissions.manage_emojis:
            await ctx.send("You don't have permission to manage emojis")
            return
        if not (emojis := await self.get_emojis(ctx)):
            return
        names = [''.join(re.findall(r"\w+", name)) for name in names]
        names = [name if len(name) >= 2 else None for name in names]
        async with aiohttp.ClientSession() as session:
            for emoji, name in zip_longest(emojis, names):
                if not emoji:
                    break
                link = f"https://cdn.discordapp.com/emojis/{emoji[2]}.{'gif' if emoji[0] else 'png'}"
                try:
                    async with session.get(link) as resp:
                        image = io.BytesIO(await resp.read()).read()
                except Exception as error:
                    await ctx.send(f"Couldn't download {emoji[1]}, {type(error).__name__}: {error}")
                    return
                try:
                    added = await ctx.guild.create_custom_emoji(name=name or emoji[1], image=image)
                except Exception as error:
                    await ctx.send(f"Couldn't upload {emoji[1]}, {type(error).__name__}: {error}")
                    return
                try:
                    await ctx.message.add_reaction(added)
                except:
                    pass
