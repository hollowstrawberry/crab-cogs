import io
import json
import asyncio
import discord
import logging
import calendar
from PIL import Image
from datetime import datetime, timedelta, timezone
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red
from novelai_api import NovelAIError
from novelai_api.ImagePreset import ImageModel, ImagePreset, ImageSampler, UCPreset
from typing import Optional, Coroutine

from novelai.naiapi import NaiAPI
from novelai.imageview import ImageView
from novelai.constants import *

log = logging.getLogger("red.crab-cogs.novelai")


class NovelAI(commands.Cog):
    """Generate anime images with NovelAI v3."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.api: Optional[NaiAPI] = None
        self.queue: list[Coroutine] = []
        self.queue_task: Optional[asyncio.Task] = None
        self.last_dm: dict[int, datetime] = {}
        self.config = Config.get_conf(self, identifier=66766566169)
        defaults_user = {
            "base_prompt": DEFAULT_PROMPT,
            "base_negative_prompt": DEFAULT_NEGATIVE_PROMPT,
            "resolution": "portrait",
            "guidance": 5.0,
            "guidance_rescale": 0.0,
            "sampler": "k_euler",
            "sampler_version": "Regular",
            "noise_schedule": "native",
            "decrisper": False,
        }
        defaults_global = {
            "nsfw_filter": True,
        }
        self.config.register_user(**defaults_user)
        self.config.register_global(**defaults_global)

    async def cog_load(self):
        await self.try_create_api()

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    async def try_create_api(self):
        api = await self.bot.get_shared_api_tokens("novelai")
        username, password = api.get("username"), api.get("password")
        if username and password:
            self.api = NaiAPI(username, password)
            return True
        else:
            return False

    async def consume_queue(self):
        while self.queue:
            try:
                await self.queue.pop(0)
            except:
                log.exception("NovelAI task queue")

    @app_commands.command(name="novelai",
                          description="Generate anime images with NovelAI v3.")
    @app_commands.describe(prompt="What you want to generate.",
                           negative_prompt="Undesired terms for your generation.",
                           seed="Random number that determines image generation.",
                           **PARAMETER_DESCRIPTIONS)
    @app_commands.choices(**PARAMETER_CHOICES)
    async def novelai(self,
                      ctx: discord.Interaction,
                      prompt: str,
                      negative_prompt: Optional[str],
                      seed: Optional[int],
                      resolution: Optional[str],
                      guidance: Optional[app_commands.Range[float, 0.0, 10.0]],
                      guidance_rescale: Optional[app_commands.Range[float, 0.0, 1.0]],
                      sampler: Optional[ImageSampler],
                      sampler_version: Optional[str],
                      noise_schedule: Optional[str],
                      decrisper: Optional[bool],
                      ):
        if not self.api and not await self.try_create_api():
            return await ctx.response.send_message(KEY_NOT_SET_MESSAGE)  # noqa
        if not ctx.guild and ctx.user.id in self.last_dm \
                and (datetime.now(timezone.utc) - self.last_dm[ctx.user.id]).seconds < DM_COOLDOWN:
            eta = self.last_dm[ctx.user.id] + timedelta(seconds=DM_COOLDOWN)
            return await ctx.response.send_message(  # noqa
                f"You may use this command again in DMs <t:{calendar.timegm(eta.utctimetuple())}:R>", ephemeral=True)
        await ctx.response.defer()  # noqa

        base_prompt = await self.config.user(ctx.user).base_prompt()
        if base_prompt:
            prompt = f"{prompt.strip(' ,')}, {base_prompt}" if prompt else base_prompt
        base_neg = await self.config.user(ctx.user).base_negative_prompt()
        if base_neg:
            negative_prompt = f"{negative_prompt.strip(' ,')}, {base_neg}" if negative_prompt else base_neg
        if ctx.guild and not ctx.channel.nsfw and await self.config.nsfw_filter():
            blacklisted = [term.strip() for term in NSFW_TERMS.split(",")]
            if any(term in prompt for term in blacklisted) or "safe" in negative_prompt:
                return await ctx.followup.send(":warning: You may not generate NSFW images in non-NSFW channels.")
            prompt = "{safe}, " + prompt
            negative_prompt = "{nsfw}, " + negative_prompt
        preset = ImagePreset()
        preset.n_samples = 1
        preset.resolution = RESOLUTION_OBJECTS[resolution or await self.config.user(ctx.user).resolution()]
        preset.uc = negative_prompt or DEFAULT_NEGATIVE_PROMPT
        preset.uc_preset = UCPreset.Preset_None
        preset.quality_toggle = False
        preset.sampler = sampler or ImageSampler(await self.config.user(ctx.user).sampler())
        preset.scale = guidance if guidance is not None else await self.config.user(ctx.user).guidance()
        preset.cfg_rescale = guidance_rescale if guidance_rescale is not None else await self.config.user(ctx.user).guidance_rescale()
        preset.decrisper = decrisper if decrisper is not None else await self.config.user(ctx.user).decrisper()
        preset.noise_schedule = noise_schedule or await self.config.user(ctx.user).noise_schedule()
        if "ddim" in str(preset.sampler) or "ancestral" in str(preset.sampler) and preset.noise_schedule == "karras":
            preset.noise_schedule = "native"
        if seed is not None and seed > 0:
            preset.seed = seed
        preset.uncond_scale = 1.0
        sampler_version = sampler_version or await self.config.user(ctx.user).sampler_version()
        preset.smea = "SMEA" in sampler_version
        preset.smea_dyn = "DYN" in sampler_version

        self.queue.append(self.fulfill_novelai_request(ctx, prompt, preset))
        if not self.queue_task or self.queue_task.done():
            self.queue_task = asyncio.create_task(self.consume_queue())

    async def fulfill_novelai_request(self,
                                      ctx: discord.Interaction,
                                      prompt: str, preset: ImagePreset,
                                      requester: Optional[int] = None,
                                      callback: Optional[Coroutine] = None):
        if not ctx.guild:
            self.last_dm[ctx.user.id] = ctx.created_at
        try:
            async with self.api as wrapper:
                async for name, img in wrapper.api.high_level.generate_image(prompt, ImageModel.Anime_v3, preset):
                    fp = io.BytesIO(img)
                    file = discord.File(fp, name)
        except Exception as error:
            if isinstance(error, NovelAIError):
                if error.status == 500:
                    return await ctx.followup.send(":warning: NovelAI encountered an error. Please try again.")
                elif error.status == 401:
                    return await ctx.followup.send(":warning: Failed to authenticate NovelAI account.")
                elif error.status == 402:
                    return await ctx.followup.send(":warning: The subscription and/or credits have run out for this NovelAI account.")
                elif error.status == 400:
                    return await ctx.followup.send(":warning: Failed to generate image: " + (error.message or "A validation error occured."))
                elif error.status == 409:
                    return await ctx.followup.send(":warning: Failed to generate image: " + (error.message or "A conflict error occured."))
                else:
                    return await ctx.followup.send(f":warning: Failed to generate image: {error.status} {error.message}")
            else:
                log.exception("Generating image")
                return await ctx.followup.send(":warning: Failed to generate image! Contact the bot owner for more information.")

        if preset.seed > 0:
            seed = preset.seed
        else:
            try:
                image = Image.open(fp)
                seed = json.loads(image.info["Comment"])["seed"]
            except:
                seed = 0
            fp.seek(0)
        view = ImageView(self, prompt, preset, seed)
        content = f"Reroll requested by <@{requester}>" if requester and ctx.guild else None
        msg = await ctx.followup.send(content, file=file, view=view, allowed_mentions=discord.AllowedMentions.none())
        imagescanner = self.bot.get_cog("ImageScanner")
        if imagescanner:
            if ctx.channel.id in imagescanner.scan_channels:  # noqa
                await msg.add_reaction("🔎")
        asyncio.create_task(self.delete_button_after(msg, view))
        if callback:
            await callback

    @staticmethod
    async def delete_button_after(msg: discord.Message, view: ImageView):
        await asyncio.sleep(VIEW_TIMEOUT)
        if not view.deleted:
            await msg.edit(view=None)

    @app_commands.command(name="novelaidefaults",
                          description="Views or updates your personal default values for /novelai")
    @app_commands.describe(base_prompt="Gets added after each prompt. \"none\" to delete, \"default\" to reset.",
                           base_negative_prompt="Gets added after each negative prompt. \"none\" to delete, \"default\" to reset.",
                           **PARAMETER_DESCRIPTIONS)
    @app_commands.choices(**PARAMETER_CHOICES)
    async def novelaidefaults(self,
                              ctx: discord.Interaction,
                              base_prompt: Optional[str],
                              base_negative_prompt: Optional[str],
                              resolution: Optional[str],
                              guidance: Optional[app_commands.Range[float, 0.0, 10.0]],
                              guidance_rescale: Optional[app_commands.Range[float, 0.0, 1.0]],
                              sampler: Optional[str],
                              sampler_version: Optional[str],
                              noise_schedule: Optional[str],
                              decrisper: Optional[bool],
                              ):
        if base_prompt is not None:
            base_prompt = base_prompt.strip(" ,")
            if base_prompt.lower() == "none":
                base_prompt = None
            elif base_prompt.lower() == "default":
                base_prompt = DEFAULT_PROMPT
            await self.config.user(ctx.user).base_prompt.set(base_prompt)
        if base_negative_prompt is not None:
            base_negative_prompt = base_negative_prompt.strip(" ,")
            if base_negative_prompt.lower() == "none":
                base_negative_prompt = None
            elif base_negative_prompt.lower() == "default":
                base_negative_prompt = DEFAULT_NEGATIVE_PROMPT
            await self.config.user(ctx.user).base_negative_prompt.set(base_negative_prompt)
        if resolution is not None:
            await self.config.user(ctx.user).resolution.set(resolution)
        if guidance is not None:
            await self.config.user(ctx.user).guidance.set(guidance)
        if guidance_rescale is not None:
            await self.config.user(ctx.user).guidance_rescale.set(guidance_rescale)
        if sampler is not None:
            await self.config.user(ctx.user).sampler.set(sampler)
        if sampler_version is not None:
            await self.config.user(ctx.user).sampler_version.set(sampler_version)
        if noise_schedule is not None:
            await self.config.user(ctx.user).noise_schedule.set(noise_schedule)
        if decrisper is not None:
            await self.config.user(ctx.user).decrisper.set(decrisper)

        embed = discord.Embed(title="NovelAI default settings", color=0xffffff)
        prompt = str(await self.config.user(ctx.user).base_prompt())
        neg = str(await self.config.user(ctx.user).base_negative_prompt())
        embed.add_field(name="Base prompt", value=prompt[:1000] + "..." if len(prompt) > 1000 else prompt, inline=False)
        embed.add_field(name="Base negative prompt", value=neg[:1000] + "..." if len(neg) > 1000 else neg, inline=False)
        embed.add_field(name="Resolution", value=RESOLUTION_TITLES[await self.config.user(ctx.user).resolution()])
        embed.add_field(name="Guidance", value=f"{await self.config.user(ctx.user).guidance():.1f}")
        embed.add_field(name="Guidance Rescale", value=f"{await self.config.user(ctx.user).guidance_rescale():.2f}")
        embed.add_field(name="Sampler", value=SAMPLER_TITLES[await self.config.user(ctx.user).sampler()])
        embed.add_field(name="Sampler Version", value=await self.config.user(ctx.user).sampler_version())
        embed.add_field(name="Noise Schedule", value=await self.config.user(ctx.user).noise_schedule())
        embed.add_field(name="Decrisper", value=f"{await self.config.user(ctx.user).decrisper()}")
        await ctx.response.send_message(embed=embed, ephemeral=True)  # noqa

    @commands.group()
    @commands.is_owner()
    async def novelaiset(self, _):
        """Configure /novelai bot-wide."""
        pass

    @novelaiset.command()
    async def nsfw_filter(self, ctx: commands.Context):
        """Toggles the NSFW filter for /novelai"""
        new = not await self.config.nsfw_filter()
        await self.config.nsfw_filter.set(new)
        if new:
            await ctx.reply("NSFW filter enabled in non-nsfw channels. Note that this is not perfect.")
        else:
            await ctx.reply("NSFW filter disabled. Users may easily generate NSFW content with /novelai")
