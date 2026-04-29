import base64
import logging
import asyncio
import discord
from io import BytesIO
from typing import Coroutine, List, Optional, Tuple, Union
from datetime import datetime, timezone
from discord.ext import tasks
from redbot.core import commands, app_commands
from openai import AsyncOpenAI, APIError, APIStatusError

from gptimage.utils import normalize_image, MODELS
from gptimage.settings import GptImageSettings
from gptimage.views.edit import EditModal
from gptimage.views.image import ImageView
from gptimage.views.generating import GeneratingView

log = logging.getLogger("red.crab-cogs.gptimage")


class GptImage(GptImageSettings):
    """Generate images with OpenAI"""

    async def cog_load(self):
        self.remix_context_menu = app_commands.ContextMenu(name='Remix', type=discord.AppCommandType.message, callback=self.remix_app_command)
        self.bot.tree.add_command(self.remix_context_menu)
        await self.try_create_client()
        self.clear_quota.start()

    async def cog_unload(self):
        self.bot.tree.remove_command(self.remix_context_menu.name, type=self.remix_context_menu.type)
        self.clear_quota.stop()
        if self.client:
            await self.client.close()

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

    @staticmethod
    async def normalize_attachments(attachments: List[discord.Attachment]) -> Tuple[List[bytes], str]:
        fp = [BytesIO() for _ in attachments]
        for i in range(len(attachments)):
            await attachments[i].save(fp[i])
        results = [await asyncio.to_thread(normalize_image, b) for b in fp]
        images = [img[0] for img in results]
        resolution = results[0][1] if results else "1536x1024"
        return images, resolution


    # context menu added in cog_load
    async def remix_app_command(self, interaction: discord.Interaction, message: discord.Message):
        """Edits an image with OpenAI."""
        attachments = [att for att in message.attachments if att.content_type and "image" in att.content_type]
        if not attachments:
            return await interaction.response.send_message("This message doesn't have an image to remix.", ephemeral=True)
        modal = EditModal(self, message)
        await interaction.response.send_modal(modal)


    @app_commands.command(name="imagine", description="Generate images with OpenAI")
    @app_commands.describe(
        prompt="What you want to make.",
        reference1="A possible input image for the AI to use.",
        reference2="A possible input image for the AI to use.",
        reference3="A possible input image for the AI to use.",
    )
    @app_commands.choices(resolution=[
        app_commands.Choice(name="Same as reference", value=""),
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
        image_bytes, first_resolution = await self.normalize_attachments(references)
        resolution = resolution or first_resolution
        await self.imagine(interaction, resolution, prompt, image_bytes)


    async def imagine(self,
                      ctx: Union[discord.Interaction, commands.Context],
                      resolution: str,
                      prompt: str,
                      images: List[bytes],
                      callback: Optional[Coroutine] = None,
                     ):
        user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
        send = ctx.followup.send if isinstance(ctx, discord.Interaction) else ctx.reply
        assert ctx.guild and isinstance(user, discord.Member) and isinstance(ctx.channel, discord.abc.Messageable)

        if not self.client:
            return await send("OpenAI key not set.")
        prompt = prompt.strip()
        if len(prompt) < 3:
            return await send("Prompt too short.", ephemeral=True)
        if not await self.config.guild(ctx.guild).enabled():
            return await send(content=":warning: The generator is not enabled for this server.")
        model = await self.config.model()
        if model not in MODELS:
            return await send("The available image generation models have changed. Please configure the cog to change the model.")
        
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

        embed = discord.Embed(color=await self.bot.get_embed_color(ctx.channel))
        embed.description = f"{await self.config.loading_emoji()} Generating GPT image..."
        embed.set_footer(text=user.display_name, icon_url=user.display_avatar.url)
        view = GeneratingView(prompt, await self.bot.get_embed_color(ctx.channel))
        
        if isinstance(ctx, discord.Interaction):
            progress_message = None
            await send(embed=embed, view=view)
            view.message = await ctx.original_response()
            async def edit_original_response(**kwargs):
                if "view" not in kwargs:
                    kwargs["view"] = None
                if "file" in kwargs:
                    kwargs["attachments"] = [kwargs["file"]]
                    del kwargs["file"]
                if "embed" not in kwargs:
                    kwargs["embed"] = None
                await ctx.edit_original_response(**kwargs)
            send = edit_original_response
        else:
            progress_message = await send(embed=embed, view=view)
            view.message = progress_message

        result = None
        try:
            self.generating[user.id] = True
            args = {
                "n": 1,
                "model": model,
                "prompt": prompt,
                "quality": await self.config.quality(),
                "size": resolution,
            }
            if images:
                formatted_images = [(f"image{i+1}.webp", img, "image/webp") for i, img in enumerate(images)]
                result = await self.client.images.edit(image=formatted_images, **args)  # type: ignore
            else:
                result = await self.client.images.generate(moderation="low", **args)  # type: ignore

        except APIStatusError as e:
            message = e.response.json().get('error', {}).get('message')
            if "safety" in message:
                return await send(content=f":warning: Request rejected by the safety system.")
            else:
                return await send(content=f":warning: Failed to generate image. {message}")
        except APIError as e:
            if "safety" in e.message:
                return await send(content=f":warning: Request rejected by the safety system.")
            else:
                return await send(content=f":warning: Failed to generate image. {e.message}")
        except Exception:
            log.exception(msg="Trying to generate image with OpenAI", stack_info=True)
        finally:
            self.generating[user.id] = False
            if progress_message:
                asyncio.create_task(progress_message.delete())
            if callback:
                asyncio.create_task(callback)

        if not result or not result.data or not result.data[0].b64_json:
            return await send(content=":warning: Sorry, there was a problem trying to generate your image.")

        self.gen_count[user.id] += 1
        image_data = BytesIO(base64.b64decode(result.data[0].b64_json))
        fid = ctx.id if isinstance(ctx, discord.Interaction) else ctx.message.id
        filename = f"gptimage_{fid}.png"
        file = discord.File(fp=image_data, filename=filename)
        if isinstance(ctx, commands.Context) or ctx.type == discord.InteractionType.component:
            content = f"-# Requested by {user.mention}"
        else:
            content = ""
        view = ImageView(self, prompt, resolution, images)
        message = await send(content=content, view=view, file=file, allowed_mentions=discord.AllowedMentions.none())
        view.message = message
