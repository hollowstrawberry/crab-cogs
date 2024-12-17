import re
import io
import base64
import discord
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red

from openai import AsyncOpenAI, APIError, APIStatusError
from dalle.imageview import ImageView

log = logging.getLogger("red.crab-cogs.dalle")

SIMPLE_PROMPT = "I NEED to test how the tool works with extremely simple prompts. DO NOT add any detail, just use it AS-IS: "


class DallE(commands.Cog):
    """Generate images with OpenAI's Dall-E 3."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.client: Optional[AsyncOpenAI] = None
        self.generating: Dict[int, bool] = {}
        self.user_last_img: Dict[int, datetime] = {}
        self.loading_emoji = ""
        self.config = Config.get_conf(self, identifier=64616665)
        defaults_global = {
            "vip": [],
            "cooldown": 0,
        }
        self.config.register_global(**defaults_global)

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

    @app_commands.command(name="imagine",
                          description="Generate AI images with Dall-E 3.")
    @app_commands.describe(prompt="Your prompt will get adjusted by OpenAI.",
                           prompt_style="Dall-E will always edit your prompt before generating.")
    @app_commands.choices(prompt_style=[app_commands.Choice(name="Add detail", value="detail"),
                                        app_commands.Choice(name="Don't add detail", value="nodetail")])
    @app_commands.guild_only()
    async def imagine_app(self, ctx: discord.Interaction, prompt: str, prompt_style: str = "detail"):
        await self.imagine(ctx, prompt, prompt_style == "detail")

    async def imagine(self, ctx: discord.Interaction, prompt: str, add_detail: bool):
        if not self.client:
            return await ctx.response.send_message("OpenAI key not set.", ephemeral=True)
        prompt = prompt.strip()
        if len(prompt) < 2:
            return await ctx.response.send_message("Prompt too short.", ephemeral=True)
        if ctx.user.id not in await self.config.vip():
            cooldown = await self.config.cooldown()
            if self.generating.get(ctx.user.id, False):
                content = "Your current image must finish generating before you can request another one."
                return await ctx.response.send_message(content, ephemeral=True)
            if ctx.user.id in self.user_last_img and \
                    (datetime.now() - self.user_last_img[ctx.user.id]).total_seconds() < cooldown:
                eta = self.user_last_img[ctx.user.id] + timedelta(seconds=cooldown)
                content = f"You may use this command again {discord.utils.format_dt(eta, 'R')}."
                return await ctx.response.send_message(content, ephemeral=True)

        await ctx.response.defer(thinking=True)
        result = None
        try:
            self.generating[ctx.user.id] = True
            result = await self.client.images.generate(
                prompt=SIMPLE_PROMPT+prompt if not add_detail else prompt,
                model="dall-e-3",
                size="1024x1024",
                quality="standard",
                n=1,
                response_format="b64_json"
            )
        except APIStatusError as e:
            return await ctx.followup.send(content=f":warning: Failed to generate image: {e.response.json()['error']['message']}")
        except APIError as e:
            return await ctx.followup.send(content=f":warning: Failed to generate image: {e.message}")
        except Exception:  # noqa, reason: user-facing error
            log.exception(msg="Trying to generate image with Dall-E", stack_info=True)
        finally:
            self.generating[ctx.user.id] = False

        if not result or not result.data or not result.data[0].b64_json:
            return await ctx.followup.send(content=":warning: Sorry, there was a problem trying to generate your image.")

        self.user_last_img[ctx.user.id] = datetime.now()
        
        image_data = io.BytesIO(base64.b64decode(result.data[0].b64_json))
        timestamp = f"{datetime.utcnow().timestamp():.6f}"
        filename = f"dalle3_{timestamp.replace('.', '_')}.png"
        file = discord.File(fp=image_data, filename=filename)
        content = f"Reroll requested by {ctx.user.mention}" if ctx.type == discord.InteractionType.component else ""
        message = await ctx.original_response()
        view = ImageView(self, message, prompt, result.data[0].revised_prompt, add_detail)
        await ctx.followup.send(content=content, view=view, file=file, allowed_mentions=discord.AllowedMentions.none())

    @commands.group()
    @commands.is_owner()
    async def dalleset(self, _):
        """Configure /imagine bot-wide."""
        pass

    @dalleset.command()
    async def cooldown(self, ctx: commands.Context, seconds: Optional[int]):
        """Time in seconds between when a user's generation ends and when they can start a new one."""
        if seconds is None:
            seconds = await self.config.cooldown()
        else:
            await self.config.cooldown.set(max(0, seconds))
        await ctx.reply(f"Users will need to wait {max(0, seconds)} seconds between generations.")

    @dalleset.group(name="vip", invoke_without_command=True)
    async def vip(self, ctx: commands.Context):
        """Manage the VIP list which skips the cooldown."""
        await ctx.send_help()

    @vip.command(name="add")
    async def vip_add(self, ctx: commands.Context, *, users: str):
        """Add a list of users to the VIP list."""
        user_ids = [int(uid) for uid in re.findall(r"([0-9]+)", users)]
        if not user_ids:
            return await ctx.reply("Please enter one or more valid users.")
        vip = set(await self.config.vip())
        vip.update(uid for uid in user_ids)
        await self.config.vip.set(list(vip))
        await ctx.tick()

    @vip.command(name="remove")
    async def vip_remove(self, ctx: commands.Context, *, users: str):
        """Remove a list of users from the VIP list."""
        user_ids = [int(uid) for uid in re.findall(r"([0-9]+)", users)]
        if not user_ids:
            return await ctx.reply("Please enter one or more valid users.")
        vip = set(await self.config.vip())
        vip.difference_update(uid for uid in user_ids)
        await self.config.vip.set(list(vip))
        await ctx.tick()

    @vip.command(name="list")
    async def vip_list(self, ctx: commands.Context):
        """Show all users in the VIP list."""
        await ctx.reply('\n'.join([f'<@{uid}>' for uid in await self.config.vip()]) or "*None*",
                        allowed_mentions=discord.AllowedMentions.none())
