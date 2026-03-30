import io
import os
import asyncio
import aiohttp
import discord
from hashlib import md5
from expiringdict import ExpiringDict
from redbot.core import commands, app_commands
from redbot.core.bot import Red
from sd_prompt_reader.constants import SUPPORTED_FORMATS
from sd_prompt_reader.image_data_reader import ImageDataReader

import imagescanner.utils as utils
from imagescanner.comfy import ComfyMetadata, ComfyMetadataReader
from imagescanner.commands import ImageScannerCommands
from imagescanner.constants import log, IMAGE_TYPES, PARAM_REGEX, RESOURCE_HASH_REGEX, RESOURCE_FILE_REGEX
from imagescanner.imageview import ImageView

MODEL = "Model"
MODEL_HASH = "Model hash"
VAE_HASH = "VAE hash"
LORA_HASHES = "Lora hashes"


class ImageScanner(ImageScannerCommands):
    """Scans images for AI generation metadata, including A1111, ComfyUI, SwarmUI, and NovelAI."""

    def __init__(self, bot: Red):
        super().__init__(bot)
        self.context_menu = app_commands.ContextMenu(name="Image Info", callback=self.scanimage_app)
        self.bot.tree.add_command(self.context_menu)

    async def cog_load(self):
        self.scan_channels = set(await self.config.channels())
        self.scan_limit = await self.config.scanlimit()
        self.attach_images = await self.config.attach_images()
        self.use_civitai = await self.config.use_civitai()
        self.civitai_emoji = await self.config.civitai_emoji()
        self.use_arcenciel = await self.config.use_arcenciel()
        self.arcenciel_emoji = await self.config.arcenciel_emoji()
        self.model_cache_civitai = await self.config.model_cache_v2()
        self.model_cache_arcenciel = await self.config.model_cache_arcenciel()
        log.info(f"model cache {self.model_cache_arcenciel}")
        self.image_cache_size = await self.config.image_cache_size()
        self.image_cache = ExpiringDict(max_len=self.image_cache_size, max_age_seconds=24*60*60)
        self.always_scan_generated_images = await self.config.always_scan_generated_images()

    async def cog_unload(self):
        self.bot.tree.remove_command(self.context_menu.name, type=self.context_menu.type)
        if self.image_cache:
            self.image_cache.clear()
        if self.session:
            await self.session.close()

    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return await self.bot.allowed_by_whitelist_blacklist(message.author) \
               and await self.bot.ignored_channel_or_guild(message) \
               and not await self.bot.cog_disabled_in_guild(self, message.guild)

    @staticmethod
    def convert_novelai_info(img_info: dict):  # used by novelai cog
        return utils.convert_novelai_info(img_info)
    
    async def grab_metadata_dict(self, message: discord.Message) -> dict:  # used by gptmemory from holo-cogs
        assert self.image_cache is not None
        
        if message.id in self.image_cache:
            metadata, image_bytes = self.image_cache[message.id]
        elif not message.attachments:
            return {}
        else:
            metadata: dict[int, ImageDataReader] = {}
            image_bytes: dict[int, bytes] = {}
            tasks = [utils.read_attachment_metadata(i, attachment, metadata, image_bytes)
                    for i, attachment in enumerate(message.attachments)]
            await asyncio.gather(*tasks)
            if metadata and self.image_cache_size > 0:
                self.image_cache[message.id] = (metadata, image_bytes)

        if metadata:
            return utils.get_params_from_metadata(metadata[0])
        else:
            return {}
        

    async def prepare_embed(self, message: discord.Message, metadata: ImageDataReader, i: int, total=1) -> discord.Embed:
        assert isinstance(message.author, discord.Member)
        params = utils.get_params_from_metadata(metadata)
        embed = utils.get_embed(params, message.author)
        embed.description = message.jump_url if self.civitai_emoji else f":arrow_right: {message.jump_url}"
        if total > 1:
            embed.title = f"{embed.title or ''} ({i+1}/{total})"

        if "Comfy" in metadata._tool:
            comfy_data = ComfyMetadataReader.from_info(metadata._info)
            if comfy_data:
                hyperlinks = await self.resolve_arcenciel_resources(comfy_data)
                embed.description += "\n" + "\n".join([f"{self.arcenciel_emoji} {link}" for link in hyperlinks])
            return embed
        if self.use_civitai:
            desc_ext = []
            if MODEL_HASH in params:
                link = await self.grab_civitai_model_link(params[MODEL_HASH])
                if link:
                    if MODEL in params:
                        desc_ext.append(f"{self.civitai_emoji} `CHECKPOINT` [{params[MODEL]}]({link})")
                    else:
                        desc_ext.append(f"{self.civitai_emoji} `CHECKPOINT` [Model]({link})")
                    utils.remove_field(embed, MODEL_HASH)
            utils.remove_field(embed, VAE_HASH) #  vae hashes seem to be bugged in automatic1111 webui
            if params.get(LORA_HASHES):
                hashes = PARAM_REGEX.findall(params[LORA_HASHES].strip('"')+",") # trailing comma for the regex
                log.debug(hashes)
                links = {name: await self.grab_civitai_model_link(short_hash)
                            for name, short_hash in hashes}
                for name, link in links.items():
                    if link:
                        desc_ext.append(f"{self.civitai_emoji} `LORA` [{name}]({link})")
            if desc_ext:
                embed.description += "\n" + "\n".join(desc_ext)
        if self.use_arcenciel:
            desc_ext = []
            if MODEL_HASH in params:
                models = await self.search_arcenciel_resource(params[MODEL_HASH], hash_only=True)
                if models:
                    desc_ext.append(self.build_arcenciel_hyperlink(models[0]))
                    utils.remove_field(embed, MODEL_HASH)
            utils.remove_field(embed, VAE_HASH) #  vae hashes seem to be bugged in automatic1111 webui
            if params.get(LORA_HASHES):
                hashes = PARAM_REGEX.findall(params[LORA_HASHES].strip('"')+",") # trailing comma for the regex
                log.debug(hashes)
                for _, hash in hashes:
                    models = await self.search_arcenciel_resource(hash, hash_only=True)
                    if models:
                        desc_ext.append(self.build_arcenciel_hyperlink(models[0]))
            if desc_ext:
                embed.description += "\n" + "\n".join([f"{self.arcenciel_emoji} {link}" for link in desc_ext])
        return embed


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Scan images for AI metadata in allowed channels"""
        assert self.image_cache is not None
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

        metadata: dict[int, ImageDataReader] = {}
        image_bytes: dict[int, bytes] = {}
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
        assert self.bot.user and self.image_cache is not None
        if ctx.emoji.name != '🔎' or not ctx.member or ctx.member.bot:
            return
        if ctx.channel_id not in self.scan_channels and not self.always_scan_generated_images:
            return

        channel = self.bot.get_channel(ctx.channel_id)
        assert isinstance(channel, discord.abc.Messageable)
        message: discord.Message = await channel.fetch_message(ctx.message_id)
        assert isinstance(message.author, discord.Member)
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
            metadata: dict[int, ImageDataReader] = {}
            image_bytes: dict[int, bytes] = {}
            tasks = [utils.read_attachment_metadata(i, attachment, metadata, image_bytes)
                     for i, attachment in enumerate(attachments)]
            await asyncio.gather(*tasks)
            if self.image_cache_size > 0:
                self.image_cache[message.id] = (metadata, image_bytes)

        if not metadata:
            embed = utils.get_embed({}, message.author)
            embed.description = f"{message.jump_url}\nThis post contains no image generation data."
            embed.set_thumbnail(url=attachments[0].url)
            try:
                await ctx.member.send(embed=embed)
            except discord.Forbidden:
                log.debug(f"User {ctx.member.id} does not accept DMs")
            return
        
        for i, data in sorted(metadata.items()):
            embed = await self.prepare_embed(message, data, i, len(attachments))
            view = ImageView(data.raw, [embed], ephemeral=False)
            if self.attach_images and i in image_bytes:
                img = io.BytesIO(image_bytes[i])
                filename = md5(image_bytes[i]).hexdigest() + ".png"
                file = discord.File(img, filename=filename)
                embed.set_image(url=f"attachment://{filename}")
                try:
                    msg = await ctx.member.send(embed=embed, file=file, view=view)
                    view.message = msg
                except discord.Forbidden:
                    log.debug(f"User {ctx.member.id} does not accept DMs")
            else:
                if len(attachments) > i:
                    embed.set_thumbnail(url=attachments[i].url)
                try:
                    msg = await ctx.member.send(embed=embed, view=view)
                    view.message = msg
                except discord.Forbidden:
                    log.debug(f"User {ctx.member.id} does not accept DMs")


    # context menu set in __init__
    async def scanimage_app(self, interaction: discord.Interaction, message: discord.Message):
        """Get image metadata"""
        assert self.image_cache
        attachments = [a for a in message.attachments if a.filename.lower().endswith(tuple(SUPPORTED_FORMATS))]
        if not attachments:
            await interaction.response.send_message("This post contains no images.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True, thinking=True)

        if message.id in self.image_cache:
            metadata, image_bytes = self.image_cache[message.id]
        else:
            metadata, image_bytes = {}, {}
            tasks = [utils.read_attachment_metadata(i, attachment, metadata, image_bytes)
                     for i, attachment in enumerate(attachments)]
            await asyncio.gather(*tasks)

        if not metadata:
            embed = discord.Embed(title="Image Info", color=message.author.color)
            embed.description = "This message contains no image generation data."
            embed.set_thumbnail(url=attachments[0].url)
            embed.set_footer(text=f'Posted by {message.author}', icon_url=message.author.display_avatar.url)
            await interaction.followup.send(embed=embed)
            return
        
        embeds = []
        metadata_sorted = sorted(metadata.items(), key=lambda m: m[0])
        for i, data in metadata_sorted:
            embed = await self.prepare_embed(message, data, i, len(attachments))
            embed.set_thumbnail(url=attachments[i].url or attachments[i].proxy_url or None)
            embeds.append(embed)
        params = "\n\n".join(data.raw for data in metadata.values() if data)
        view = ImageView(params, embeds, ephemeral=True)

        await interaction.followup.send(embed=embeds[0], view=view)


    async def grab_civitai_model_link(self, short_hash: str) -> str | None:
        if not short_hash:
            return None
        elif short_hash in self.model_cache_civitai:
            model_id = self.model_cache_civitai[short_hash]
        elif short_hash in self.model_not_found_cache_civitai:
            return None
        else:
            url = f"https://civitai.com/api/v1/model-versions/by-hash/{short_hash}"
            try:
                async with self.session.get(url) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
            except aiohttp.ClientError as error:
                if isinstance(error, aiohttp.ClientResponseError) and error.status == 404:
                    log.debug(f"Civitai model {short_hash} not found")
                else:
                    log.warning(f"Trying to grab model {short_hash} from Civitai: {type(error).__name__}: {error}")
                return None

            if not data or "modelId" not in data:
                self.model_not_found_cache_civitai[short_hash] = True
                return None
            model_id = (data['modelId'], data['id'])
            self.model_cache_civitai[short_hash] = model_id
            async with self.config.model_cache_v2() as model_cache:
                model_cache[short_hash] = model_id

        return f"https://civitai.com/models/{model_id[0]}?modelVersionId={model_id[1]}"


    async def search_arcenciel_resource(self, query: str, *, hash_only: bool = False) -> list[dict]:
        if not query.strip():
            return []
        url = "https://arcenciel.io/api/models/search"
        params = {
            "search": query,
            "limit": 10,
        }
        if hash_only:
            params["hashOnly"] = "1"
        try:
            api_key = (await self.bot.get_shared_api_tokens("arcenciel")).get("api_key")
            headers = {"x-api-key": api_key} if api_key else {}
            async with self.session.get(url, params=params, headers = headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except aiohttp.ClientError as error:
            if isinstance(error, aiohttp.ClientResponseError) and error.status == 404:
                log.debug(f"Arcenciel model {query} not found")
            else:
                log.warning(f"Trying to grab model {query} from Arcenciel: {type(error).__name__}: {error}")
            return []
        return data["data"]
    

    async def resolve_arcenciel_resources(self, metadata: ComfyMetadata) -> list[str]:
        hyperlinks: set[str] = set()
        hints = metadata.resource_hint_strings()
        files = [str(os.path.basename(filename.strip(' "'))) for filename in RESOURCE_FILE_REGEX.findall(metadata.raw or "")]
        log.info(f"hints {hints} /// files {files}")
        for hint in hints + files:
            if hint not in self.model_cache_arcenciel and hint in self.model_not_found_cache_arcenciel:
                continue
            if hint in self.model_cache_arcenciel:
                hyperlinks.add(self.model_cache_arcenciel[hint])
                continue
            is_hash = RESOURCE_HASH_REGEX.match(hint) is not None
            resources = await self.search_arcenciel_resource(hint, hash_only=is_hash)
            log.info(f"Resource matches for {hint} /// " + ", ".join([str(model["id"]) for model in resources]))
            if not resources:
                await self.arcenciel_cache_set(hint, None)
                continue
            if is_hash or len(resources) == 1:
                choice = resources[0]
            else:
                choice = None
                for model in resources:
                    version_names = []
                    for version in model["versions"]:
                        vns = [version.get("fileName"), version.get("filePath"), version.get("originalName")]
                        version_names += [vn for vn in vns if vn]
                    if any(hint in name for name in version_names):
                        choice = model
                        break
            if choice:
                link = self.build_arcenciel_hyperlink(choice)
                await self.arcenciel_cache_set(hint, link)
                hyperlinks.add(link)
        return sorted(list(hyperlinks))
    

    async def arcenciel_cache_set(self, hint: str, hyperlink: str | None) -> None:
        if hyperlink is None:
            self.model_not_found_cache_arcenciel[hint] = True
        else:
            self.model_cache_arcenciel[hint] = hyperlink
            async with self.config.model_cache_arcenciel() as cache:
                cache[hint] = hyperlink
            log.info(f"model cache {await self.config.model_cache_arcenciel()}")

    def build_arcenciel_hyperlink(self, model: dict) -> str:
        return f"`{model['type']}` [{model['title']}](https://arcenciel.io/models/{model['id']})"
