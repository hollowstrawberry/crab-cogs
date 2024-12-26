# https://github.com/Dav-Git/Dav-Cogs/tree/master/mcwhitelister

import io
import re
import base64
import logging
import discord
from typing import Dict, Tuple
from discord import Embed
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu
from mcstatus import JavaServer
from aiomcrcon import Client
from aiomcrcon.errors import IncorrectPasswordError, RCONConnectionError

log = logging.getLogger("red.crab-cogs.minecraft")

re_username = re.compile(r"^.?\w{3,30}$")


class Minecraft(commands.Cog):
    """Manage your Minecraft server from within your Discord server, and check server status and online players without opening the game."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.clients: Dict[int, Client] = {}
        self.config = Config.get_conf(self, identifier=110320200153)
        default_guild = {
            "players": {},
            "host": "localhost",
            "port": 25565,
            "rcon_port": 25575,
            "password": "",
            "players_to_delete": [],
        }
        self.config.register_guild(**default_guild)

    async def initialize(self):
        pass

    async def cog_load(self):
        all_data = await self.config.all_guilds()
        for guild_id, data in all_data.items():
            if data["password"]:
                self.clients[guild_id] = Client(data["host"], data["rcon_port"], data["password"])
            # old version
            updated = False
            for user_id, player in list(data["players"].items()):
                if isinstance(player, dict):
                    del data["players"][user_id]
                    data["players"][user_id] = player["name"]
                    updated = True
            if updated:
                await self.config.guild_from_id(guild_id).players.set(data["players"])

    async def cog_unload(self):
        for client in self.clients.values():
            await client.close()

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        all_data = await self.config.all_guilds()
        for guild_id in all_data:
            if str(user_id) in all_data[guild_id]["players"]:
                del all_data[guild_id]["players"][str(user_id)]
                await self.config.guild_from_id(guild_id).players.set(all_data[guild_id]["players"])


    async def run_minecraft_command(self, guild: discord.Guild, command: str) -> Tuple[bool, str]:
        if guild.id not in self.clients:
            return False, "Please set up the cog first."
        try:
            async with self.clients[guild.id] as client:
                resp = await client.send_cmd(command, 10)
            return True, resp[0]
        except (RCONConnectionError, TimeoutError) as error:
            return False, error or "Couldn't connect to the server."
        except IncorrectPasswordError:
            return False, "Incorrect RCON password."
        except Exception as error:  # catch everything to be able to give feedback to the user
            log.exception("Executing command")
            return False, f"{type(error).__name__}: {error}"


    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Remove member from whitelist when leaving guild"""
        players = await self.config.guild(member.guild).players()
        if str(member.id) in players:
            success, _ = await self.run_minecraft_command(member.guild, f"whitelist remove {players[str(member.id)]}")
            if not success:
                async with self.config.guild(member.guild).players_to_delete() as players_to_delete:
                    players_to_delete.append(players[str(member.id)])
            async with self.config.guild(member.guild).players() as cur_players:
                del cur_players[str(member.id)]


    async def delete_orphan_players(self, guild: discord.Guild):
        players_to_delete = await self.config.guild(guild).players_to_delete()
        if not players_to_delete:
            return
        for player in players_to_delete:
            success, _ = await self.run_minecraft_command(guild, f"whitelist remove {player}")
            if not success:
                return
            async with self.config.guild(guild).players_to_delete() as cur_players_to_delete:
                cur_players_to_delete.remove(player)
        await self.run_minecraft_command(guild, f"whitelist reload")


    @commands.group()
    async def minecraft(self, ctx):
        """Minecraft server commands"""
        pass


    @commands.guildowner()
    @minecraft.command()
    async def setup(self, ctx: commands.Context, host: str, port: int, rcon_port: int, *, password: str):
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
        if self.clients.get(ctx.guild.id, None):
            await self.clients[ctx.guild.id].close()
        self.clients[ctx.guild.id] = Client(host, rcon_port, password)
        try:
            async with self.clients[ctx.guild.id] as client:
                await client.send_cmd("help")
        except (RCONConnectionError, TimeoutError) as error:
            await ctx.send((error or "Could not connect to the server.") +
                           "\nMake sure your server is online and your values are correct, and that the RCON port is open to the public.")
        except IncorrectPasswordError:
            await ctx.send("Incorrect password.")
        except Exception as error:  # catch everything to be able to give feedback to the user
            log.exception("Executing command")
            if f"{error}" == "unpack requires a buffer of 4 bytes":
                await ctx.send("Could not connect to the server. You may have set the port and rcon port backwards.")
            else:
                await ctx.send(f"{type(error).__name__}: {error}")
        else:
            await ctx.send("✅ Server credentials saved!")


    @minecraft.command()
    async def status(self, ctx: commands.Context):
        """Display info about the Minecraft server."""
        host = await self.config.guild(ctx.guild).host()
        port = await self.config.guild(ctx.guild).port()
        ip = f"{host}:{port}"
        try:
            server = await JavaServer.async_lookup(ip)
            status = await server.async_status() if server else None
        except (ConnectionError, TimeoutError):
            status = None
        except Exception as error:  # python package is unclear as to the errors that may be raised
            if f"{error}" == "Socket did not respond with any information!":
                return await ctx.send("🟡 The server may be asleep! You can try joining to start it back up.")
            log.exception(f"Retrieving status for {ip}")
            return await ctx.send(f"An error occurred. {error}")

        if not status:
            embed = discord.Embed(title=f"Minecraft Server", color=0xFF0000)
            embed.add_field(name="IP", value=ip)
            embed.add_field(name="Status", value="🔴 Offline")
            file = None
        else:
            embed = discord.Embed(title=f"Minecraft Server", color=0x00FF00)
            if status.motd:
                embed.add_field(name="Description", value=status.motd.to_plain(), inline=False)
            embed.add_field(name="IP", value=ip)
            embed.add_field(name="Version", value=status.version.name)
            embed.add_field(name="Status", value="🟢 Online")
            embed.add_field(name=f"Players ({status.players.online}/{status.players.max})",
                            value="\n" + ", ".join([p.name for p in status.players.sample]) if status.players.online else "*None*")
            if status.icon:
                b = io.BytesIO(base64.b64decode(status.icon.removeprefix("data:image/png;base64,")))
                filename = "server.png"
                file = discord.File(b, filename=filename)
                embed.set_thumbnail(url=f"attachment://{filename}")
            else:
                file = None

        await ctx.send(embed=embed, file=file)


    @minecraft.command()
    async def join(self, ctx: commands.Context, name: str):
        """Add yourself to the whitelist. You will be removed when leaving the guild."""
        if not re_username.match(name):
            return await ctx.send(f"Invalid username.")

        players = await self.config.guild(ctx.guild).players()
        if str(ctx.author.id) in players:
            return await ctx.send(f"You are already whitelisted.\nYou can remove yourself with {ctx.clean_prefix}minecraft leave")

        success, msg = await self.run_minecraft_command(ctx.guild, f"whitelist add {name}")
        if "That player does not exist" in msg:
            return await ctx.send("Unknown player. Please attempt to join the server for it to recognize you.")
        await ctx.send(msg)
        if not success:
            return

        async with self.config.guild(ctx.guild).players() as cur_players:
            cur_players[str(ctx.author.id)] = name

        await self.delete_orphan_players(ctx.guild)


        success, msg = await self.run_minecraft_command(ctx.guild, "whitelist reload")
        await ctx.send(msg)


    @minecraft.command()
    async def leave(self, ctx: commands.Context):
        """Remove yourself from the whitelist."""
        players = await self.config.guild(ctx.guild).players()

        if str(ctx.author.id) not in players:
            return await ctx.send("You are not registered to the Minecraft server through Discord.")

        async with self.config.guild(ctx.guild).players() as cur_players:
            del cur_players[str(ctx.author.id)]

        success, msg = await self.run_minecraft_command(ctx.guild, f"whitelist remove {players[str(ctx.author.id)]}")
        await ctx.send(msg)
        if not success:
            async with self.config.guild(ctx.author.guild).players_to_delete() as players_to_delete:
                players_to_delete.append(players[str(ctx.author.id)])
            return

        await self.delete_orphan_players(ctx.guild)

        success, msg = await self.run_minecraft_command(ctx.guild, "whitelist reload")
        await ctx.send(msg)


    @commands.admin()
    @minecraft.command()
    async def add(self, ctx: commands.Context, name: str):
        """Add someone else to the whitelist by Minecraft username. They will not be removed automatically when leaving the guild."""
        if not re_username.match(name):
            return await ctx.send(f"Invalid username.")

        success, msg = await self.run_minecraft_command(ctx.guild, f"whitelist add {name}")
        await ctx.send(msg)
        if not success:
            return

        await self.delete_orphan_players(ctx.guild)

        success, msg = await self.run_minecraft_command(ctx.guild, "whitelist reload")
        await ctx.send(msg)


    @commands.admin()
    @minecraft.command()
    async def remove(self, ctx: commands.Context, name: str):
        """Remove someone else from the whitelist by their Minecraft username."""
        if not re_username.match(name):
            return await ctx.send(f"Invalid username.")

        success, msg = await self.run_minecraft_command(ctx.guild, f"whitelist remove {name}")
        await ctx.send(msg)
        if not success:
            return

        await self.delete_orphan_players(ctx.guild)

        success, msg = await self.run_minecraft_command(ctx.guild, "whitelist reload")
        await ctx.send(msg)


    @commands.admin()
    @minecraft.command()
    async def whitelist(self, ctx: commands.Context):
        """See who is whitelisted on your server."""

        success, msg = await self.run_minecraft_command(ctx.guild, "whitelist list")
        await ctx.send(msg if len(msg) <= 2000 else msg[:1997] + "...")

        if success:
            await self.delete_orphan_players(ctx.guild)

        players = await self.config.guild(ctx.guild).players()
        if len(players) == 0:
            await ctx.send("Nobody has whitelisted themselves through Discord.")
            return

        outstr = []
        for user_id, player in players.items():
            outstr.append(f"<@{user_id}> | {player}\n")

        pages = list(pagify("\n".join(outstr), page_length=1024))
        rendered = []
        for page in pages:
            emb = Embed(title="Whitelisted through Discord:", description=page, color=0xFFA500)
            rendered.append(emb)

        await menu(ctx, rendered, controls=DEFAULT_CONTROLS, timeout=60.0)


    @commands.guildowner()
    @minecraft.command()
    async def command(self, ctx: commands.Context, *, command: str):
        """Run a command on the Minecraft server. No validation is done."""
        if len(command) > 1440:
            return await ctx.send("Command too long!")
        success, resp = await self.run_minecraft_command(ctx.guild, command)
        await ctx.send(resp or "✅")
        if success:
            await self.delete_orphan_players(ctx.guild)
