import io
import asyncio
import discord
import aiohttp
import logging
from redbot.core import commands, app_commands, Config
from typing import Optional
from collections import OrderedDict
from PIL import Image

log = logging.getLogger("red.crab-cogs.imagescanner")

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
HEADERS = {
    "User-Agent": f"crab-cogs/v1 (https://github.com/hollowstrawberry/crab-cogs);"
}

class ImageScanner(commands.Cog):
    """Scans images for AI parameters and other metadata."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.scan_channels = set()
        self.config = Config.get_conf(self, identifier=7072707469)
        self.scan_limit = 10 * 1024**2
        self.attach_images = True
        self.use_civitai = True
        self.model_cache = {}
        defaults = {
            "channels": [],
            "scanlimit": self.scan_limit,
            "attach_images": self.attach_images,
            "use_civitai": self.use_civitai,
            "model_cache": {}
        }
        self.config.register_global(**defaults)
        self.context_menu = app_commands.ContextMenu(name='Image Info', callback=self.scanimage)
        self.bot.tree.add_command(self.context_menu)

    async def cog_load(self):
        self.scan_channels = set(await self.config.channels())
        self.scan_limit = await self.config.scanlimit()
        self.attach_images = await self.config.attach_images()
        self.use_civitai = await self.config.use_civitai()
        self.model_cache = await self.config.model_cache()

    async def cog_unload(self):
        self.bot.tree.remove_command(self.context_menu.name, type=self.context_menu.type)

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    # Static methods

    @staticmethod
    def get_params_from_string(param_str) -> dict:
        output_dict = {}
        parts = param_str.split('Steps: ')
        prompts = parts[0]
        promptkey = 'Prompt'
        if 'Negative prompt: ' in prompts:
            output_dict['Prompt'] = prompts.split('Negative prompt: ')[0]
            output_dict['Negative Prompt'] = prompts.split('Negative prompt: ')[1]
            if len(output_dict['Negative Prompt']) > 1000:
                output_dict['Negative Prompt'] = output_dict['Negative Prompt'][:1000] + '...'
        else:
            nai = prompts.split('NovelAI3 Prompt: ')
            if len(nai) > 1:
                promptkey = 'NovelAI3 Prompt'
                output_dict[promptkey] = nai[1]
            else:
                output_dict[promptkey] = prompts
        if len(output_dict[promptkey]) > 1000:
            output_dict[promptkey] = output_dict[promptkey][:1000] + '...'
        if len(parts) > 1:
            params = 'Steps: ' + parts[1]
            params = params.split(', ')
            for param in params:
                try:
                    key, value = param.split(': ')
                    output_dict[key] = value
                except ValueError:
                    pass
        return output_dict

    @staticmethod
    def get_embed(embed_dict: dict, author: discord.Member) -> discord.Embed:
        embed = discord.Embed(title="Here's your image!", color=author.color)
        for key, value in embed_dict.items():
            embed.add_field(name=key, value=value, inline='Prompt' not in key)
        embed.set_footer(text=f'Posted by {author}', icon_url=author.display_avatar.url)
        return embed

    @staticmethod
    async def read_attachment_metadata(i: int, attachment: discord.Attachment, metadata: OrderedDict):
        try:
            image_data = await attachment.read()
            with Image.open(io.BytesIO(image_data)) as img:
                try:
                    if attachment.filename.endswith(".png"):
                        info = img.info['parameters']
                    else:
                        info = img._getexif().get(37510).decode('utf8')[7:]
                    if info and "Steps" in info:
                        metadata[i] = info
                except:
                    if "Title" in img.info and img.info["Title"] == "AI generated image":
                        metadata[i] = "NovelAI3 Prompt: " + img.info['Description'].strip()

        except Exception as error:
            print(f"{type(error).__name__}: {error}")
        else:
            print("Downloaded", i)

    # Events

    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return await self.bot.allowed_by_whitelist_blacklist(message.author) \
               and await self.bot.ignored_channel_or_guild(message) \
               and not await self.bot.cog_disabled_in_guild(self, message.guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Scan images for AI metadata in allowed channels
        if not message.guild or message.author.bot or message.channel.id not in self.scan_channels:
            return
        channel_perms = message.channel.permissions_for(message.guild.me)
        if not channel_perms.add_reactions:
            return
        attachments = [a for a in message.attachments if a.filename.lower().endswith((".png", ".jpeg", ".jpg")) and a.size < self.scan_limit]
        if not attachments:
            return
        if not await self.is_valid_red_message(message):
            return
        for i, attachment in list(enumerate(attachments))[:2]:  # Scan first 2 images just in case
            metadata = OrderedDict()
            await self.read_attachment_metadata(i, attachment, metadata)
            if metadata:
                await message.add_reaction('🔎')
                return

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, ctx: discord.RawReactionActionEvent):
        """Send image metadata in reacted post to user DMs"""
        if ctx.emoji.name != '🔎' or ctx.member.bot or ctx.channel_id not in self.scan_channels:
            return
        channel = self.bot.get_channel(ctx.channel_id)
        message = await channel.fetch_message(ctx.message_id)
        if not message:
            return
        attachments = [a for a in message.attachments if a.filename.lower().endswith(IMAGE_TYPES)]
        if not attachments:
            return
        if not await self.is_valid_red_message(message):
            return
        metadata = OrderedDict()
        tasks = [self.read_attachment_metadata(i, attachment, metadata) for i, attachment in enumerate(attachments)]
        await asyncio.gather(*tasks)
        if not metadata:
            embed = self.get_embed({}, message.author)
            embed.description = f"This post contains no image generation data."
            embed.set_thumbnail(url=attachments[0].url)
            await ctx.member.send(embed=embed)
            return
        for i, attachment, data in [(i, attachments[i], data) for i, data in metadata.items()]:
            params = self.get_params_from_string(data)
            embed = self.get_embed(params, message.author)
            if len(metadata) > 1:
                embed.title += f" ({i+1}/{len(metadata)})"
                log.info(f"use_civitai: {self.use_civitai}")
            if self.use_civitai and "Model hash" in params:
                log.info(f"model hash: {params['Model hash']}")
                model_link = await self.grab_civitai_model_link(params["Model hash"])
                log.info(f"model link: {model_link}")
                if model_link:
                    embed.description = f"[🔗 Checkpoint on Civitai]({model_link})"
            if self.attach_images:
                img = io.BytesIO()
                try:
                    await attachment.save(img, use_cached=True)
                except:
                    file = None
                else:
                    file = discord.File(img, filename=attachment.filename)
                embed.set_image(url=f"attachment://{attachment.filename}")
                await ctx.member.send(embed=embed, file=file)
            else:
                embed.set_thumbnail(url=attachment.url)
                await ctx.member.send(embed=embed)

    # context menu set in __init__
    async def scanimage(self, ctx: discord.Interaction, message: discord.Message):
        """Get image metadata"""
        attachments = [a for a in message.attachments if a.filename.lower().endswith(IMAGE_TYPES)]
        if not attachments:
            await ctx.response.send_message("This post contains no images.", ephemeral=True)
            return
        # await ctx.defer(ephemeral=True)
        metadata = OrderedDict()
        tasks = [self.read_attachment_metadata(i, attachment, metadata) for i, attachment in enumerate(attachments)]
        await asyncio.gather(*tasks)
        if not metadata:
            for i, att in enumerate(attachments):
                size_kb, size_mb = round(att.size / 1024), round(att.size / 1024**2, 2)
                metadata[i] = f"Filename: {att.filename}, Dimensions: {att.width}x{att.height}, "\
                            + f"Filesize: " + (f"{size_mb} MB" if size_mb >= 1.0 else f"{size_kb} KB")
        response = "\n\n".join(metadata.values())
        if len(response) < 1980:
            await ctx.response.send_message(f"```yaml\n{response}```", ephemeral=True)
        else:
            with io.StringIO() as f:
                f.write(response)
                f.seek(0)
                await ctx.response.send_message(file=discord.File(f, "parameters.yaml"), ephemeral=True)

    async def grab_civitai_model_link(self, short_hash: str) -> Optional[str]:
        if short_hash in self.model_cache:
            model_id = self.model_cache[short_hash]
        else:
            url = f"https://civitai.com/api/v1/model-versions/by-hash/{short_hash}"
            try:
                async with aiohttp.ClientSession(headers=HEADERS) as session:
                    async with session.get(url) as resp:
                        data = await resp.json()
            except Exception as e:
                log.error("Trying to grab model from Civitai", exc_info=e)
                return None
            if not data or not "modelId" not in data:
                return None
            model_id = data['modelId']
            self.model_cache[short_hash] = model_id
            async with self.config.model_cache() as model_cache:
                model_cache[short_hash] = model_id
        return f"https://civitai.com/models/{model_id}"

    # Config commands

    @commands.group(invoke_without_command=True)
    @commands.is_owner()
    async def scanset(self, ctx: commands.Context):
        """Owner command to manage image scanner settings."""
        await ctx.send_help()

    @scanset.command(name="maxsize")
    async def scanset_maxsize(self, ctx: commands.Context, newlimit: Optional[int]):
        """Views or set the filesize limit for scanned images in MB."""
        if not newlimit or newlimit < 0 or newlimit > 1024:
            await ctx.reply(f"The current image scan limit is {self.scan_limit // 1024**2} MB.")
            return
        self.scan_limit = newlimit * 1024**2
        await self.config.scan_limit.set(self.scan_limit)
        await ctx.react_quietly("✅")

    @scanset.group(name="channel", invoke_without_command=True)
    async def scanset_channel(self, ctx: commands.Context):
        """Owner command to manage channels where images are scanned."""
        await ctx.send_help()

    @scanset_channel.command(name="add")
    async def scanset_channel_add(self, ctx: commands.Context, *, channels: str):
        """Add a list of channels by ID to the scan list."""
        try:
            channel_ids = [int(s.strip()) for s in channels.split(' ') if s.strip()]
        except:
            await ctx.reply("Please enter valid numbers as channel IDs")
            return
        self.scan_channels.update(ch for ch in channel_ids)
        await self.config.channels.set(list(self.scan_channels))
        await ctx.react_quietly("✅")

    @scanset_channel.command(name="remove")
    async def scanset_channel_remove(self, ctx: commands.Context, *, channels: str):
        """Remove a list of channels by ID from the scan list."""
        try:
            channel_ids = [int(s.strip()) for s in channels.split(' ') if s.strip()]
        except:
            await ctx.reply("Please enter valid numbers as channel IDs")
            return
        self.scan_channels.difference_update(ch for ch in channel_ids)
        await self.config.channels.set(list(self.scan_channels))
        await ctx.react_quietly("✅")

    @scanset_channel.command(name="list")
    async def scanset_channel_list(self, ctx: commands.Context):
        """Show all channels in the scan list."""
        await ctx.reply('\n'.join([f'<#{id}>' for id in self.scan_channels]) or "*None*")

    @scanset.command(name="attachimages")
    async def scanset_attachimages(self, ctx: commands.Context):
        """Toggles whether images sent in DMs will be attached or linked."""
        self.attach_images = not self.attach_images
        await self.config.attach_images.set(self.attach_images)
        if self.attach_images:
            await ctx.reply("Images sent in DMs will now be attached as a file and embedded in full size.")
        else:
            await ctx.reply("Images sent in DMs will now be added as a link and embedded as a thumbnail.")

    @scanset.command(name="civitai")
    async def scanset_civitai(self, ctx: commands.Context):
        """Toggles whether images should look for a model on Civitai."""
        self.use_civitai = not self.use_civitai
        await self.config.use_civitai.set(self.use_civitai)
        if self.use_civitai:
            await ctx.reply("Images sent in DMs will now try to find the used model on Civitai.")
        else:
            await ctx.reply("Images sent in DMs will no longer search for the model on Civitai.")
