import io
import re
import json
import asyncio
import aiohttp
import discord
from hashlib import md5
from typing import Optional, Any, Dict, Tuple
from expiringdict import ExpiringDict
from redbot.core import commands, app_commands, Config
from sd_prompt_reader.constants import SUPPORTED_FORMATS

import imagescanner.utils as utils
from imagescanner.imageview import ImageView
from imagescanner.constants import log, IMAGE_TYPES, HASHES_GROUP_REGEX, HEADERS

ImageCache = ExpiringDict[int, Tuple[Dict[int, str], Dict[int, bytes]]]


class ImageScanner(commands.Cog):
    """Scans images for AI parameters and other metadata."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7072707469)
        self.scan_channels = set()
        self.scan_limit = 10 * 1024**2
        self.attach_images = True
        self.use_civitai = True
        self.civitai_emoji = ""
        self.model_cache: Dict[str, Tuple[Any, Any]] = {}
        self.model_not_found_cache: Dict[str, bool] = ExpiringDict(max_len=100, max_age_seconds=24*60*60)
        self.image_cache: Optional[ImageCache] = None
        self.image_cache_size = 100
        self.always_scan_generated_images = False
        defaults = {
            "channels": [],
            "scanlimit": self.scan_limit,
            "attach_images": self.attach_images,
            "use_civitai": self.use_civitai,
            "civitai_emoji": self.civitai_emoji,
            "model_cache_v2": {},
            "image_cache_size": self.image_cache_size,
            "always_scan_generated_images": self.always_scan_generated_images
        }
        self.config.register_global(**defaults)
        self.context_menu = app_commands.ContextMenu(name="Image Info", callback=self.scanimage)
        self.bot.tree.add_command(self.context_menu)

    async def cog_load(self):
        self.scan_channels = set(await self.config.channels())
        self.scan_limit = await self.config.scanlimit()
        self.attach_images = await self.config.attach_images()
        self.use_civitai = await self.config.use_civitai()
        self.civitai_emoji = await self.config.civitai_emoji()
        self.model_cache = await self.config.model_cache_v2()
        self.image_cache_size = await self.config.image_cache_size()
        self.image_cache = ExpiringDict(max_len=self.image_cache_size, max_age_seconds=24*60*60)
        self.always_scan_generated_images = await self.config.always_scan_generated_images()

    async def cog_unload(self):
        self.bot.tree.remove_command(self.context_menu.name, type=self.context_menu.type)
        self.image_cache.clear()

    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return await self.bot.allowed_by_whitelist_blacklist(message.author) \
               and await self.bot.ignored_channel_or_guild(message) \
               and not await self.bot.cog_disabled_in_guild(self, message.guild)

    @staticmethod
    def convert_novelai_info(img_info: dict):  # used by novelai cog
        return utils.convert_novelai_info(img_info)


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Scan images for AI metadata in allowed channels"""
        if not message.guild or message.author.bot or message.channel.id not in self.scan_channels:
            return
        channel_perms = message.channel.permissions_for(message.guild.me)
        if not channel_perms.add_reactions:
            return
        attachments = [a for a in message.attachments if a.filename.lower().endswith(tuple(SUPPORTED_FORMATS)) and a.size < self.scan_limit]
        if not attachments:
            return
        if not await self.is_valid_red_message(message):
            return

        metadata: Dict[int, str] = {}
        image_bytes: [Dict[int, bytes]] = {}
        tasks = [utils.read_attachment_metadata(i, attachment, metadata, image_bytes)
                 for i, attachment in enumerate(attachments)]
        await asyncio.gather(*tasks)

        if metadata:
            if self.image_cache_size > 0:
                self.image_cache[message.id] = (metadata, image_bytes)
            await message.add_reaction('🔎')
        else:
            self.image_cache[message.id] = ({}, {})


    @commands.Cog.listener()
    async def on_raw_reaction_add(self, ctx: discord.RawReactionActionEvent):
        """Send image metadata in reacted post to user DMs"""
        if ctx.emoji.name != '🔎' or not ctx.member or ctx.member.bot:
            return
        if ctx.channel_id not in self.scan_channels and not self.always_scan_generated_images:
            return

        channel = self.bot.get_channel(ctx.channel_id)
        message: discord.Message = await channel.fetch_message(ctx.message_id)
        if not message or message.author.bot and message.author.id != self.bot.user.id:
            return
        if ctx.channel_id not in self.scan_channels and message.author.id != self.bot.user.id:
            return

        attachments = [a for a in message.attachments if a.filename.lower().endswith(IMAGE_TYPES)]
        if not attachments:
            return

        if not await self.is_valid_red_message(message):
            return

        if message.id in self.image_cache:
            metadata, image_bytes = self.image_cache[message.id]
        else:
            metadata, image_bytes = {}, {}
            tasks = [utils.read_attachment_metadata(i, attachment, metadata, image_bytes)
                     for i, attachment in enumerate(attachments)]
            await asyncio.gather(*tasks)

        if not metadata:
            embed = utils.get_embed({}, message.author)
            embed.description = f"{message.jump_url}\nThis post contains no image generation data."
            embed.set_thumbnail(url=attachments[0].url)
            try:
                await ctx.member.send(embed=embed)
            except discord.Forbidden:
                log.info(f"User {ctx.member.id} does not accept DMs")
            return

        for i, data in sorted(metadata.items()):
            params = utils.get_params_from_string(data)
            embed = utils.get_embed(params, message.author)
            embed.description = message.jump_url if self.civitai_emoji else f":arrow_right: {message.jump_url}"
            if len(metadata) > 1:
                embed.title += f" ({i+1}/{len(metadata)})"

            if self.use_civitai:
                desc_ext = []
                if "Model hash" in params:
                    link = await self.grab_civitai_model_link(params["Model hash"])
                    if link:
                        desc_ext.append(f"[Model:{params['Model']}]({link})" if "Model" in params else f"[Model]({link})")
                        utils.remove_field(embed, "Model hash")
                #  vae hashes seem to be bugged in automatic1111 webui
                utils.remove_field(embed, "VAE hash")
                # if "VAE hash" in params:
                #     link = await self.grab_civitai_model_link(params["VAE hash"])
                #     if link:
                #         desc_ext.append(f"[VAE:{params['VAE']}]({link})" if "VAE" in params else f"[VAE]({link})")
                #         self.remove_field(embed, "VAE hash")
                if m := HASHES_GROUP_REGEX.search(data):
                    try:
                        hashes = json.loads(m.group(1))
                    except json.JSONDecodeError:
                        log.exception("Trying to parse Civitai hashes")
                    else:
                        hashes["model"] = None
                        hashes["vae"] = None
                        links = {name: await self.grab_civitai_model_link(short_hash)
                                 for name, short_hash in hashes.items()}
                        for name, link in links.items():
                            if link:
                                desc_ext.append(f"[{name}]({link})")
                if desc_ext:
                    embed.description += f"\n{self.civitai_emoji} " if self.civitai_emoji else "\n🔗 **Civitai:** "
                    embed.description += ", ".join(desc_ext)

            view = ImageView(data, embed)
            if self.attach_images and i in image_bytes:
                img = io.BytesIO(image_bytes[i])
                filename = md5(image_bytes[i]).hexdigest() + ".png"
                file = discord.File(img, filename=filename)
                embed.set_image(url=f"attachment://{filename}")
                try:
                    msg = await ctx.member.send(embed=embed, file=file, view=view)
                    view.message = msg
                except discord.Forbidden:
                    log.info(f"User {ctx.member.id} does not accept DMs")
            else:
                if len(attachments) > i:
                    embed.set_thumbnail(url=attachments[i].url)
                try:
                    msg = await ctx.member.send(embed=embed, view=view)
                    view.message = msg
                except discord.Forbidden:
                    log.info(f"User {ctx.member.id} does not accept DMs")


    # context menu set in __init__
    async def scanimage(self, ctx: discord.Interaction, message: discord.Message):
        """Get image metadata"""
        attachments = [a for a in message.attachments if a.filename.lower().endswith(IMAGE_TYPES)]
        if not attachments:
            await ctx.response.send_message("This post contains no images.", ephemeral=True)
            return
        if message.id in self.image_cache:
            metadata, image_bytes = self.image_cache[message.id]
        else:
            metadata, image_bytes = {}, {}
            tasks = [utils.read_attachment_metadata(i, attachment, metadata, image_bytes)
                     for i, attachment in enumerate(attachments)]
            await asyncio.gather(*tasks)
        if not metadata:
            metadata = {}  # Don't overwrite the cache in an edge case
            for i, att in enumerate(attachments):
                size_kb, size_mb = round(att.size / 1024), round(att.size / 1024**2, 2)
                metadata[i] = f"Filename: {att.filename}, Dimensions: {att.width}x{att.height}, " \
                              f"Filesize: " + (f"{size_mb} MB" if size_mb >= 1.0 else f"{size_kb} KB")
        response = "\n\n".join([data for i, data in sorted(metadata.items())]).strip(", \n")
        if len(response) < 1980:
            await ctx.response.send_message(f"```yaml\n{response}```", ephemeral=True)
        else:
            with io.StringIO() as f:
                f.write(response)
                f.seek(0)
                await ctx.response.send_message(file=discord.File(f, "parameters.yaml"), ephemeral=True)  # noqa, reason, StringIO works


    async def grab_civitai_model_link(self, short_hash: str) -> Optional[str]:
        if not short_hash:
            return None
        elif short_hash in self.model_cache:
            model_id = self.model_cache[short_hash]
        elif short_hash in self.model_not_found_cache:
            return None
        else:
            url = f"https://civitai.com/api/v1/model-versions/by-hash/{short_hash}"
            try:
                async with aiohttp.ClientSession(headers=HEADERS) as session:
                    async with session.get(url) as resp:
                        resp.raise_for_status()
                        data = await resp.json()
            except aiohttp.ClientError:
                log.exception("Trying to grab model from Civitai")
                return None

            if not data or "modelId" not in data:
                self.model_not_found_cache[short_hash] = True
                return None
            model_id = (data['modelId'], data['id'])
            self.model_cache[short_hash] = model_id
            async with self.config.model_cache_v2() as model_cache:
                model_cache[short_hash] = model_id

        return f"https://civitai.com/models/{model_id[0]}?modelVersionId={model_id[1]}"


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
        await ctx.tick()

    @scanset.group(name="channel", invoke_without_command=True)
    async def scanset_channel(self, ctx: commands.Context):
        """Owner command to manage channels where images are scanned."""
        await ctx.send_help()

    @scanset_channel.command(name="add")
    async def scanset_channel_add(self, ctx: commands.Context, *, channels: str):
        """Add a list of channels by ID to the scan list."""
        channel_ids = [int(ch) for ch in re.findall(r"([0-9]+)", channels)]
        if not channel_ids:
            return await ctx.reply("Please enter one or more valid channels.")
        self.scan_channels.update(ch for ch in channel_ids)
        await self.config.channels.set(list(self.scan_channels))
        await ctx.tick()

    @scanset_channel.command(name="remove")
    async def scanset_channel_remove(self, ctx: commands.Context, *, channels: str):
        """Remove a list of channels from the scan list."""
        channel_ids = [int(ch) for ch in re.findall(r"([0-9]+)", channels)]
        if not channel_ids:
            return await ctx.reply("Please enter one or more valid channels.")
        self.scan_channels.difference_update(ch for ch in channel_ids)
        await self.config.channels.set(list(self.scan_channels))
        await ctx.tick()

    @scanset_channel.command(name="list")
    async def scanset_channel_list(self, ctx: commands.Context):
        """Show all channels in the scan list."""
        await ctx.reply('\n'.join([f'<#{cid}>' for cid in self.scan_channels]) or "*None*")

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
        """Toggles whether images should look for models on Civitai."""
        self.use_civitai = not self.use_civitai
        await self.config.use_civitai.set(self.use_civitai)
        if self.use_civitai:
            await ctx.reply("Images sent in DMs will now try to find models on Civitai.")
        else:
            await ctx.reply("Images sent in DMs will no longer search for models on Civitai.")

    @scanset.command(name="civitaiemoji")
    async def scanset_civitaiemoji(self, ctx: commands.Context, emoji: Optional[discord.Emoji]):
        """Add your own Civitai custom emoji with this command."""
        if emoji is None:
            self.civitai_emoji = ""
            await self.config.civitai_emoji.set("")
            await ctx.reply(f"No emoji will appear when Civitai links are shown to users, only the word \"Civitai\".")
            return
        try:
            await ctx.react_quietly(emoji)
        except (discord.NotFound, discord.Forbidden):
            await ctx.reply("I don't have access to that emoji. I must be in the same server to use it.")
        else:
            self.civitai_emoji = str(emoji)
            await self.config.civitai_emoji.set(str(emoji))
            await ctx.reply(f"{emoji} will now appear when Civitai links are shown to users.")

    @scanset.command(name="cache")
    async def scanset_cache(self, ctx: commands.Context, size: Optional[int]):
        """How many images to cache in memory."""
        if size is None:
            size = await self.config.image_cache_size()
            await ctx.reply(f"Up to {size} recent images will be cached in memory to prevent duplicate downloads. "
                            f"Images are removed from cache after 24 hours.")
        elif size < 0 or size > 1000:
            await ctx.reply("Please choose a value between 0 and 1000, or none to see the current value.")
        else:
            await self.config.image_cache_size.set(size)
            await ctx.reply(f"Up to {size} recent images will be cached in memory to prevent duplicate downloads. "
                            f"Images are removed from cache after 24 hours."
                            f"\nRequires a cog reload to apply the new value, which will clear the cache.")
            
    @scanset.command(name="scangenerated")
    async def scanset_scangenerated(self, ctx: commands.Context):
        """Toggles always scanning images generated by the bot itself, regardless of channel whitelisting in ImageScanner."""
        always_scan_generated_images = not await self.config.always_scan_generated_images()
        await self.config.always_scan_generated_images.set(always_scan_generated_images)
        if always_scan_generated_images:
            await ctx.reply("Scanning of images generated by the bot always enabled.")
        else:
            await ctx.reply("Scanning of images generated by the bot enabled only for ImageScanner whistelisted channels.")
