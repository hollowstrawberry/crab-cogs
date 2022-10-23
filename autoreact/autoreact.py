import re
import discord
import logging
from emoji import is_emoji
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import *

log = logging.getLogger("red.crab-cogs.autoreact")

class Autoreact(commands.Cog):
    """Lets you configure emojis that will be added to any message containing text matching a regex."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=61757472)
        self.autoreacts: Dict[int, Dict[str, re.Pattern]] = {}
        self.config.register_guild(autoreact_regex=[])

    async def load_config(self):
        all_config = await self.config.all_guilds()
        self.autoreacts = {guild_id: {emoji: re.compile(text) for emoji, text in conf['autoreact_regex']}
                           for guild_id, conf in all_config.items()}

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
        for emoji, regex in autoreact.items():
            if regex.search(message.content):
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
        """Reacts to specific text with an emoji."""
        await ctx.send_help()

    @autoreact.command()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def add(self, ctx: commands.Context, emoji: Union[discord.Emoji, str], *, pattern: str):
        """Add a new autoreact using regex."""
        if isinstance(emoji, str) and not is_emoji(emoji):
            await ctx.send("Sorry, that doesn't seem to be a valid emoji to react with.")
            return
        if isinstance(emoji, discord.Emoji) and emoji not in self.bot.emojis:
            await ctx.send("I must be in the same guild as an emoji to be able to use it!")
            return
        if len(pattern) > 400:
            await ctx.send("Sorry, the regex may not be longer than 400 characters.")
            return
        if pattern.startswith('`') and pattern.endswith('`'):
            pattern = pattern.strip('`')
        try:
            pattern = re.compile(pattern)
        except Exception as error:
            await ctx.send(f"Invalid regex pattern: {error}")
            return
        emoji = str(emoji)
        self.autoreacts.setdefault(ctx.guild.id, {})
        async with self.config.guild(ctx.guild).autoreact_regex() as autoreacts:
            autoreacts[emoji] = pattern
            self.autoreacts[ctx.guild.id][emoji] = pattern
            await ctx.react_quietly("✅")

    @autoreact.command()
    @commands.has_permissions(manage_guild=True)
    async def remove(self, ctx: commands.Context, emoji: Union[discord.Emoji, str]):
        """Remove an existing autoreact for an emoji."""
        if isinstance(emoji, str) and not is_emoji(emoji):
            await ctx.send("Sorry, that doesn't seem to be a valid emoji.")
            return
        emoji = str(emoji)
        self.autoreacts.setdefault(ctx.guild.id, {})
        async with self.config.guild(ctx.guild).autoreact_regex() as autoreacts:
            removed1 = autoreacts.pop(emoji, None)
            removed2 = self.autoreacts[ctx.guild.id].pop(emoji, None)
            if removed1 or removed2:
                await ctx.react_quietly("✅")
            else:
                await ctx.send("No autoreacts found for that emoji.")

    @autoreact.command()
    @commands.guild_only()
    async def list(self, ctx: commands.Context, page: int = 1):
        """Shows all autoreacts."""
        embed = discord.Embed(title="Server Autoreacts", color=await ctx.embed_color(), description="None")
        if ctx.guild.id in self.autoreacts and self.autoreacts[ctx.guild.id]:
            autoreacts = [f"{emoji} {text if '`' in text else f'`{text}`'}"
                          for text, emoji in self.autoreacts[ctx.guild.id].items()]
            embed.set_footer(text=f"Page {page}/{(9+len(autoreacts))//10}")
            autoreacts = autoreacts[10*(page-1):10*page]
            if autoreacts:
                embed.description = '\n'.join(autoreacts)
        await ctx.send(embed=embed)
