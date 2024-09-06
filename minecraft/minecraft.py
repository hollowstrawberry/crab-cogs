# https://github.com/Dav-Git/Dav-Cogs/tree/master/mcwhitelister

import io
import re
import json
import base64
import logging
import discord
from discord import Embed
from redbot.core import Config, commands
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu
from aiomcrcon import Client
from aiomcrcon.errors import IncorrectPasswordError, RCONConnectionError
from mcstatus import JavaServer

log = logging.getLogger("red.crab-cogs.minecraft")
re_username = re.compile("^[a-zA-Z0-9_]{3,30}$")


class Minecraft(commands.Cog):
    """Manage a Minecraft server from Discord."""
    __version__ = "3.1.1"

    def format_help_for_context(self, ctx: commands.Context) -> str:
        # Thanks Sinbad! And Trusty in whose cogs I found this.
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nVersion: {self.__version__}"

    def __init__(self, bot):
        self.config = Config.get_conf(self, identifier=110320200153)
        default_guild = {
            "players": {},
            "host": "localhost",
            "port":25565,
            "rcon_port": 25575,
            "password": ""}
        self.config.register_guild(**default_guild)
        self.config.register_global(notification=0)
        self.bot = bot

    async def initialize(self):
        await self.bot.wait_until_red_ready()

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Remove member from whitelist when leaving guild"""
        p_in_conf = await self.config.guild(member.guild).players()
        host = await self.config.guild(member.guild).host()
        port = await self.config.guild(member.guild).rcon_port()
        passw = await self.config.guild(member.guild).password()
        if str(member.id) in p_in_conf:
            async with Client(host, port, passw) as client:
                await client.send_cmd(f"whitelist remove {p_in_conf[str(member.id)]['name']}")
            del p_in_conf[str(member.id)]
            await self.config.guild(member.guild).players.set(p_in_conf)

    @commands.group()
    async def minecraft(self, ctx):
        """Minecraft server commands"""
        pass

    @commands.guildowner()
    @minecraft.command()
    async def setup(self, ctx, host: str, port: int, rcon_port: int, *, password: str):
        """Set up the cog.

        `host`: The IP/URL of your minecraft server.
        `port`: Your server's normal port. (The default is 25565)
        `rcon_port`: Your server's RCON port. (The default is 25575)
        `password`: The RCON password.
        RCON needs to be enabled and set up in your `server.properties` file.
        More information is available [here](https://minecraft.wiki/w/Server.properties)
        """
        await ctx.message.delete()
        await self.config.guild(ctx.guild).host.set(host)
        await self.config.guild(ctx.guild).port.set(port)
        await self.config.guild(ctx.guild).rcon_port.set(rcon_port)
        await self.config.guild(ctx.guild).password.set(password)
        try:
            async with Client(host, rcon_port, password) as c:
                await c.send_cmd("help")
        except RCONConnectionError:
            await ctx.send("Could not connect to server.")
        except IncorrectPasswordError:
            await ctx.send("Incorrect password.")
        else:
            await ctx.send("Server credentials saved.")

    @minecraft.command()
    async def status(self, ctx):
        """Display info about the Minecraft server."""
        host = await self.config.guild(ctx.guild).host()
        port = await self.config.guild(ctx.guild).port()
        ip = f"{host}:{port}"
        try:
            server = await JavaServer.async_lookup(ip)
            status = await server.async_status() if server else None
        except Exception as e:
            if f"{e}" == "Socket did not respond with any information!":
                return await ctx.send("🟡 The server is asleep! You can join to start it back up.")
            return await ctx.send(f"An error occurred. {e}")

        if not status:
            embed = discord.Embed(title=f"Minecraft Server", color=0xFF0000)
            embed.add_field(name="IP", value=ip)
            embed.add_field(name="Status", value="🔴 Offline")
            return embed
        else:
            embed = discord.Embed(title=f"Minecraft Server", color=0x00FF00)
            if status.description:
                embed.add_field(name="Description", value=status.description, inline=False)
            if status.motd and status.motd.simplify().raw.strip() != status.description.strip():
                embed.add_field(name="MOTD", value=status.motd.simplify().raw, inline=False)
            embed.add_field(name="IP", value=ip)
            embed.add_field(name="Version", value=status.version.name)
            embed.add_field(name="Status", value="🟢 Online")
            embed.add_field(name=f"Players ({status.players.online}/{status.players.max})",
                            value="\n" + ", ".join([p.name for p in status.players.sample]) if status.players.online else "*None*")
            b = io.BytesIO(base64.b64decode(status.icon.removeprefix("data:image/png;base64,")))
            filename = "server.png"
            file = discord.File(b, filename=filename)
            embed.set_thumbnail(url=f"attachment://{filename}")
        await ctx.send(embed=embed, file=file)

    @minecraft.command()
    async def join(self, ctx, name: str):
        """Add yourself to the whitelist."""
        if not re_username.match(name):
            return await ctx.send(f"Invalid username.")
        p_in_conf = await self.config.guild(ctx.guild).players()
        if str(ctx.author.id) in p_in_conf:
            return await ctx.send(f"You are already whitelisted.\nRemove yourself first with {ctx.clean_prefix}minecraft leave")
        host = await self.config.guild(ctx.guild).host()
        port = await self.config.guild(ctx.guild).rcon_port()
        passw = await self.config.guild(ctx.guild).password()
        p_in_conf[ctx.author.id] = {"name": name}
        await self.config.guild(ctx.guild).players.set(p_in_conf)
        async with Client(host, port, passw) as c:
            resp = await c.send_cmd(f"whitelist add {name}", 30)
        await ctx.send(resp[0])
        async with Client(host, port, passw) as c:
            resp = await c.send_cmd("whitelist reload")
        await ctx.send(resp[0])

    @minecraft.command()
    async def leave(self, ctx):
        """Remove yourself from the whitelist."""
        p_in_conf = await self.config.guild(ctx.guild).players()
        host = await self.config.guild(ctx.guild).host()
        port = await self.config.guild(ctx.guild).rcon_port()
        passw = await self.config.guild(ctx.guild).password()
        if str(ctx.author.id) in p_in_conf:
            deleted = p_in_conf[str(ctx.author.id)]
            del p_in_conf[str(ctx.author.id)]
            async with Client(host, port, passw) as c:
                resp = await c.send_cmd(f"whitelist remove {deleted}")
            await self.config.guild(ctx.guild).players.set(p_in_conf)
            await ctx.send(resp[0])
        else:
            await ctx.send("That Minecraft account is not whitelisted on the server.")
        async with Client(host, port, passw) as c:
            resp = await c.send_cmd("whitelist reload")
        await ctx.send(resp[0])

    @commands.admin()
    @minecraft.command()
    async def add(self, ctx, name: str):
        """Add someone else to the whitelist.\nThey will not be removed automatically when leaving the guild."""
        if not re_username.match(name):
            return await ctx.send(f"Invalid username.")
        host = await self.config.guild(ctx.guild).host()
        port = await self.config.guild(ctx.guild).rcon_port()
        passw = await self.config.guild(ctx.guild).password()
        async with Client(host, port, passw) as c:
            resp = await c.send_cmd(f"whitelist add {name}", 30)
        await ctx.send(resp[0])
        async with Client(host, port, passw) as c:
            resp = await c.send_cmd("whitelist reload")
        await ctx.send(resp[0])

    @commands.admin()
    @minecraft.command()
    async def remove(self, ctx, name: str):
        """Remove someone else from the whitelist.\nThis might not be reflected correctly in `[p]minecraft whitelist`."""
        if not re_username.match(name):
            return await ctx.send(f"Invalid username.")
        host = await self.config.guild(ctx.guild).host()
        port = await self.config.guild(ctx.guild).rcon_port()
        passw = await self.config.guild(ctx.guild).password()
        async with Client(host, port, passw) as c:
            resp = await c.send_cmd(f"whitelist remove {name}", 30)
        await ctx.send(resp[0])
        async with Client(host, port, passw) as c:
            resp = await c.send_cmd("whitelist reload")
        await ctx.send(resp[0])

    @commands.admin()
    @minecraft.command()
    async def whitelist(self, ctx):
        """See who is whitelisted on your server."""
        host = await self.config.guild(ctx.guild).host()
        port = await self.config.guild(ctx.guild).rcon_port()
        passw = await self.config.guild(ctx.guild).password()
        async with Client(host, port, passw) as c:
            resp = await c.send_cmd("whitelist list")
        await ctx.send(resp[0] if len(resp[0]) < 1900 else resp[0][:1900] + "...")
        p_in_config = await self.config.guild(ctx.guild).players()
        outstr = []
        if len(p_in_config) == 0:
            await ctx.send("Nobody was whitelisted themselves through Discord.")
            return
        for e in p_in_config:
            outstr.append(f"{ctx.guild.get_member(int(e)).mention} | {p_in_config[e]['name']}\n")
        pages = list(pagify("\n".join(outstr), page_length=1024))
        rendered = []
        for page in pages:
            emb = Embed(title="Whitelisted through Discord:", description=page, color=0xFFA500)
            rendered.append(emb)
        await menu(ctx, rendered, controls=DEFAULT_CONTROLS, timeout=60.0)

    @commands.guildowner()
    @minecraft.command()
    async def command(self, ctx, *, command):
        """Run a command on the Minecraft server.\n\n**NO VALIDATION is performed on your inputs.**"""
        host = await self.config.guild(ctx.guild).host()
        port = await self.config.guild(ctx.guild).rcon_port()
        passw = await self.config.guild(ctx.guild).password()
        async with Client(host, port, passw) as c:
            resp = await c.send_cmd(command)
        await ctx.send(resp[0] or "✅")
