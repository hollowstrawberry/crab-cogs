import re
import io
import base64
import discord
import logging
from typing import List, Literal, Optional, Dict, Union
from datetime import datetime, timedelta
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red

from openai import AsyncOpenAI, APIError, APIStatusError, NotGiven
from gptimage.base import GptImageBase
from gptimage.views.image import ImageView

log = logging.getLogger("red.crab-cogs.gptimage")

SIMPLE_PROMPT = "I NEED to test how the tool works with extremely simple prompts. DO NOT add any detail, just use it AS-IS: "

MODELS = { # model name -> quality name list
    "dall-e-2": [],
    "dall-e-3": ["standard", "hd"],
    "gpt-image-1": ["low", "medium", "high"],
    "gpt-image-2": ["low", "medium", "high"],
}


class GptImage(GptImageBase):
    """Generate images with OpenAI"""

    async def cog_load(self):
        await self.try_create_client()
        self.loading_emoji = await self.config.loading_emoji()

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, _):
        if service_name == "openai":
            await self.try_create_client()

    async def try_create_client(self):
        api = await self.bot.get_shared_api_tokens("openai")
        api_key = api.get("api_key")
        if api_key:
            self.client = AsyncOpenAI(api_key=api_key)


    @app_commands.command(name="imagine", description="Generate AI images with OpenAI")
    @app_commands.describe(
        prompt="What you want to make.",
        reference1="A possible input image for the AI to use.",
        reference2="A possible input image for the AI to use.",
        reference3="A possible input image for the AI to use.",
    )
    @app_commands.choices(resolution=[
        app_commands.Choice(name="Square", value="1024x1024"),
        app_commands.Choice(name="Portrait", value="1024x1536"),
        app_commands.Choice(name="Landscape", value="1536x1024"),
    ])
    @app_commands.guild_only()
    async def imagine_app(self,
                          interaction: discord.Interaction,
                          prompt: str,
                          resolution: Optional[str],
                          reference1: Optional[discord.Attachment],
                          reference2: Optional[discord.Attachment],
                          reference3: Optional[discord.Attachment]):
        references = [ref for ref in [reference1, reference2, reference3] if ref is not None]
        for ref in references:
            if not ref.content_type or "image" not in ref.content_type:
                return await interaction.response.send_message("One of the references you uploaded is not an image.", ephemeral=True)
        
        await interaction.response.defer(thinking=True)

        fp = [io.BytesIO() for _ in references]
        for i in range(len(references)):
            await references[i].save(fp[i], seek_begin=True)
        images = [b.read() for b in fp]

        resolution = resolution or "1536x1024"
        await self.imagine(interaction, resolution, prompt, images)

    async def imagine(self,
                      ctx: Union[discord.Interaction, commands.Context],
                      resolution: str,
                      prompt: str,
                      images: List[bytes]):
        user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
        send = ctx.followup.send if isinstance(ctx, discord.Interaction) else ctx.reply
        assert isinstance(user, discord.Member) and isinstance(ctx.channel, discord.abc.Messageable)
        if not self.client:
            return await send("OpenAI key not set.", ephemeral=True)
        prompt = prompt.strip()
        if len(prompt) < 3:
            return await send("Prompt too short.", ephemeral=True)
        if user.id not in await self.config.vip():
            cooldown = await self.config.cooldown()
            if self.generating.get(user.id, False):
                content = "Your current image must finish generating before you can request another one."
                return await send(content, ephemeral=True)
            if user.id in self.user_last_img and \
                    (datetime.now() - self.user_last_img[user.id]).total_seconds() < cooldown:
                eta = self.user_last_img[user.id] + timedelta(seconds=cooldown)
                content = f"You may use this command again {discord.utils.format_dt(eta, 'R')}."
                return await send(content, ephemeral=True)

        result = None
        try:
            self.generating[user.id] = True
            model = await self.config.model()
            args = {
                "n": 1,
                "model": model,
                "prompt": prompt,
                "quality": NotGiven() if model == "dall-e-2" else await self.config.quality(),
                "response_format": NotGiven() if "gpt-image" in model else "b64_json",
                "size": resolution,
            }
            if images:
                result = await self.client.images.edit(images, **args)  # type: ignore
            else:
                result = await self.client.images.generate(moderation="low", **args)  # type: ignore
        except APIStatusError as e:
            return await send(content=f":warning: Failed to generate image: {e.response.json()['error']['message']}")
        except APIError as e:
            return await send(content=f":warning: Failed to generate image: {e.message}")
        except Exception:  # noqa, reason: user-facing error
            log.exception(msg="Trying to generate image with OpenAI", stack_info=True)
        finally:
            self.generating[user.id] = False

        if not result or not result.data or not result.data[0].b64_json:
            return await send(content=":warning: Sorry, there was a problem trying to generate your image.")

        self.user_last_img[user.id] = datetime.now()
        
        image_data = io.BytesIO(base64.b64decode(result.data[0].b64_json))
        fid = ctx.id if isinstance(ctx, discord.Interaction) else ctx.message.id
        filename = f"gptimage_{fid}.png"
        file = discord.File(fp=image_data, filename=filename)
        if isinstance(ctx, commands.Context) or ctx.type == discord.InteractionType.component:
            content = f"Reroll requested by {user.mention}"
        else:
            content = ""
        view = ImageView(self, prompt, resolution, images)
        message = await send(content=content, view=view, file=file, allowed_mentions=discord.AllowedMentions.none())
        view.message = message

    @commands.group(name="gptimage", aliases=["gptimageset"]) # type: ignore
    @commands.is_owner()
    async def gptimage(self, _):
        """Configure /imagine bot-wide."""
        pass

    @gptimage.command()
    async def model(self, ctx: commands.Context, model: Optional[str]):
        """The OpenAI image generation model to be used. Careful of costs, see https://openai.com/api/pricing/"""
        if model is None:
            model = await self.config.model()
        else:
            model = model.lower().strip()
            if model not in MODELS.keys():
                await ctx.reply("Model must be one of: " + ",".join([f'`{m}`' for m in MODELS.keys()]))
                return
            await self.config.model.set(model)
            quality = await self.config.quality()
            if quality not in MODELS[model]:
                await self.config.quality.set(MODELS[model][0] if len(MODELS[model]) else None)
        await ctx.reply(f"The /imagine command will use the {model} model.")

    @gptimage.command()
    async def quality(self, ctx: commands.Context, quality: Optional[str]):
        """The quality to be used with the image generation model. Careful of costs, see https://openai.com/api/pricing/"""
        if quality is None:
            quality = await self.config.quality()
        else:
            model = await self.config.model()
            quality = quality.lower().strip()
            qualities = MODELS.get(model, [])
            if quality not in qualities:
                if not qualities:
                    await ctx.reply(f"The {model} model does not support qualities")
                else:
                    await ctx.reply("Quality must be one of: " + ",".join([f'`{m}`' for m in (qualities)]))
                return
            await self.config.quality.set(quality)
        await ctx.reply(f"The /imagine command will use {quality} quality.")

    @gptimage.command()
    async def cooldown(self, ctx: commands.Context, seconds: Optional[int]):
        """Time in seconds between when a user's generation ends and when they can start a new one."""
        if seconds is None:
            seconds = await self.config.cooldown()
        else:
            await self.config.cooldown.set(max(0, seconds))
        await ctx.reply(f"Users will need to wait {max(0, seconds or 0)} seconds between generations.")

    @gptimage.group(name="vip", invoke_without_command=True)
    async def vip(self, ctx: commands.Context):
        """Manage the VIP list which skips the cooldown."""
        await ctx.send_help()

    @vip.command(name="add")
    async def vip_add(self, ctx: commands.Context, *, users: str):
        """Add a list of users to the VIP list."""
        user_ids = [int(uid) for uid in re.findall(r"(\d+)", users)]
        if not user_ids:
            return await ctx.reply("Please enter one or more valid users.")
        vip = set(await self.config.vip())
        vip.update(uid for uid in user_ids)
        await self.config.vip.set(list(vip))
        await ctx.tick(message="VIP user(s) added")

    @vip.command(name="remove")
    async def vip_remove(self, ctx: commands.Context, *, users: str):
        """Remove a list of users from the VIP list."""
        user_ids = [int(uid) for uid in re.findall(r"(\d+)", users)]
        if not user_ids:
            return await ctx.reply("Please enter one or more valid users.")
        vip = set(await self.config.vip())
        vip.difference_update(uid for uid in user_ids)
        await self.config.vip.set(list(vip))
        await ctx.tick(message="VIP user(s) removed")

    @vip.command(name="list")
    async def vip_list(self, ctx: commands.Context):
        """Show all users in the VIP list."""
        await ctx.reply('\n'.join([f'<@{uid}>' for uid in await self.config.vip()]) or "*None*",
                        allowed_mentions=discord.AllowedMentions.none())
        
    @staticmethod
    def is_nsfw(channel: discord.abc.Messageable):
        if isinstance(channel, discord.TextChannel):
            return channel.nsfw
        elif isinstance(channel, discord.Thread) and channel.parent:
            return channel.parent.nsfw
        else:
            return False
