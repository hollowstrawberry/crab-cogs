import re
import logging
import discord
from typing import Dict, List
from dataclasses import dataclass
from redbot.core import commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.crab-cogs.linkfixer")


@dataclass
class Link:
    name: str
    pattern: re.Pattern
    fixed: str


GENERIC_LINK = re.compile(r"(?<!<)https?://[^\s|)>\]]+")

ALL_LINKS = [
    Link(
        "twitter",
        re.compile(r"(?<!<)(https?://(?:www\.|m\.)?(?:x|twitter)\.com/([^\s]+status/[^\s|)>\]]+))"),
        "https://fxtwitter.com/"
    ),
    Link(
        "tiktok",
        re.compile(r"(?<!<)(https?://(?:www\.)?tiktok\.com/([^/]+/video/[^\s|)>\]]+)|https?://vm\.tiktok\.com/([^\s|)>\]]+))"),
        "https://kktiktok.com/"
    ),
    Link(
        "instagram",
        re.compile(r"(?<!<)(https?://(?:www\.)?instagram\.com/([^/]+/[^\s|)>\]]+))"),
        "https://kkinstagram.com/"
    ),
    Link(
        "reddit",
        re.compile(r"(?<!<)(https?://(?:www\.|old\.)?reddit\.com/(r/[^/]+/[^\s|)>\]]+))"),
        "https://vxreddit.com/"
    ),
    Link(
        "pixiv",
        re.compile(r"(?<!<)(https?://(?:www\.)?pixiv\.net/([^\s|)>\]]+))"),
        "https://phixiv.net/"
    ),
]


class LinkFixer(commands.Cog):
    """Sends modified links to embed content from popular social media sites."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=44141349)
        self.config.register_guild(**{
            "enabled": False,
            "disabled_links": [],
        })
        self.enabled_guilds: List[int] = []
        self.disabled_links: Dict[int, List[str]] = {}

    async def cog_load(self):
        all_guilds = await self.config.all_guilds()
        for gid, config in all_guilds.items():
            if config.get("enabled", False):
                self.enabled_guilds.append(gid)
                self.disabled_links[gid] = config.get("disabled_links", [])

    async def red_delete_data_for_user(self, *args, **kwargs):
        """Nothing to delete"""
        pass

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if not message.guild or message.guild.id not in self.enabled_guilds:
            return
        perms = message.channel.permissions_for(message.guild.me)
        if not perms.send_messages or not perms.embed_links:
            return
        if not await self.is_valid_red_message(message):
            return
        
        matched_links = list(dict.fromkeys(GENERIC_LINK.findall(message.content)))
        for i in range(len(matched_links)):
            spoilered = f"||{matched_links[i]}||"
            if spoilered in message.content:
                matched_links[i] = spoilered
        matched_links.insert(0, "-# I fixed the links so the content embeds better.")

        allowed_links = [link for link in ALL_LINKS if link.name not in self.disabled_links.get(message.guild.id, [])]
        for link in allowed_links:
            any_fixed = False
            matches = link.pattern.findall(message.content)
            for match in matches:
                any_fixed = True
                log.info(match)
                tail = [m for m in match if m][-1]
                try:
                    if f"||{match[0]}||" in matched_links:
                        matched_links[matched_links.index(f"||{match[0]}||")] = f"||{link.fixed}{tail}||"
                    else:
                        matched_links[matched_links.index(match[0])] = f"{link.fixed}{tail}"
                except ValueError:
                    pass

        if not any_fixed:
            return

        await message.channel.send("\n".join(matched_links))
        if message.channel.permissions_for(message.guild.me).manage_messages:
            await message.edit(suppress=True)

    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return await self.bot.allowed_by_whitelist_blacklist(message.author) \
            and await self.bot.ignored_channel_or_guild(message) \
            and not await self.bot.cog_disabled_in_guild(self, message.guild)
    
    @commands.group(name="linkfixer", aliases=["linkfix"])  # type: ignore
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def command_linkfixer(self, _: commands.Context):
        """Configure the LinkFixer cog."""
        pass

    @command_linkfixer.command(name="enable")
    async def command_linkfixer_enable(self, ctx: commands.Context):
        """Enable LinkFixer in this server."""
        assert ctx.guild
        await self.config.guild(ctx.guild).enabled.set(True)
        if ctx.guild.id not in self.enabled_guilds:
            self.enabled_guilds.append(ctx.guild.id)
        await ctx.reply(f"✅ LinkFixer enabled in {ctx.guild.name}")

    @command_linkfixer.command(name="disable")
    async def command_linkfixer_disable(self, ctx: commands.Context):
        """Disable LinkFixer in this server."""
        assert ctx.guild
        await self.config.guild(ctx.guild).enabled.set(False)
        if ctx.guild.id in self.enabled_guilds:
            self.enabled_guilds.remove(ctx.guild.id)
        await ctx.reply(f"✅ LinkFixer disabled in {ctx.guild.name}")
       
    @command_linkfixer.group(name="link", aliases=["links"])
    async def command_linkfixer_links(self, _: commands.Context):
        """List or toggle available links for the fixer."""
        pass

    @command_linkfixer_links.command(name="list")
    async def command_linkfixer_links_list(self, ctx: commands.Context):
        """List all available links for the fixer."""
        assert ctx.guild
        disabled_links = await self.config.guild(ctx.guild).disabled_links()
        links = []
        for link in ALL_LINKS:
            links.append(f"`{link.name}`: {'disabled' if link.name in disabled_links else 'enabled'}")
        await ctx.send(">>> " + "\n".join(links))

    @command_linkfixer_links.command(name="toggle")
    async def command_linkfixer_links_toggle(self, ctx: commands.Context, link_name: str):
        assert ctx.guild
        """Enables or disables a link fix."""
        link_names = [link.name for link in ALL_LINKS]
        if link_name not in link_names:
            await ctx.send("Link fix not found, valid values are: " + ", ".join([f"`{name}`" for name in link_names]))
            return
        disabled_links: list[str] = await self.config.guild(ctx.guild).disabled_links()
        enabled = link_name not in disabled_links
        if enabled:
            disabled_links.append(link_name)
        else:
            disabled_links.remove(link_name)
        await self.config.guild(ctx.guild).disabled_links.set(disabled_links)
        self.disabled_links[ctx.guild.id] = disabled_links
        enabled = not enabled
        await ctx.send(f"`{link_name}`: {'enabled' if enabled else 'disabled'}")
