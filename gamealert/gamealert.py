import logging
import discord
from typing import List, Dict
from datetime import datetime, timezone
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.views import SimpleMenu

log = logging.getLogger("red.crab-cogs.gamealert")

def batched(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


class GameAlert(commands.Cog):
    """Sends a configured message when a user has been playing a specific game for some time."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6761656165)
        self.alerts: Dict[int, List[Dict]] = {}
        self.alerted: List[int] = []
        self.config.register_guild(alerts=[])
        self.alert_loop.start()

    async def cog_load(self):
        all_config = await self.config.all_guilds()
        self.alerts = {guild_id: conf['alerts'] for guild_id, conf in all_config.items()}

    def cog_unload(self):
        self.alert_loop.stop()

    # Loop

    @tasks.loop(seconds=15)
    async def alert_loop(self):
        for guild_id in self.alerts:
            if not (guild := self.bot.get_guild(guild_id)):
                continue
            if await self.bot.cog_disabled_in_guild(self, guild):
                continue
            for member in guild.members:
                activity = next(iter(act for act in member.activities if act.type == discord.ActivityType.playing), None)
                if activity and activity.name and activity.created_at:
                    alert = next(iter(a for a in self.alerts[guild.id] if a['game_name'] == activity.name), None)
                    if alert and (datetime.now(timezone.utc) - activity.created_at).total_seconds() > 60 * alert['delay_minutes']:
                        if member.id in self.alerted or not await self.bot.allowed_by_whitelist_blacklist(member):
                            continue
                        channel = guild.get_channel(alert['channel_id'])
                        message = alert['message']\
                            .replace("{user}", member.display_name)\
                            .replace("{mention}", member.mention)
                        try:
                            await channel.send(message)
                            self.alerted.append(member.id)
                        except Exception as error:
                            log.warning(f"Failed to send game alert in {alert['channel_id']} - {type(error).__name__}: {error}", exc_info=True)
                elif member.id in self.alerted:
                    self.alerted.remove(member.id)

    @alert_loop.before_loop
    async def alert_loop_before(self):
        await self.bot.wait_until_red_ready()

    # Commands

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def gamealert(self, ctx: commands.Context):
        """Send a message when someone is playing a game for some time."""
        await ctx.send_help()

    @gamealert.command()
    @commands.has_permissions(manage_guild=True)
    async def add(self, ctx: commands.Context, game: str, delay: int, *, message: str):
        """Add a new game alert to this channel. Usage:
        `[p]gamealert add \"game\" <delay in minutes> <message>`
        The message may contain {user} or {mention}"""
        if len(message) > 1000:
            await ctx.send("Sorry, the message may not be longer than 1000 characters.")
            return
        async with self.config.guild(ctx.guild).alerts() as alerts:
            alert = {'game_name': game, 'message': message, 'delay_minutes': max(delay, 0), 'channel_id': ctx.channel.id}
            old_alert = [a for a in alerts if a['game_name'] == alert['game_name']]
            for a in old_alert:
                alerts.remove(a)
            alerts.append(alert)
            self.alerts[ctx.guild.id] = list(alerts)
            await ctx.tick()

    @gamealert.command()
    @commands.has_permissions(manage_guild=True)
    async def remove(self, ctx: commands.Context, *, game: str):
        """Remove an existing game alert by its game name."""
        async with self.config.guild(ctx.guild).alerts() as alerts:
            old_alert = [a for a in alerts if a['game_name'] == game]
            for a in old_alert:
                alerts.remove(a)
            self.alerts[ctx.guild.id] = list(alerts)
            if old_alert:
                await ctx.tick()
            else:
                await ctx.send("No alerts found for that game.")

    @gamealert.command()
    async def list(self, ctx: commands.Context):
        """Shows all game alerts."""
        if ctx.guild.id not in self.alerts or not self.alerts[ctx.guild.id]:
            return await ctx.send("None.")
        alerts = [f"- {alert['game_name']} in <#{alert['channel_id']}> after {alert['delay_minutes']} minutes"
                  for alert in self.alerts[ctx.guild.id]]
        pages = []
        for i, batch in enumerate(batched(alerts, 10)):
            embed = discord.Embed(title="Server Autoreacts", color=await ctx.embed_color())
            if len(alerts) > 10:
                embed.set_footer(text=f"Page {i+1}/{(9+len(alerts))//10}")
            embed.description = '\n'.join(batch)
            pages.append(embed)
        if len(pages) == 1:
            await ctx.send(embed=pages[0])
        else:
            await SimpleMenu(pages, timeout=600).start(ctx)

    @gamealert.command()
    async def show(self, ctx: commands.Context, *, game: str):
        """Shows the message for an alert for a game."""
        alert = None
        if ctx.guild.id in self.alerts and self.alerts[ctx.guild.id]:
            alert = next(iter(a for a in self.alerts[ctx.guild.id] if a['game_name'] == game), None)
        await ctx.send(f"```\n{alert['message']}```" if alert else "No alert found for that game.")
