import io
import asyncio
import discord
import aiohttp
import re
import json
import logging
from discord.ui import View
from redbot.core import commands, app_commands, Config
from PIL import Image
from typing import Optional
from collections import OrderedDict
from expiringdict import ExpiringDict

log = logging.getLogger("red.crab-cogs.imagescanner")

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
VIEW_TIMEOUT = 5*60

# language=RegExp
LOOKAHEAD_PATTERN = rf'(?=(?:[^"]*"[^"]*")*[^"]*$)'  # ensures the characters surrounding the lookahead are not inside quotes
PARAM_REGEX = re.compile(rf" ?([^:]+): (.+?),{LOOKAHEAD_PATTERN}")
PARAM_GROUP_REGEX = re.compile(rf", [^:]+: {{.+?{LOOKAHEAD_PATTERN}}}")
HASHES_GROUP_REGEX = re.compile(rf", Hashes: ({{.+?{LOOKAHEAD_PATTERN}}})")

PARAMS_BLACKLIST = [
    "Template", "hashes",
    "ADetailer confidence", "ADetailer mask", "ADetailer dilate", "ADetailer denoising",
    "ADetailer inpaint", "ADetailer version", "ADetailer prompt", "ADetailer use", "ADetailer checkpoint",
    "FreeU Stages", "FreeU Schedule",
    "Mimic", "Separate Feature Channels", "Scaling Startpoint", "Variability Measure",  # Dynamic thresholding
    "Interpolate Phi", "Threshold percentile", "CFG mode", "CFG scale min",
]
NAIV3_PARAMS = {
    "steps": "Steps",                       "width": "Width",                   "height": "Height",
    "seed": "Seed",                         "scale": "Guidance",                "cfg_rescale": "Guidance Rescale",
    "sampler": "Sampler",                   "sm": "SMEA",                       "sm_dyn": "DYN",
    "uncond_scale": "Undesired Strength",   "noise_schedule": "Noise Schedule", "request_type": "Operation",
}

HEADERS = {
    "User-Agent": f"crab-cogs/v1 (https://github.com/hollowstrawberry/crab-cogs);"
}


class ImageView(View):
    def __init__(self, params: str, embed: discord.Embed):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.params = params
        self.embed = embed
        self.pressed = False

    @discord.ui.button(emoji="🔧", label='View Full Parameters', style=discord.ButtonStyle.grey)
    async def view_full_parameters(self, ctx: discord.Interaction, _: discord.Button):
        if len(self.params) < 1980:
            await ctx.response.send_message(f"```yaml\n{self.params}```")  # noqa
        else:
            with io.StringIO() as f:
                f.write(self.params)
                f.seek(0)
                await ctx.response.send_message(file=discord.File(f, "parameters.yaml"))  # noqa
        await ctx.message.edit(view=None, embed=self.embed)
        self.pressed = True
        self.stop()


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
        self.model_cache = {}
        self.model_not_found_cache = ExpiringDict(max_len=100, max_age_seconds=24*60*60)
        self.image_cache: Optional[ExpiringDict] = None
        self.image_cache_size = 100
        defaults = {
            "channels": [],
            "scanlimit": self.scan_limit,
            "attach_images": self.attach_images,
            "use_civitai": self.use_civitai,
            "civitai_emoji": self.civitai_emoji,
            "model_cache_v2": {},
            "image_cache_size": self.image_cache_size,
        }
        self.config.register_global(**defaults)
        self.context_menu = app_commands.ContextMenu(name='Image Info', callback=self.scanimage)
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

    async def cog_unload(self):
        self.bot.tree.remove_command(self.context_menu.name, type=self.context_menu.type)
        self.image_cache.clear()

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @staticmethod
    def get_params_from_string(param_str: str) -> OrderedDict:
        output_dict = OrderedDict()
        if "NovelAI3 Parameters: " in param_str:
            prompts, params = param_str.split("NovelAI3 Parameters: ")
            output_dict["NovelAI3 Prompt"], output_dict["Negative Prompt"] = prompts.split("Negative prompt: ")
            param_dict = json.loads(params)
            for key, new_key in NAIV3_PARAMS.items():
                if key in param_dict:
                    output_dict[new_key] = str(param_dict[key])
        else:
            prompts, params = param_str.split("Steps: ", 1)
            output_dict["Prompt"], output_dict["Negative Prompt"] = prompts.split("Negative prompt: ")
            params = f"Steps: {params},"
            params = PARAM_GROUP_REGEX.sub("", params)
            param_list = PARAM_REGEX.findall(params)
            for key, value in param_list:
                if len(output_dict) > 24 or any(blacklisted in key for blacklisted in PARAMS_BLACKLIST):
                    continue
                output_dict[key] = value
        for key in output_dict:
            if len(output_dict[key]) > 1000:
                output_dict[key] = output_dict[key][:1000] + "..."
        return output_dict

    @staticmethod
    def get_embed(embed_dict: dict, author: discord.Member) -> discord.Embed:
        embed = discord.Embed(title="Here's your image!", color=author.color)
        for key, value in embed_dict.items():
            embed.add_field(name=key, value=value, inline='Prompt' not in key)
        embed.set_footer(text=f'Posted by {author}', icon_url=author.display_avatar.url)
        return embed

    @staticmethod
    async def read_attachment_metadata(i: int, attachment: discord.Attachment, metadata: dict, image_bytes: dict):
        try:
            image_data = await attachment.read()
            with Image.open(io.BytesIO(image_data)) as img:
                try:
                    if attachment.filename.endswith(".png"):
                        info = img.info['parameters']
                    else:  # jpeg jank
                        info = img._getexif().get(37510).decode('utf8')[7:]  # noqa
                    if info and "Steps" in info:
                        metadata[i] = info
                        image_bytes[i] = image_data
                except:  # novelai
                    if "Title" in img.info and img.info["Title"] == "AI generated image":
                        info = json.loads(img.info["Comment"])
                        prompt = info.pop('prompt')
                        negative_prompt = "Negative prompt: " + info.pop('uc')
                        metadata[i] = f"{prompt}\n{negative_prompt}\nNovelAI3 Parameters: {json.dumps(info)}"
                        image_bytes[i] = image_data
        except Exception as e:
            log.error("Downloading attachment", exc_info=e)

    @staticmethod
    def remove_field(embed: discord.Embed, field_name: str):
        for i, field in enumerate(embed.fields):
            if field.name == field_name:
                embed.remove_field(i)
                return

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
        metadata, image_bytes = {}, {}
        tasks = [self.read_attachment_metadata(i, attachment, metadata, image_bytes)
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
        if ctx.emoji.name != '🔎' or ctx.member.bot or ctx.channel_id not in self.scan_channels:
            return
        channel = self.bot.get_channel(ctx.channel_id)
        message: discord.Message = await channel.fetch_message(ctx.message_id)
        if not message:
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
            tasks = [self.read_attachment_metadata(i, attachment, metadata, image_bytes)
                     for i, attachment in enumerate(attachments)]
            await asyncio.gather(*tasks)
        if not metadata:
            embed = self.get_embed({}, message.author)
            embed.description = f"{message.jump_url}\nThis post contains no image generation data."
            embed.set_thumbnail(url=attachments[0].url)
            await ctx.member.send(embed=embed)
            return
        edit_tasks = []
        for i, data in sorted(metadata.items()):
            params = self.get_params_from_string(data)
            embed = self.get_embed(params, message.author)
            embed.description = message.jump_url if self.civitai_emoji else f":arrow_right: {message.jump_url}"
            if len(metadata) > 1:
                embed.title += f" ({i+1}/{len(metadata)})"
            if self.use_civitai:
                desc_ext = []
                if "Model hash" in params:
                    link = await self.grab_civitai_model_link(params["Model hash"])
                    if link:
                        desc_ext.append(f"[Model:{params['Model']}]({link})" if "Model" in params else f"[Model]({link})")
                        self.remove_field(embed, "Model hash")
                #  vae hashes seem to be bugged in automatic1111 webui
                self.remove_field(embed, "VAE hash")
                # if "VAE hash" in params:
                #     link = await self.grab_civitai_model_link(params["VAE hash"])
                #     if link:
                #         desc_ext.append(f"[VAE:{params['VAE']}]({link})" if "VAE" in params else f"[VAE]({link})")
                #         self.remove_field(embed, "VAE hash")
                if m := HASHES_GROUP_REGEX.search(data):
                    try:
                        hashes = json.loads(m.group(1))
                    except Exception as e:
                        log.error("Trying to parse Civitai hashes", exc_info=e)
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
                if len(attachments) > i:
                    filename = attachments[i].filename
                else:  # edge case where an individual image has been deleted off of a message
                    filename = f"{i}.png"
                file = discord.File(img, filename=filename)
                embed.set_image(url=f"attachment://{filename}")
                msg = await ctx.member.send(embed=embed, file=file, view=view)
            else:
                if len(attachments) > i:
                    embed.set_thumbnail(url=attachments[i].url)
                msg = await ctx.member.send(embed=embed, view=view)
            edit_tasks.append(self.edit_dm(view, embed, msg))
        await asyncio.sleep(VIEW_TIMEOUT)
        await asyncio.gather(*edit_tasks)

    @staticmethod
    async def edit_dm(view: ImageView, embed: discord.Embed, msg: discord.Message):
        if not view.pressed:
            await msg.edit(view=None, embed=embed)

    # context menu set in __init__
    async def scanimage(self, ctx: discord.Interaction, message: discord.Message):
        """Get image metadata"""
        attachments = [a for a in message.attachments if a.filename.lower().endswith(IMAGE_TYPES)]
        if not attachments:
            await ctx.response.send_message("This post contains no images.", ephemeral=True)  # noqa
            return
        # await ctx.defer(ephemeral=True)
        if message.id in self.image_cache:
            metadata, image_bytes = self.image_cache[message.id]
        else:
            metadata, image_bytes = {}, {}
            tasks = [self.read_attachment_metadata(i, attachment, metadata, image_bytes)
                     for i, attachment in enumerate(attachments)]
            await asyncio.gather(*tasks)
        if not metadata:
            for i, att in enumerate(attachments):
                size_kb, size_mb = round(att.size / 1024), round(att.size / 1024**2, 2)
                metadata[i] = f"Filename: {att.filename}, Dimensions: {att.width}x{att.height}, " \
                              f"Filesize: " + (f"{size_mb} MB" if size_mb >= 1.0 else f"{size_kb} KB")
        response = "\n\n".join([data for i, data in sorted(metadata.items())])
        if len(response) < 1980:
            await ctx.response.send_message(f"```yaml\n{response}```", ephemeral=True)  # noqa
        else:
            with io.StringIO() as f:
                f.write(response)
                f.seek(0)
                await ctx.response.send_message(file=discord.File(f, "parameters.yaml"), ephemeral=True)  # noqa

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
                        data = await resp.json()
            except Exception as e:
                log.error("Trying to grab model from Civitai", exc_info=e)
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
        except:
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
