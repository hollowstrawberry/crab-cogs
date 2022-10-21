import discord
import logging
from emoji import is_emoji
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import *

log = logging.getLogger("red.crab-cogs.autoreact")

class Autoreact(commands.Cog):
    """Lets you configure emojis that will be added to any message containing specific text."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=61757472)
        self.autoreacts: Dict[int, List[Tuple[str, str]]] = {}
        self.config.register_guild(autoreacts=[])

    async def load_config(self):
        all_config = await self.config.all_guilds()
        self.autoreacts = {guild_id: conf['autoreacts'] for guild_id, conf in all_config.items()}

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    # Listeners

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        channel_perms = message.channel.permissions_for(message.guild.me)
        if not channel_perms.add_reactions:
            return
        autoreact = self.autoreacts.get(message.guild.id, None)
        if not autoreact:
            return
        if not await self.is_valid_red_message(message):
            return
        for text, emoji in autoreact:
            if text in message.content:
                try:
                    await message.add_reaction(emoji)
                except Exception as error:
                    log.warning(f"Failed to react with {emoji} - {type(error).__name__}: {error}", exc_info=True)

    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return await self.bot.allowed_by_whitelist_blacklist(message.author) \
               and await self.bot.ignored_channel_or_guild(message) \
               and not await self.bot.cog_disabled_in_guild(self, message.guild)

    # Commands

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def autoreact(self, ctx: commands.Context):
        """Reacts to a specific text with an emoji."""
        await ctx.send_help()

    @autoreact.command()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def add(self, ctx: commands.Context, emoji: Union[discord.Emoji, str], *, text: str):
        """Add a new autoreact with an emoji to a text."""
        if isinstance(emoji, str) and not is_emoji(emoji):
            await ctx.send("Sorry, that doesn't seem to be a valid emoji to react with.")
            return
        if len(text) > 200:
            await ctx.send("Sorry, the target text may not be longer than 200 characters.")
            return
        async with self.config.guild(ctx.guild).autoreacts() as autoreacts:
            pair = (text, str(emoji))
            if pair in autoreacts:
                await ctx.react_quietly("✅")
                return
            autoreacts.append(pair)
            self.autoreacts.setdefault(ctx.guild.id, [])
            self.autoreacts[ctx.guild.id].append(pair)
            await ctx.react_quietly("✅")

    @autoreact.command()
    @commands.has_permissions(manage_guild=True)
    async def removetext(self, ctx: commands.Context, *, text: str):
        """Remove existing autoreacts for a target text."""
        self.autoreacts.setdefault(ctx.guild.id, [])
        async with self.config.guild(ctx.guild).autoreacts() as autoreacts:
            removed = any(pair[0] == text for pair in autoreacts)
            autoreacts[:] = [pair for pair in autoreacts if pair[0] != text]
            self.autoreacts[ctx.guild.id] = list(autoreacts)
            if removed:
                await ctx.react_quietly("✅")
            else:
                await ctx.send("No autoreacts found for that text.")

    @autoreact.command()
    @commands.has_permissions(manage_guild=True)
    async def removeemoji(self, ctx: commands.Context, emoji: Union[discord.Emoji, str]):
        """Remove existing autoreacts for an emoji."""
        if isinstance(emoji, str) and not is_emoji(emoji):
            await ctx.send("Sorry, that doesn't seem to be a valid emoji.")
            return
        if isinstance(emoji, discord.Emoji) and emoji not in self.bot.emojis:
            await ctx.send("I must be in the same guild as an emoji to be able to use it!")
            return
        self.autoreacts.setdefault(ctx.guild.id, [])
        async with self.config.guild(ctx.guild).autoreacts() as autoreacts:
            removed = any(pair[1] == emoji for pair in autoreacts)
            autoreacts[:] = [pair for pair in autoreacts if pair[1] != emoji]
            self.autoreacts[ctx.guild.id] = list(autoreacts)
            if removed:
                await ctx.react_quietly("✅")
            else:
                await ctx.send("No autoreacts found for that emoji.")

    @autoreact.command()
    async def list(self, ctx: commands.Context, page: int = 1):
        """Shows all autoreacts."""
        embed = discord.Embed(title="Server Autoreacts", color=await ctx.embed_color(), description="None")
        if ctx.guild.id in self.autoreacts and self.autoreacts[ctx.guild.id]:
            autoreacts = [f"{emoji} {text if '`' in text else f'`{text}`'}"
                          for text, emoji in self.autoreacts[ctx.guild.id]]
            embed.set_footer(text=f"Page {page}/{(9+len(autoreacts))//10}")
            autoreacts = autoreacts[10*(page-1):10*page]
            if autoreacts:
                embed.description = '\n'.join(autoreacts)
        await ctx.send(embed=embed)
