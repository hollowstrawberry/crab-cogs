import io
import re
import aiohttp
import discord
from dataclasses import dataclass
from itertools import zip_longest
from redbot.core import commands, app_commands
from typing import Optional, Union, List

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".gif", ".webp")

MISSING_EMOJIS = "Can't find emojis or stickers in that message."
MISSING_REFERENCE = "Reply to a message with this command to steal an emoji."
MISSING_ATTACHMENT = "You must upload an image when using this command."
MESSAGE_FAIL = "I couldn't grab that message, sorry."
UPLOADED_BY = "Uploaded by"
STICKER_DESC = "Stolen sticker"
STICKER_EMOJI = "😶"
STICKER_FAIL = "❌ Failed to upload sticker"
STICKER_SUCCESS = "✅ Uploaded sticker"
STICKER_SLOTS = "⚠ This server doesn't have any more space for stickers!"
EMOJI_FAIL = "❌ Failed to upload"
EMOJI_SLOTS = "⚠ This server doesn't have any more space for emojis!"
INVALID_EMOJI = "Invalid emoji or emoji ID."

@dataclass(init=True, order=True)
class StolenEmoji:
    animated: bool
    name: str
    id: int

    @property
    def url(self):
        return f"https://cdn.discordapp.com/emojis/{self.id}.{'gif' if self.animated else 'png'}"


class EmojiSteal(commands.Cog):
    """Steals emojis and stickers sent by other people and optionally uploads them to your own server. Supports context menu commands."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.steal_context = app_commands.ContextMenu(name='Steal Emojis', callback=self.steal_app_command)
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

    async def steal_ctx(self, ctx: commands.Context) -> Optional[List[Union[StolenEmoji, discord.StickerItem]]]:
        reference = ctx.message.reference
        if not reference:
            await ctx.send(MISSING_REFERENCE)
            return None
        message = await ctx.channel.fetch_message(reference.message_id)
        if not message:
            await ctx.send(MESSAGE_FAIL)
            return None
        if message.stickers:
            return message.stickers
        if not (emojis := self.get_emojis(message.content)):
            await ctx.send(MISSING_EMOJIS)
            return None
        return emojis

    @commands.group(name="steal", aliases=["emojisteal"], invoke_without_command=True)
    async def steal_command(self, ctx: commands.Context):
        """Steals the emojis and stickers of the message you reply to. Can also upload them with [p]steal upload."""
        if not (emojis := await self.steal_ctx(ctx)):
            return
        response = '\n'.join([emoji.url for emoji in emojis])
        await ctx.send(response)
    
    # context menu added in __init__
    async def steal_app_command(self, ctx: discord.Interaction, message: discord.Message):
        if message.stickers:
            emojis = message.stickers
        elif not (emojis := self.get_emojis(message.content)):
            return await ctx.response.send_message(MISSING_EMOJIS, ephemeral=True)
        response = '\n'.join([emoji.url for emoji in emojis])
        await ctx.response.send_message(content=response, ephemeral=True)

    @steal_command.command(name="upload")
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def steal_upload_command(self, ctx: commands.Context, *names: str):
        """Steals emojis and stickers you reply to and uploads them to this server."""
        if not (emojis := await self.steal_ctx(ctx)):
            return
        
        if isinstance(emojis[0], discord.StickerItem):
            if len(ctx.guild.stickers) >= ctx.guild.sticker_limit:
                return await ctx.send(STICKER_SLOTS)
            sticker = emojis[0]
            fp = io.BytesIO()
            try:
                await sticker.save(fp)
                await ctx.guild.create_sticker(name=sticker.name, description=STICKER_DESC, emoji=STICKER_EMOJI, file=discord.File(fp))
            except Exception as error:
                return await ctx.send(f"{STICKER_FAIL}, {type(error).__name__}: {error}")
            return await ctx.send(f"{STICKER_SUCCESS}: {sticker.name}")
        
        names = [''.join(re.findall(r"\w+", name)) for name in names]
        names = [name if len(name) >= 2 else None for name in names]
        clean_emojis = []
        for emoji in emojis:
            if emoji not in clean_emojis:
                clean_emojis.append(emoji)

        async with aiohttp.ClientSession() as session:
            for emoji, name in zip_longest(clean_emojis, names):
                if len(ctx.guild.emojis) >= ctx.guild.emoji_limit:
                    return await ctx.send(EMOJI_SLOTS)
                if not emoji:
                    break
                try:
                    async with session.get(emoji.url) as resp:
                        image = io.BytesIO(await resp.read()).read()
                    added = await ctx.guild.create_custom_emoji(name=name or emoji.name, image=image)
                except Exception as error:
                    return await ctx.send(f"{EMOJI_FAIL} {emoji.name}, {type(error).__name__}: {error}")
                try:
                    await ctx.message.add_reaction(added)
                except:
                    pass

    # context menu added in __init__
    async def steal_upload_slash(self, ctx: discord.Interaction, message: discord.Message):
        if message.stickers:
            emojis = message.stickers
        elif not (emojis := self.get_emojis(message.content)):
            return await ctx.response.send_message(MISSING_EMOJIS, ephemeral=True)
        
        await ctx.response.defer(thinking=True)
        
        if isinstance(emojis[0], discord.StickerItem):
            if len(ctx.guild.stickers) >= ctx.guild.sticker_limit:
                return await ctx.edit_original_response(content=STICKER_SLOTS)
            sticker = emojis[0]
            fp = io.BytesIO()
            try:
                await sticker.save(fp)
                await ctx.guild.create_sticker(
                    name=sticker.name, description=STICKER_DESC, emoji=STICKER_EMOJI, file=discord.File(fp))
            except Exception as error:
                return await ctx.edit_original_response(content=f"{STICKER_FAIL}, {type(error).__name__}: {error}")
            return await ctx.edit_original_response(content=f"{STICKER_SUCCESS}: {sticker.name}")
        
        clean_emojis = []
        for emoji in emojis:
            if emoji not in clean_emojis:
                clean_emojis.append(emoji)
        added_emojis = []
        async with aiohttp.ClientSession() as session:
            for emoji in clean_emojis:
                try:
                    async with session.get(emoji.url) as resp:
                        image = io.BytesIO(await resp.read()).read()
                    added = await ctx.guild.create_custom_emoji(name=emoji.name, image=image)
                except Exception as error:
                    response = f"{EMOJI_FAIL} {emoji.name}, {type(error).__name__}: {error}"
                    if added_emojis:
                        response = ' '.join([str(e) for e in added_emojis]) + '\n' + response
                    await ctx.edit_original_response(content=response)
                added_emojis.append(added)
        
        response = ' '.join([str(e) for e in added_emojis])
        await ctx.edit_original_response(content=response)

    @commands.command()
    async def getemoji(self, ctx: commands.Context, *, emoji: str):
        """Get the image link for custom emojis or an emoji ID."""
        emoji = emoji.strip()
        if emoji.isnumeric():
            emojis = [StolenEmoji(False, "e", int(emoji)), StolenEmoji(True, "e", emoji)]
        elif not (emojis := self.get_emojis(emoji)):
            await ctx.send(INVALID_EMOJI)
            return
        await ctx.send('\n'.join(emoji.url for emoji in emojis))

    @commands.command()
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def uploadsticker(self, ctx: commands.Context, *, name: str):
        """Uploads a sticker to the server, useful for mobile."""
        if len(ctx.guild.stickers) >= ctx.guild.sticker_limit:
            return await ctx.send(content=STICKER_SLOTS)
        if not ctx.message.attachments or not ctx.message.attachments[0].filename.endswith(IMAGE_TYPES):
            return await ctx.send(MISSING_ATTACHMENT)
        await ctx.typing()
        fp = io.BytesIO()
        try:
            await ctx.message.attachments[0].save(fp)
            sticker = await ctx.guild.create_sticker(
                name=name, description=f"{UPLOADED_BY} {ctx.author}", emoji=STICKER_EMOJI, file=discord.File(fp))
        except Exception as error:
            return await ctx.edit_original_response(content=f"{STICKER_FAIL}, {type(error).__name__}: {error}")
        return await ctx.send(f"{STICKER_SUCCESS}: {sticker.name}")
