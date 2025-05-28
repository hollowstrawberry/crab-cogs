from base64 import b64encode
import discord
from io import BytesIO
from typing import Optional
from redbot.core import commands, Config
from redbot.core.bot import Red

from openai import AsyncOpenAI

VISION_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
]
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_PROMPT = """
You are in a Discord server and are tasked with welcoming new users.
When welcoming a user, give them a personalized message, mentioning something unique about the contents of their avatar or about their username.
Never say things like "I'm sorry" or "I can't assist with that". Instead, if something would break your content guidelines, pretend it's not there.
""".strip()


class GptWelcome(commands.Cog):
    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.openai_client: Optional[AsyncOpenAI] = None
        self.config = Config.get_conf(self, identifier=1947582011)
        self.config.register_guild(**{
            "enabled": False,
            "prompt": DEFAULT_PROMPT,
            "model": DEFAULT_MODEL,
        })

    async def cog_load(self):
        await self.initialize_openai_client()

    async def cog_unload(self):
        if self.openai_client:
            await self.openai_client.close()

    async def initialize_openai_client(self):
        api_key = (await self.bot.get_shared_api_tokens("openai")).get("api_key")
        if not api_key:
            return
        self.openai_client = AsyncOpenAI(api_key=api_key)

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name, _):
        if service_name == "openai":
            await self.initialize_openai_client()

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if message.type != discord.MessageType.new_member:
            return
        
        ctx: commands.Context = await self.bot.get_context(message)  # noqa
        if await self.bot.cog_disabled_in_guild(self, ctx.guild):
            return
        if not await self.bot.ignored_channel_or_guild(ctx):
            return
        if not await self.bot.allowed_by_whitelist_blacklist(ctx.author):
            return
        
        await self.welcome_user(ctx)

    async def welcome_user(self, ctx: commands.Context):
        if not self.openai_client:
            await self.initialize_openai_client()
        if not self.openai_client:
            return
        
        prompt = await self.config.guild(ctx.guild).prompt()
        if not prompt:
            return
        
        messages =  [{ "role": "system", "content": prompt }]
        whojoined = f"The following user has joined the server: {ctx.author.display_name}"

        # Attach the user's avatar
        fp = BytesIO()
        try:
            await ctx.author.display_avatar.with_format("png").with_size(512).save(fp)
        except (discord.DiscordException, TypeError):
            messages.append({ "role": "user", "content": whojoined })
        else:
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": whojoined
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64encode(fp.read()).decode()}"
                        }
                    }
                ]
            })

        model = await self.config.guild(ctx.guild).model()
        response = await self.openai_client.beta.chat.completions.parse(
            model=model,
            messages=messages
        )
        completion = response.choices[0].message.content
        await ctx.reply(content=completion, mention_author=True)

    @commands.group(name="gptwelcome", aliases=["aiwelcome", "llmwelcome"])
    async def gptwelcome(self, _: commands.Context):
        """Base command for configuring the GPT Welcome cog."""
        pass

    @gptwelcome.command("enable")
    @commands.is_owner()
    async def gptwelcome_enable(self, ctx: commands.Context):
        """Enables GPT Welcome for this server."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.tick(message="Enabled")

    @gptwelcome.command("disable")
    @commands.has_permissions(manage_guild=True)
    async def gptwelcome_disable(self, ctx: commands.Context):
        """Disable GPT Welcome for this server."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.tick(message="Disabled")

    @gptwelcome.command("model")
    @commands.is_owner()
    async def gptwelcome_model(self, ctx: commands.Context, model: Optional[str]):
        """Views or changes the OpenAI model being used for welcoming."""
        if not model or not model.strip():
            model = await self.config.guild(ctx.guild).model()
            await ctx.reply(f"Current model for the welcomer is {model}")
        elif model.strip().lower() not in VISION_MODELS:
            await ctx.reply("Invalid model!\nValid models are " + ",".join([f"`{m}`" for m in VISION_MODELS]))
        else:
            await self.config.guild(ctx.guild).model.set(model.strip().lower())
            await ctx.tick(message="Model changed")

    @gptwelcome.command(name="prompt")
    @commands.has_permissions(manage_guild=True)
    async def gptwelcome_prompt(self, ctx: commands.Context, *, prompt: Optional[str]):
        """Gives you the current prompt or sets a new prompt for the AI welcomer. Use "reset" to reset."""
        if not prompt or not prompt.strip():
            prompt = await self.config.guild(ctx.guild).prompt()
            await ctx.reply(f"`current welcomer prompt`\n>>> {prompt or '*None*'}", mention_author=False)
        elif prompt.strip().lower() in ["default", "reset"]:
            await self.config.guild(ctx.guild).prompt.set(DEFAULT_PROMPT)
            await ctx.reply(f"`new welcomer prompt`\n>>> {prompt.strip()}", mention_author=False)
        else:
            await self.config.guild(ctx.guild).prompt.set(prompt.strip())
            await ctx.reply(f"`new welcomer prompt`\n>>> {prompt.strip()}", mention_author=False)

    @gptwelcome.command(name="test")
    async def gptwelcome_test(self, ctx: commands.Context):
        """Simulates you joining the server"""
        if not await self.config.guild(ctx.guild).enabled():
            await ctx.reply("GPT welcomer not enabled.")
            return
        if not await self.config.guild(ctx.guild).prompt():
            await ctx.reply("Prompt not set.")
            return
        if not ctx.guild.system_channel:
            await ctx.reply("Your server doesn't have a configured `System Messages Channel` set. The bot needs to use those welcome messages to ping the user who joined.")
            return
        if not ctx.guild.system_channel.permissions_for(ctx.guild.me).send_messages:
            await ctx.reply(f"The bot doesn't have permission to send messages in the {ctx.guild.system_channel.mention} channel, which is where your server is configured to send welcome messages.")
            return
        await self.welcome_user(ctx)
