import io
import re
import zipfile
import aiohttp
import discord
from typing import Optional, Union, List
from itertools import zip_longest
from redbot.core import commands, app_commands

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
STICKER_KB = 512
STICKER_DIM = 320
STICKER_TIME = 5

MISSING_EMOJIS = "Can't find emojis or stickers in that message."
MISSING_REFERENCE = "Reply to a message with this command to steal an emoji."
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
STICKER_TOO_BIG = f"Stickers may only be up to {STICKER_KB} KB and {STICKER_DIM}x{STICKER_DIM} pixels and last up to {STICKER_TIME} seconds."
STICKER_ATTACHMENT = """\
>>> For a non-moving sticker, simply use this command and attach a PNG image.
For a moving sticker, Discord limitations make it very annoying. Follow these steps:
1. Scale down and optimize your video/gif in <https://ezgif.com>
2. Convert it to APNG in that same website.
3. Download it and put it inside a zip file.
4. Use this command and attach that zip file.
\n**Important:** """ + STICKER_TOO_BIG


class EmojiSteal(commands.Cog):
    """Steals emojis and stickers sent by other people and optionally uploads them to your own server. Supports context menu commands."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.steal_context_menu = app_commands.ContextMenu(name='Steal Emotes', callback=self.steal_app_command)
        self.steal_upload_context_menu = app_commands.ContextMenu(name='Steal+Upload Emotes', callback=self.steal_upload_app_command)
        self.bot.tree.add_command(self.steal_context_menu)
        self.bot.tree.add_command(self.steal_upload_context_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.steal_context_menu.name, type=self.steal_context_menu.type)
        self.bot.tree.remove_command(self.steal_upload_context_menu.name, type=self.steal_upload_context_menu.type)

    @staticmethod
    def get_emojis(content: str) -> Optional[List[discord.PartialEmoji]]:
        results = re.findall(r"(<(a?):(\w+):(\d{10,20})>)", content)
        return [discord.PartialEmoji.from_str(result[0]) for result in results]
    
    @staticmethod
    def available_emoji_slots(guild: discord.Guild, animated: bool) -> int:
        current_emojis = len([em for em in guild.emojis if em.animated == animated])
        return guild.emoji_limit - current_emojis

    async def steal_ctx(self, ctx: commands.Context) -> Optional[List[Union[discord.PartialEmoji, discord.StickerItem]]]:
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
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True, add_reactions=True)
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
                await ctx.guild.create_sticker(
                    name=sticker.name, description=STICKER_DESC, emoji=STICKER_EMOJI, file=discord.File(fp))

            except discord.DiscordException as error:
                return await ctx.send(f"{STICKER_FAIL}, {type(error).__name__}: {error}")

            return await ctx.send(f"{STICKER_SUCCESS}: {sticker.name}")
        
        names = [''.join(re.findall(r"\w+", name)) for name in names]
        names = [name if len(name) >= 2 else None for name in names]
        emojis = list(dict.fromkeys(emojis))

        async with aiohttp.ClientSession() as session:
            for emoji, name in zip_longest(emojis, names):
                if not self.available_emoji_slots(ctx.guild, emoji.animated):
                    return await ctx.send(EMOJI_SLOTS)
                if not emoji:
                    break

                try:
                    async with session.get(emoji.url) as resp:
                        resp.raise_for_status()
                        image = io.BytesIO(await resp.read()).read()
                    added = await ctx.guild.create_custom_emoji(name=name or emoji.name, image=image)

                except (aiohttp.ClientError, discord.DiscordException) as error:
                    return await ctx.send(f"{EMOJI_FAIL} {emoji.name}, {type(error).__name__}: {error}")

                try:
                    await ctx.message.add_reaction(added)
                except discord.DiscordException:
                    pass  # fail silently to not interrupt the loop, ideally there'd be a summary at the end


    # context menu added in __init__
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_emojis=True)
    @app_commands.checks.bot_has_permissions(manage_emojis=True)
    async def steal_upload_app_command(self, ctx: discord.Interaction, message: discord.Message):
        if message.stickers:
            emojis: List[Union[discord.PartialEmoji, discord.StickerItem]] = message.stickers
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

            except discord.DiscordException as error:
                return await ctx.edit_original_response(content=f"{STICKER_FAIL}, {type(error).__name__}: {error}")

            return await ctx.edit_original_response(content=f"{STICKER_SUCCESS}: {sticker.name}")

        added_emojis = []
        emojis = list(dict.fromkeys(emojis))
        async with aiohttp.ClientSession() as session:
            for emoji in emojis:
                if not self.available_emoji_slots(ctx.guild, emoji.animated):
                    response = EMOJI_SLOTS
                    if added_emojis:
                        response = ' '.join([str(e) for e in added_emojis]) + '\n' + response
                    return await ctx.edit_original_response(content=response)

                try:
                    async with session.get(emoji.url) as resp:
                        resp.raise_for_status()
                        image = io.BytesIO(await resp.read()).read()
                    added = await ctx.guild.create_custom_emoji(name=emoji.name, image=image)

                except (aiohttp.ClientError, discord.DiscordException) as error:
                    response = f"{EMOJI_FAIL} {emoji.name}, {type(error).__name__}: {error}"
                    if added_emojis:
                        response = ' '.join([str(e) for e in added_emojis]) + '\n' + response
                    return await ctx.edit_original_response(content=response)

                added_emojis.append(added)
        
        response = ' '.join([str(e) for e in added_emojis])
        await ctx.edit_original_response(content=response)


    @commands.command()
    async def getemoji(self, ctx: commands.Context, *, emoji: str):
        """Get the image link for custom emojis or an emoji ID."""
        emoji = emoji.strip()

        if emoji.isnumeric():
            emojis = [discord.PartialEmoji(name="e", animated=b, id=int(emoji)) for b in [False, True]]
        elif not (emojis := self.get_emojis(emoji)):
            await ctx.send(INVALID_EMOJI)
            return

        await ctx.send('\n'.join(emoji.url for emoji in emojis))


    @commands.command()
    @commands.has_permissions(manage_emojis=True)
    @commands.bot_has_permissions(manage_emojis=True)
    async def uploadsticker(self, ctx: commands.Context, *, name: str = None):
        """Uploads a sticker to the server, useful for mobile."""
        if len(ctx.guild.stickers) >= ctx.guild.sticker_limit:
            return await ctx.send(content=STICKER_SLOTS)

        if not ctx.message.attachments or not ctx.message.attachments[0].filename.endswith((".png", ".zip")):
            return await ctx.send(STICKER_ATTACHMENT)

        attachment = ctx.message.attachments[0]
        if attachment.size > STICKER_KB * 1024 or attachment.width and attachment.width > STICKER_DIM or attachment.height and attachment.height > STICKER_DIM:
            return await ctx.send(STICKER_TOO_BIG)

        await ctx.typing()
        name = name or attachment.filename.split('.')[0]
        fp = io.BytesIO()

        try:
            await attachment.save(fp)

            if attachment.filename.endswith(".zip"):
                z = zipfile.ZipFile(fp)
                files = zipfile.ZipFile.namelist(z)
                file = next(f for f in files if f.endswith(".png"))
                if not file:
                    return await ctx.send(STICKER_ATTACHMENT)
                fp = io.BytesIO(z.read(file))

            sticker = await ctx.guild.create_sticker(
                name=name, description=f"{UPLOADED_BY} {ctx.author}", emoji=STICKER_EMOJI, file=discord.File(fp))

        except (discord.DiscordException, zipfile.BadZipFile) as error:
            if "exceed" in str(error):
                return await ctx.send(STICKER_TOO_BIG)
            return await ctx.send(f"{STICKER_FAIL}, {type(error).__name__}: {error}")

        return await ctx.send(f"{STICKER_SUCCESS}: {sticker.name}")
