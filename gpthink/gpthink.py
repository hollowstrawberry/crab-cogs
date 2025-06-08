import re
import discord
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red

from openai import AsyncOpenAI, APIError, APIStatusError

log = logging.getLogger("red.crab-cogs.gpthink")

MODELS = ["o3-mini", "o4-mini", "o3"]
EMPTY = "ᅠ"
CODE_REGEX = re.compile(r"^```(\w*)\s*$")
MAX_MESSAGE_LENGTH = 1950


async def chunk_and_send(inter: discord.Interaction, full_text: str, embed: discord.Embed):
    base_lines = full_text.splitlines(keepends=True)
    lines = []
    for base_line in base_lines:
        while len(base_line) > MAX_MESSAGE_LENGTH:
            lines.append(base_line)
            base_line = base_line[:MAX_MESSAGE_LENGTH]
        else:
            lines.append(base_line)

    chunks = []
    current = ""
    in_code = False
    code_lang = ""

    def flush_chunk():
        nonlocal current, in_code, code_lang
        if in_code:
            current += "```\n"  # close open fence
        if current:
            chunks.append(current)
        # start new
        current = ""
        if in_code:
            # re-open fence with language
            current += f"```{code_lang}\n"
    
    for line in lines:
        if m := CODE_REGEX.match(line):
            if m.group(1):
                in_code = True
                code_lang = m.group(1)
            else:
                in_code = not in_code
        if len(current) + len(line) > MAX_MESSAGE_LENGTH:
            flush_chunk()
        current += line

    flush_chunk()

    for idx, chunk in enumerate(chunks):
        is_last = (idx == len(chunks) - 1)
        if is_last:
            chunk += f"\n{EMPTY}"
        await inter.followup.send(
            content=chunk,
            embed=embed if is_last else discord.utils.MISSING,
            allowed_mentions=discord.AllowedMentions.none()
        )


class GptThinkModal(discord.ui.Modal):
    prompt = discord.ui.TextInput(label="Prompt", custom_id="prompt", style=discord.TextStyle.long)

    def __init__(self, cog: "GptThink", effort: str):
        super().__init__(title="GPT Think")
        self.cog = cog
        self.effort = effort

    async def on_submit(self, inter: discord.Interaction):
        assert self.cog.client and isinstance(inter.channel, discord.TextChannel)
        await inter.response.defer(thinking=True)
        result = None
        try:
            self.cog.generating[inter.user.id] = True
            model = await self.cog.config.model()
            prompt = self.prompt.value
            result = await self.cog.client.responses.create(
                model=model,
                reasoning={
                    "effort": self.effort,
                    "summary": "auto"
                }, # type: ignore
                input=[
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ]
            )
        except APIStatusError as e:
            try:
                data = e.response.json()
            except ValueError:
                data = {}
            msg = data.get("error",{}).get("message") or str(e)
            return await inter.followup.send(f":warning: Failed to process prompt: {msg}", ephemeral=True)
        except APIError as e:
            return await inter.followup.send(content=f":warning: Failed to process prompt: {e.message}")
        except Exception:  # noqa, reason: user-facing error
            log.exception(msg="Trying to process prompt with OpenAI", stack_info=True)
        finally:
            self.cog.generating[inter.user.id] = False

        if not result or not result.output_text:
            return await inter.followup.send(content=":warning: Sorry, there was a problem processing your prompt.")

        self.cog.user_last_prompt[inter.user.id] = datetime.now()
        
        embed = discord.Embed(
            title="Reasoning",
            color=await self.cog.bot.get_embed_color(inter.channel),
        )

        summary = [o.summary[0].text for o in result.output if o.type == "reasoning" and o.summary]
        if summary:
            embed.description = summary[0][:3950]
        if result.usage and result.usage.total_tokens:
            embed.add_field(name="Tokens used", value=result.usage.total_tokens)
        
        await chunk_and_send(inter, result.output_text, embed)


class GptThink(commands.Cog):
    """Use OpenAI's reasoning models"""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.client: Optional[AsyncOpenAI] = None
        self.generating: Dict[int, bool] = {}
        self.user_last_prompt: Dict[int, datetime] = {}
        self.config = Config.get_conf(self, identifier=646156651)
        defaults_global = {
            "vip": [],
            "cooldown": 0,
            "model": "o4-mini",
        }
        self.config.register_global(**defaults_global)

    async def cog_load(self):
        await self.try_create_client()

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, _):
        if service_name == "openai":
            await self.try_create_client()

    async def try_create_client(self):
        api = await self.bot.get_shared_api_tokens("openai")
        api_key = api.get("api_key")
        if api_key:
            self.client = AsyncOpenAI(api_key=api_key)

    @app_commands.command(name="think", description="Open a prompt box for OpenAI's reasoning models.")
    @app_commands.describe(effort="How hard it will think after you write the prompt.")
    @app_commands.choices(effort=[
        app_commands.Choice(name="Low", value="low"),
        app_commands.Choice(name="Medium", value="medium"),
        app_commands.Choice(name="High", value="high"),
    ])
    @app_commands.guild_only()
    async def think_app(self, inter: discord.Interaction, effort: Optional[str]):
        await self.think(inter, effort or "medium")

    async def think(self, inter: discord.Interaction, effort: str):
        assert isinstance(inter.channel, discord.TextChannel)
        if not self.client:
            return await inter.response.send_message("OpenAI key not set.", ephemeral=True)
        if inter.user.id not in await self.config.vip():
            cooldown = await self.config.cooldown()
            if self.generating.get(inter.user.id, False):
                content = "Your current request must finish generating before you can make a new one."
                return await inter.response.send_message(content, ephemeral=True)
            if inter.user.id in self.user_last_prompt and \
                    (datetime.now() - self.user_last_prompt[inter.user.id]).total_seconds() < cooldown:
                eta = self.user_last_prompt[inter.user.id] + timedelta(seconds=cooldown)
                content = f"You may use this command again {discord.utils.format_dt(eta, 'R')}."
                return await inter.response.send_message(content, ephemeral=True)
            
        await inter.response.send_modal(GptThinkModal(self, effort))

        
    @commands.group() # type: ignore
    @commands.is_owner()
    async def gpthink(self, _):
        """Configure /think bot-wide."""
        pass

    @gpthink.command()
    async def model(self, ctx: commands.Context, model: Optional[str]):
        """The OpenAI reasoning model to use. Careful of costs, see https://openai.com/api/pricing/"""
        if model is None:
            model = await self.config.model()
        else:
            model = model.lower().strip()
            if model not in MODELS:
                await ctx.reply("Model must be one of: " + ",".join([f'`{m}`' for m in MODELS]))
                return
            await self.config.model.set(model)
        await ctx.reply(f"The /think command will use the {model} model.")

    @gpthink.command()
    async def cooldown(self, ctx: commands.Context, seconds: Optional[int]):
        """Time in seconds between when a user's generation ends and when they can start a new one."""
        if seconds is None:
            seconds = await self.config.cooldown()
        else:
            await self.config.cooldown.set(max(0, seconds))
        await ctx.reply(f"Users will need to wait {max(0, seconds or 0)} seconds between generations.")

    @gpthink.group(name="vip", invoke_without_command=True)
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
        await ctx.tick(message="VIP user(s) added")

    @vip.command(name="remove")
    async def vip_remove(self, ctx: commands.Context, *, users: str):
        """Remove a list of users from the VIP list."""
        user_ids = [int(uid) for uid in re.findall(r"([0-9]+)", users)]
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
