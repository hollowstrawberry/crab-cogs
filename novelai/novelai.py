import io
import asyncio
import discord
import logging
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red
from redbot.core.app_commands import Choice
from collections import OrderedDict
from typing import Optional
from novelai_api import NovelAIError
from novelai_api.ImagePreset import ImageModel, ImagePreset, ImageResolution, ImageSampler, UCPreset

from novelai.naiapi import NaiAPI

log = logging.getLogger("red.crab-cogs.novelai")

DEFAULT_NEGATIVE_PROMPT = "{bad}, fewer, extra, missing, worst quality, bad quality, " \
                          "watermark, jpeg artifacts, unfinished, displeasing, chromatic aberration, " \
                          "signature, extra digits, artistic error, username, scan, [abstract]"

SAMPLER_TITLES = OrderedDict({
    "k_euler": "Euler",
    "k_euler_ancestral": "Euler Ancestral",
    "k_dpmpp_2s_ancestral": "DPM++ 2S Ancestral",
    "k_dpmpp_2m": "DPM++ 2M",
    "k_dpmpp_sde": "DPM++ SDE",
    "ddim": "DDIM",
})
RESOLUTION_TITLES = OrderedDict({
    "portrait": "Portrait (832x1216)",
    "landscape": "Landscape (1216x832)",
    "square": "Square (1024x1024)",
})
RESOLUTION_OBJECTS = OrderedDict({
    "portrait": ImageResolution.Normal_Portrait_v3,
    "landscape": ImageResolution.Normal_Landscape_v3,
    "square": ImageResolution.Normal_Square_v3,
})
NOISE_SCHEDULES = [
    "native", "karras", "exponential", "polyexponential",
]

PARAMETER_DESCRIPTIONS = {
    "resolution": "The aspect ratio of your image.",
    "guidance": "The intensity of the prompt.",
    "guidance_rescale": "Adjusts the guidance somehow.",
    "sampler": "The algotithm that guides image generation.",
    "decrisper": "Reduces artifacts caused by high guidance.",
}
PARAMETER_CHOICES = {
    "resolution": [Choice(name=title, value=value) for value, title in RESOLUTION_TITLES.items()],
    "sampler": [Choice(name=title, value=value) for value, title in SAMPLER_TITLES.items()],
    "noise_schedule": [Choice(name=sch, value=sch) for sch in NOISE_SCHEDULES],
}


class NovelAI(commands.Cog):
    """Generate anime images with NovelAI v3."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.api: Optional[NaiAPI] = None
        self.working = False
        self.config = Config.get_conf(self, identifier=66766566169)
        defaults_user = {
            "base_prompt": None,
            "base_negative_prompt": DEFAULT_NEGATIVE_PROMPT,
            "resolution": "portrait",
            "guidance": 5.0,
            "guidance_rescale": 0.0,
            "sampler": "k_euler",
            "noise_schedule": "native",
            "decrisper": False,
        }
        self.config.register_user(**defaults_user)

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
                      noise_schedule: Optional[str],
                      decrisper: Optional[bool],
                      ):
        if not self.api and not await self.try_create_api():
            return await ctx.response.send_message(  # noqa
                "NovelAI username and password not set. The bot owner needs to set them like this:\n"
                "[p]set api novelai username,USERNAME\n"
                "[p]set api novelai password,PASSWORD"
            )
        await ctx.response.defer()  # noqa
        while self.working:
            await asyncio.sleep(0.5)
        self.working = True
        try:
            base_prompt = await self.config.user(ctx.user).base_prompt()
            if base_prompt:
                prompt = f"{base_prompt}, {prompt}" if prompt else base_prompt
            base_neg = await self.config.user(ctx.user).base_negative_prompt()
            if base_neg:
                negative_prompt = f"{base_neg}, {negative_prompt}" if negative_prompt else base_neg
            preset = ImagePreset()
            preset.n_samples = 1
            preset.resolution = RESOLUTION_OBJECTS[resolution or await self.config.user(ctx.user).resolution()]
            preset.uc = negative_prompt or DEFAULT_NEGATIVE_PROMPT
            preset.uc_preset = UCPreset.Preset_None
            preset.sampler = sampler or ImageSampler(await self.config.user(ctx.user).sampler())
            preset.scale = guidance if guidance is not None else await self.config.user(ctx.user).guidance()
            preset.cfg_rescale = guidance_rescale if guidance_rescale is not None else await self.config.user(ctx.user).guidance_rescale()
            preset.decrisper = decrisper if decrisper is not None else await self.config.user(ctx.user).decrisper()
            preset.noise_schedule = noise_schedule or await self.config.user(ctx.user).noise_schedule()
            if "ddim" in str(preset.sampler) or "ancestral" in str(preset.sampler) and preset.noise_schedule == "karras":
                preset.noise_schedule = "native"
            if seed is not None and seed >= 0:
                preset.seed = seed
            preset.uncond_scale = 1.0
            preset.smea = False
            preset.smea_dyn = False

            try:
                async with self.api as wrapper:
                    async for name, img in wrapper.api.high_level.generate_image(prompt, ImageModel.Anime_v3, preset):
                        file = discord.File(io.BytesIO(img), name)
            except NovelAIError as error:
                if error.status == 500:
                    return await ctx.followup.send(":warning: NovelAI encountered an error. Please try again.")
                elif error.status == 401:
                    return await ctx.followup.send(":warning: Failed to authenticate NovelAI account.")
                elif error.status == 402:
                    return await ctx.followup.send(":warning: The subscription and/or credits have run out for this NovelAI account.")
                elif error.status == 400:
                    return await ctx.followup.send(f":warning: Failed to generate image: " + error.message or "A validation error occured.")
                elif error.status == 409:
                    return await ctx.followup.send(f":warning: Failed to generate image: " + error.message or "A conflict error occured.")
                else:
                    return await ctx.followup.send(f":warning: Failed to generate image: {error.status} {error.message}")
        except:
            log.exception("Generating image")
            return await ctx.followup.send(":warning: Failed to generate image! Contact the bot owner for more information.")
        finally:
            self.working = False

        msg = await ctx.followup.send(file=file)
        imagescanner = self.bot.get_cog("ImageScanner")
        if imagescanner:
            if ctx.channel.id in imagescanner.scan_channels:  # noqa
                await msg.add_reaction("🔎")

    @app_commands.command(name="novelaidefaults",
                          description="Views or updates your personal default values for /novelai")
    @app_commands.describe(base_prompt="Gets added before each prompt. \"none\" to delete.",
                           base_negative_prompt="Gets added before each negative prompt. \"none\" to delete, \"default\" to reset.",
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
                              noise_schedule: Optional[str],
                              decrisper: Optional[bool],
                              ):
        if base_prompt is not None:
            base_prompt = base_prompt.strip(" ,")
            if base_prompt.lower() == "none":
                base_prompt = None
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
        if noise_schedule is not None:
            await self.config.user(ctx.user).noise_schedule.set(noise_schedule)
        if decrisper is not None:
            await self.config.user(ctx.user).decrisper.set(decrisper)

        embed = discord.Embed(title="NovelAI default settings", color=0xffffff)
        prompt = await self.config.user(ctx.user).base_prompt()
        neg = await self.config.user(ctx.user).base_negative_prompt()
        embed.add_field(name="Base prompt", value=prompt[:1000] + "..." if len(prompt) > 1000 else prompt, inline=False)
        embed.add_field(name="Base negative prompt", value=neg[:1000] + "..." if len(neg) > 1000 else neg, inline=False)
        embed.add_field(name="Resolution", value=RESOLUTION_TITLES[await self.config.user(ctx.user).resolution()])
        embed.add_field(name="Guidance", value=f"{await self.config.user(ctx.user).guidance():.1f}")
        embed.add_field(name="Guidance Rescale", value=f"{await self.config.user(ctx.user).guidance_rescale():.2f}")
        embed.add_field(name="Sampler", value=SAMPLER_TITLES[await self.config.user(ctx.user).sampler()])
        embed.add_field(name="Noise Schedule", value=await self.config.user(ctx.user).noise_schedule())
        embed.add_field(name="Decrisper", value=f"{await self.config.user(ctx.user).decrisper()}")
        await ctx.response.send_message(embed=embed, ephemeral=True)  # noqa
