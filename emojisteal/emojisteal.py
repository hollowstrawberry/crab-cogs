import io
import re
import aiohttp
import discord
from dataclasses import dataclass
from itertools import zip_longest
from redbot.core import commands, app_commands
from typing import Optional, Union, List


@dataclass(init=True, order=True)
class StolenEmoji:
    animated: bool
    name: str
    id: int

    @property
    def link(self):
        return f"https://cdn.discordapp.com/emojis/{self.id}.{'gif' if self.animated else 'png'}"


class EmojiSteal(commands.Cog):
    """Steals emojis sent by other people and optionally uploads them to your own server. Supports context menu commands."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.steal_context = app_commands.ContextMenu(name='Steal Emojis', callback=self.steal_slash)
        self.steal_upload_context = app_commands.ContextMenu(name='Steal+Upload Emojis', callback=self.steal_upload_slash)
        self.bot.tree.add_command(self.steal_context)
        self.bot.tree.add_command(self.steal_upload_context)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.steal_context.name, type=self.steal_context.type)
        self.bot.tree.remove_command(self.steal_upload_context.name, type=self.steal_upload_context.type)

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @staticmethod
    def get_emojis(content: str) -> Optional[List[StolenEmoji]]:
        results = re.findall(r"<(a?):(\w+):(\d{10,20})>", content)
        return [StolenEmoji(*result) for result in results]

    async def steal(self, *, message: discord.Message = None, ctx: commands.Context = None) -> Optional[List[StolenEmoji]]:
        if not message:
            reference = ctx.message.reference
            if not reference:
                await ctx.send("Reply to a message with this command to steal an emoji")
                return None
            message = await ctx.channel.fetch_message(reference.message_id)
        if not message:
            await ctx.send("I couldn't grab that message, sorry")
            return None
        if not (emojis := self.get_emojis(message.content)):
            await ctx.send("Can't find an emoji in that message")
            return None
        return emojis

    @commands.group(name="steal", aliases=["emojisteal", "stealemoji", "stealemojis"], invoke_without_command=True)
    async def steal_command(self, ctx: Union[commands.Context, discord.Interaction]):
        """Steals the emojis of the message you reply to. Can also upload them with [p]steal upload."""
        if isinstance(ctx, commands.Context):
            emojis = await self.steal(ctx=ctx)
        else:
            emojis = await self.steal(message=ctx.message)
        if not emojis:
            return
        response = '\n'.join([emoji.link for emoji in emojis])
        if isinstance(ctx, commands.Context):
            return await ctx.send(response)
        else:
            await ctx.response.send_message(content=response)

    @steal_command.command(name="upload")
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def steal_upload_command(self, ctx: Union[commands.Context, discord.Interaction], *names: str):
        """Steals emojis you reply to and uploads them to this server."""
        if isinstance(ctx, commands.Context):
            emojis = await self.steal(ctx=ctx)
        else:
            emojis = await self.steal(message=ctx.message)
        if not emojis:
            return
        names = [''.join(re.findall(r"\w+", name)) for name in names]
        names = [name if len(name) >= 2 else None for name in names]
        clean_emojis = []
        for emoji in emojis:
            if emoji not in clean_emojis:
                clean_emojis.append(emoji)
        added_emojis = []
        async with aiohttp.ClientSession() as session:
            for emoji, name in zip_longest(clean_emojis, names):
                if not emoji:
                    break
                try:
                    async with session.get(emoji.link) as resp:
                        image = io.BytesIO(await resp.read()).read()
                except Exception as error:
                    response = f"Couldn't download {emoji.name}, {type(error).__name__}: {error}"
                    if added_emojis:
                        response = ' '.join([str(e) for e in added_emojis]) + '\n' + response
                    if isinstance(ctx, commands.Context):
                        return await ctx.send(response)
                    else:
                        await ctx.edit_original_response(content=response)
                try:
                    added = await ctx.guild.create_custom_emoji(name=name or emoji.name, image=image)
                except Exception as error:
                    response = f"Couldn't upload {emoji.name}, {type(error).__name__}: {error}"
                    if added_emojis:
                        response = ' '.join([str(e) for e in added_emojis]) + '\n' + response
                    if isinstance(ctx, commands.Context):
                        return await ctx.send(response)
                    else:
                        await ctx.edit_original_response(content=response)
                added_emojis.append(added)
                if isinstance(ctx, commands.Context):
                    try:
                        await ctx.message.add_reaction(added)
                    except:
                        pass
        return added_emojis

    async def steal_slash(self, ctx: discord.Interaction, message: discord.Message):
        """Steals emojis from a message silently. Add this as a message slashtag."""
        ctx.message = message  # sigh
        await self.steal_command(ctx)

    async def steal_upload_slash(self, ctx: discord.Interaction, message: discord.Message):
        """Steals emojis from a message and uploads them to this guild. Add this as a message slashtag."""
        await ctx.response.send_message("Stealing...")
        ctx.message = message
        emojis = await self.steal_upload_command(ctx)
        if emojis:
            await ctx.edit_original_response(content=' '.join([str(e) for e in emojis]))

    @commands.command(aliases=["emojilink", "getemoji", "getimage"])
    async def getlink(self, ctx: commands.Context, *, emoji: Union[int, str]):
        """Get the image link for custom emojis or an emoji ID."""
        if isinstance(emoji, int):
            emojis = [StolenEmoji(False, "e", emoji), StolenEmoji(True, "e", emoji)]
        elif not (emojis := self.get_emojis(emoji)):
            await ctx.send("Invalid emoji or emoji ID")
            return
        await ctx.send('\n'.join(emoji.link for emoji in emojis))
