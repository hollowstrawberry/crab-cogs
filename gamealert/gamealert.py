import discord
import logging
from datetime import datetime, timedelta
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import *

log = logging.getLogger("red.crab-cogs.gamealert")


class GameAlert(commands.Cog):
    """Sends a configured message when a user has been playing a specific game for some time."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6761656165)
        self.alerts: Dict[int, List[dict]] = {}
        self.alerted: List[int] = []
        self.config.register_guild(alerts=[])
        self.alert_loop.start()

    async def load_config(self):
        all_config = await self.config.all_guilds()
        self.alerts = {guild_id: conf['alerts'] for guild_id, conf in all_config.items()}

    def cog_unload(self):
        self.alert_loop.stop()

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    # Loop

    @tasks.loop(seconds=15)
    async def alert_loop(self):
        for guild in self.bot.guilds:
            if guild.id not in self.alerts:
                continue
            if await self.bot.cog_disabled_in_guild(self, guild):
                continue
            for member in guild.members:
                log.info(f"{member.name} {member.activity}")
                if member.activity and member.activity.name and member.activity.created_at:
                    log.info(f"{member.activity.name} created_at:{member.activity.created_at}")
                    alert = next(iter(a for a in self.alerts[guild.id] if a['game_name'] == member.activity.name), None)
                    if alert and (datetime.utcnow() - member.activity.created_at) > timedelta.min(alert['delay_minutes']):
                        if member.id in self.alerted or not await self.bot.allowed_by_whitelist_blacklist(member):
                            continue
                        channel = guild.get_channel(alert['channel_id'])
                        message = alert['message']\
                            .replace("{user}", member.nick)\
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
            old_alert = [a for a in alerts if a.game_name == alert['game_name']]
            for a in old_alert:
                alerts.remove(a)
            alerts.append(alert)
            self.alerts[ctx.guild.id] = list(alerts)
            await ctx.react_quietly("✅")

    @gamealert.command()
    @commands.has_permissions(manage_guild=True)
    async def remove(self, ctx: commands.Context, *, game: str):
        """Remove an existing game alert by its game name."""
        async with self.config.guild(ctx.guild).autoreacts() as alerts:
            old_alert = [a for a in alerts if a.game_name == game]
            for a in old_alert:
                alerts.remove(a)
            self.alerts[ctx.guild.id] = list(alerts)
            if old_alert:
                await ctx.react_quietly("✅")
            else:
                await ctx.send("No alerts found for that game.")

    @gamealert.command()
    async def list(self, ctx: commands.Context, page: int = 1):
        """Shows all game alerts."""
        embed = discord.Embed(title="Server Game Alerts", color=await ctx.embed_color(), description="None")
        embed.set_footer(text=f"Page {page}")
        if ctx.guild.id in self.alerts and self.alerts[ctx.guild.id]:
            alerts = [f"- {alert['game_name']} in <#{alert['channel_id']}> after {alert['delay_minutes']} minutes"
                      for alert in self.alerts[ctx.guild.id]]
            alerts = alerts[10*(page-1):10*page]
            if alerts:
                embed.description = '\n'.join(alerts)
        await ctx.send(embed=embed)

    @gamealert.command()
    async def show(self, ctx: commands.Context, *, game: str):
        """Shows the message for an alert for a game."""
        alert = None
        if ctx.guild.id in self.alerts and self.alerts[ctx.guild.id]:
            alert = next(iter(a for a in self.alerts[ctx.guild.id] if a['game_name'] == game), None)
        await ctx.send(f"```\n{alert['response']}```" if alert else "No alert found for that game.")
