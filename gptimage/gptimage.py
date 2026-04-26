import asyncio
import io
import base64
import discord
import logging
from typing import List, Optional, Union
from datetime import datetime, timedelta, timezone
from discord.ext import tasks
from redbot.core import commands, app_commands, checks

from openai import AsyncOpenAI, APIError, APIStatusError, NotGiven
from gptimage.settings import GptImageSettings
from gptimage.views.image import ImageView

log = logging.getLogger("red.crab-cogs.gptimage")


class GptImage(GptImageSettings):
    """Generate images with OpenAI"""

    async def cog_load(self):
        await self.try_create_client()
        self.clear_quota.start()
        self.loading_emoji = await self.config.loading_emoji()

    async def cog_unload(self):
        if self.client:
            await self.client.close()
        self.clear_quota.stop()

    @tasks.loop(hours=1)
    async def clear_quota(self):
        self.gen_count.clear()
        self.last_quota_refresh = datetime.now(timezone.utc)
        log.info("Refreshed hourly quota")

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
            await references[i].save(fp[i])
        images = [b.getvalue() for b in fp]

        resolution = resolution or "1536x1024"
        await self.imagine(interaction, resolution, prompt, images)


    async def imagine(self,
                      ctx: Union[discord.Interaction, commands.Context],
                      resolution: str,
                      prompt: str,
                      images: List[bytes]
                     ):
        user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
        send = ctx.followup.send if isinstance(ctx, discord.Interaction) else ctx.reply
        assert ctx.guild and isinstance(user, discord.Member) and isinstance(ctx.channel, discord.abc.Messageable)
        
        if not self.client:
            return await send("OpenAI key not set.", ephemeral=True)
        prompt = prompt.strip()
        if len(prompt) < 3:
            return await send("Prompt too short.", ephemeral=True)
        
        vip_role = await self.config.guild(ctx.guild).vip_role()
        is_vip = user.id in await self.config.vip() or any(role.id == vip_role for role in user.roles)
        quota = await self.config.quota()
        elapsed_last_refresh = (datetime.now(timezone.utc) - self.last_quota_refresh).total_seconds()
        if not is_vip:
            embed = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            embed.set_footer(text=user.display_name, icon_url=user.display_avatar.url)
            if self.generating.get(user.id, False):
                embed.description = "🕒 You must wait for your current image to finish generating before you can request a new one."
                return await send(embed=embed, ephemeral=True)
            if self.gen_count[user.id] >= quota:
                if quota == 0:
                    embed.description = ":warning: You are not authorized to generate images at this time."
                else:
                    embed.description = "🕒 You have met your hourly quota."
                    embed.add_field(name="Time remaining", value=f"{int(60 - (elapsed_last_refresh // 60))} minutes.")
                return await send(embed=embed, ephemeral=True)

        if isinstance(ctx, discord.Interaction):
            progress_message = None
        else:
            embed = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
            embed.description = f"{await self.config.loading_emoji()} Generating image..."
            embed.set_footer(text=user.display_name, icon_url=user.display_avatar.url)
            progress_message = await send(embed=embed)

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
                formatted_images = [(f"image{i+1}.webp", img, "image/webp") for i, img in enumerate(images)]
                result = await self.client.images.edit(image=formatted_images, **args)  # type: ignore
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
            if progress_message:
                await asyncio.create_task(progress_message.delete())

        if not result or not result.data or not result.data[0].b64_json:
            return await send(content=":warning: Sorry, there was a problem trying to generate your image.")

        self.gen_count[user.id] += 1
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
