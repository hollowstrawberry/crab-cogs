from youtubesearchpython.__future__ import VideosSearch
from yt_dlp import YoutubeDL
import os
import re
import logging
import asyncio
import discord
from copy import copy
from redbot.core import commands, app_commands
from redbot.core.bot import Red
from redbot.core.commands import Cog
from redbot.cogs.audio import Audio
from redbot.cogs.audio.utils import PlaylistScope
from redbot.cogs.audio.converters import PlaylistConverter, ScopeParser
from redbot.cogs.audio.apis.playlist_interface import get_all_playlist
from typing import Optional

log = logging.getLogger("red.crab-cogs.audioslash")

BACKUP_MODE = True
DOWNLOAD_CONFIG = {'extract_audio': True, 'format': 'bestaudio', 'outtmpl': '%(title)s.mp3'}
DOWNLOAD_FOLDER = "audioslash_backup_downloads"
YOUTUBE_LINK_PATTERN = re.compile(r"(https?://)?(www\.)?(youtube.com/watch|youtu.be/)")

async def extract_info(ydl: YoutubeDL, url: str) -> dict:
    return await asyncio.to_thread(ydl.extract_info, url, False)

async def download_video(ydl: YoutubeDL, url: str) -> dict:
    return await asyncio.to_thread(ydl.extract_info, url)


class AudioSlash(Cog):
    """Audio cog commands in the form of slash commands, with YouTube and playlist autocomplete."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    async def red_delete_data_for_user(self, **kwargs):
        pass

    async def get_audio_cog(self, inter: discord.Interaction) -> Optional[Audio]:
        cog: Optional[Audio] = self.bot.get_cog("Audio")
        if cog:
            return cog
        await inter.response.send_message("Audio cog not loaded! Contact the bot owner for more information.", ephemeral=True)

    async def get_context(self, inter: discord.Interaction, cog: Audio) -> commands.Context:
        ctx: commands.Context = await self.bot.get_context(inter)  # noqa
        ctx.command.cog = cog
        return ctx

    async def can_run_command(self, ctx: commands.Context, command_name: str) -> bool:
        prefix = await self.bot.get_prefix(ctx.message)
        prefix = prefix[0] if isinstance(prefix, list) else prefix
        fake_message = copy(ctx.message)
        fake_message.content = prefix + command_name
        command = ctx.bot.get_command(command_name)
        fake_context: commands.Context = await ctx.bot.get_context(fake_message)  # noqa
        try:
            can = await command.can_run(fake_context, check_all_parents=True, change_permission_state=False)
        except commands.CommandError:
            can = False
        if not can:
            await ctx.send("You do not have permission to do this.", ephemeral=True)
        return can

    @app_commands.command()
    @app_commands.guild_only
    @app_commands.describe(search="Type here to get suggestions, or send anything to get a best match.",
                           when="You can choose when this track will play in the queue.")
    @app_commands.choices(when=[app_commands.Choice(name="Add to the end of the queue.", value="end"),
                                app_commands.Choice(name="Play after the current song.", value="next"),
                                app_commands.Choice(name="Start playing immediately.", value="now")])
    async def play(self, inter: discord.Interaction, search: str, when: Optional[str]):
        """Search a YouTube video to play in voicechat."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)

        if BACKUP_MODE:
            if not audio.local_folder_current_path:
                await ctx.send("Connect bot to a voice channel first")
                return
            if YOUTUBE_LINK_PATTERN.match(search):
                (audio.local_folder_current_path / DOWNLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
                os.chdir(audio.local_folder_current_path / DOWNLOAD_FOLDER)
                ydl = YoutubeDL(DOWNLOAD_CONFIG)
                video_info = await extract_info(ydl, search)
                log.info(video_info)
                filename = ydl.prepare_filename(video_info)
                if not os.path.exists(filename):
                    await ctx.send("Downloading video...")
                    await download_video(ydl, search)
                search = DOWNLOAD_FOLDER + "/" + filename

        if when in ("next", "now"):
            if not await self.can_run_command(ctx, "bumpplay"):
                return
            await audio.command_bumpplay(ctx, when == "now", query=search)
        else:
            if not await self.can_run_command(ctx, "play"):
                return
            await audio.command_play(ctx, query=search)

    @app_commands.command()
    @app_commands.guild_only
    async def pause(self, inter: discord.Interaction):
        """Pauses or resumes the music in voicechat."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        if not await self.can_run_command(ctx, "pause"):
            return
        await audio.command_pause(ctx)

    @app_commands.command()
    @app_commands.guild_only
    async def stop(self, inter: discord.Interaction):
        """Stops playing any music entirely."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        if not await self.can_run_command(ctx, "stop"):
            return
        await audio.command_stop(ctx)

    @app_commands.command()
    @app_commands.guild_only
    @app_commands.describe(position="Will skip to this track in the queue.")
    async def skip(self, inter: discord.Interaction, position: Optional[app_commands.Range[int, 1, 1000]]):
        """Skips a number of tracks in the music queue."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        if not await self.can_run_command(ctx, "skip"):
            return
        await audio.command_skip(ctx, position)

    @app_commands.command()
    @app_commands.guild_only
    async def queue(self, inter: discord.Interaction):
        """Show what's currently playing."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        if not await self.can_run_command(ctx, "queue"):
            return
        await audio.command_queue(ctx)

    toggle = [app_commands.Choice(name="Enabled", value="1"),
              app_commands.Choice(name="Disabled", value="0")]

    @app_commands.command()
    @app_commands.guild_only
    @app_commands.describe(volume="New volume value between 1 and 150.")
    async def volume(self, inter: discord.Interaction, volume: app_commands.Range[int, 1, 150]):
        """Sets the music volume in voicechat."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        if not await self.can_run_command(ctx, "volume"):
            return
        await audio.command_volume(ctx, volume)

    @app_commands.command()
    @app_commands.guild_only
    @app_commands.describe(toggle="Enable or disable track shuffling.")
    @app_commands.choices(toggle=toggle)
    async def shuffle(self, inter: discord.Interaction, toggle: str):
        """Sets whether the playlist should be shuffled."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        value = bool(int(toggle))
        if value != await audio.config.guild(ctx.guild).shuffle():
            if not await self.can_run_command(ctx, "shuffle"):
                return
            await audio.command_shuffle(ctx)
        else:
            embed = discord.Embed(title="Setting Unchanged", description="Shuffle tracks: " + ("Enabled" if value else "Disabled"))
            await audio.send_embed_msg(ctx, embed=embed)

    @app_commands.command()
    @app_commands.guild_only
    @app_commands.describe(toggle="Enable or disable track repeating.")
    @app_commands.choices(toggle=toggle)
    async def repeat(self, inter: discord.Interaction, toggle: str):
        """Sets whether the playlist should repeat."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        value = bool(int(toggle))
        if value != await audio.config.guild(ctx.guild).repeat():
            if not await self.can_run_command(ctx, "repeat"):
                return
            await audio.command_repeat(ctx)
        else:
            embed = discord.Embed(title="Setting Unchanged", description="Repeat tracks: " + ("Enabled" if value else "Disabled"))
            await audio.send_embed_msg(ctx, embed=embed)

    playlist = app_commands.Group(name="playlist", description="Playlist commands", guild_only=True)

    playlist_scopes = [app_commands.Choice(name="Personal", value="USERPLAYLIST"),
                       app_commands.Choice(name="Server", value="GUILDPLAYLIST"),
                       app_commands.Choice(name="Global", value="GLOBALPLAYLIST")]

    @staticmethod
    def get_scope_data(scope: str, ctx: commands.Context) -> ScopeParser:
        return [scope, ctx.author, ctx.guild, False]  # noqa

    @playlist.command(name="play")
    @app_commands.describe(playlist="The name of the playlist.",
                           shuffle="Whether to shuffle the playlist before sending it.")
    async def playlist_play(self, inter: discord.Interaction, playlist: str, shuffle: Optional[bool]):
        """Starts an existing playlist in voicechat."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        match = await PlaylistConverter().convert(ctx, playlist)
        enabled = False
        if shuffle is not None and shuffle != await audio.config.guild(ctx.guild).shuffle():
            dj_enabled = audio._dj_status_cache.setdefault(ctx.guild.id, await audio.config.guild(ctx.guild).dj_enabled())
            can_skip = await audio._can_instaskip(ctx, ctx.author)
            if not dj_enabled or can_skip and await self.can_run_command(ctx, "shuffle"):
                await audio.config.guild(ctx.guild).shuffle.set(shuffle)
                enabled = shuffle
        if not await self.can_run_command(ctx, "playlist play"):
            return
        await audio.command_playlist_start(ctx, match)
        if enabled:
            await audio.config.guild(ctx.guild).shuffle.set(False)

    @playlist.command(name="create")
    @app_commands.describe(name="The name of the new playlist. Cannot contain spaces.",
                           make_from_queue="This will fill the playlist with the current queue.",
                           scope="Who this playlist will belong to. You need permissions for Server and Global.")
    @app_commands.choices(scope=playlist_scopes)
    async def playlist_create(self, inter: discord.Interaction, name: str, make_from_queue: Optional[bool], scope: Optional[str]):
        """Creates a new playlist."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        name = name.replace(" ", "-")
        ctx = await self.get_context(inter, audio)
        if make_from_queue:
            if not await self.can_run_command(ctx, "playlist queue"):
                return
            await audio.command_playlist_queue(ctx, name, scope_data=self.get_scope_data(scope, ctx))
        else:
            if not await self.can_run_command(ctx, "playlist create"):
                return
            await audio.command_playlist_create(ctx, name, scope_data=self.get_scope_data(scope, ctx))

    @playlist.command(name="add")
    @app_commands.describe(playlist="The name of the playlist.",
                           track="The track to add to the playlist.",
                           scope="You may specify who this playlist belongs to.")
    @app_commands.choices(scope=playlist_scopes)
    async def playlist_add(self, inter: discord.Interaction, playlist: str, track: str, scope: Optional[str]):
        """Adds a track to an existing playlist."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        match = await PlaylistConverter().convert(ctx, playlist)
        if not await self.can_run_command(ctx, "playlist append"):
            return
        await audio.command_playlist_append(ctx, match, track, scope_data=self.get_scope_data(scope, ctx))

    @playlist.command(name="remove")
    @app_commands.describe(playlist="The name of the playlist.",
                           track="The link to the track to remove from the playlist.",
                           scope="You may specify who this playlist belongs to.")
    @app_commands.choices(scope=playlist_scopes)
    async def playlist_remove(self, inter: discord.Interaction, playlist: str, track: str, scope: Optional[str]):
        """Removes a track from an existing playlist."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        match = await PlaylistConverter().convert(ctx, playlist)
        if not await self.can_run_command(ctx, "playlist remove"):
            return
        await audio.command_playlist_remove(ctx, match, track, scope_data=self.get_scope_data(scope, ctx))

    @playlist.command(name="info")
    @app_commands.describe(playlist="The name of the playlist to show.",
                           scope="You may specify who this playlist belongs to.")
    @app_commands.choices(scope=playlist_scopes)
    async def playlist_info(self, inter: discord.Interaction, playlist: str, scope: Optional[str]):
        """Show information about a playlist."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        match = await PlaylistConverter().convert(ctx, playlist)
        if not await self.can_run_command(ctx, "playlist info"):
            return
        await audio.command_playlist_info(ctx, match, scope_data=self.get_scope_data(scope, ctx))

    @playlist.command(name="delete")
    @app_commands.describe(playlist="The name of the playlist to delete.",
                           scope="You may specify who this playlist belongs to.")
    @app_commands.choices(scope=playlist_scopes)
    async def playlist_delete(self, inter: discord.Interaction, playlist: str, scope: Optional[str]):
        """Deletes a playlist entirely."""
        if not (audio := await self.get_audio_cog(inter)):
            return
        ctx = await self.get_context(inter, audio)
        match = await PlaylistConverter().convert(ctx, playlist)
        if not await self.can_run_command(ctx, "playlist delete"):
            return
        await audio.command_playlist_delete(ctx, match, scope_data=self.get_scope_data(scope, ctx))

    @staticmethod
    def format_youtube(res: dict) -> str:
        name = f"({res['duration']}) {res['title']}"
        author = f" — {res['channel']['name']}"
        if len(name) + len(author) > 100:
            return name[:97 - len(author)] + "..." + author
        else:
            return name + author

    @play.autocomplete("search")
    @playlist_add.autocomplete("track")
    async def youtube_autocomplete(self, _: discord.Interaction, current: str):
        try:
            if not current:
                return []
            search = VideosSearch(current, limit=20)
            results = await search.next()
            return [app_commands.Choice(name=self.format_youtube(res), value=res["link"]) for res in results["result"]]
        except:
            log.exception("Retrieving youtube results")

    @playlist_play.autocomplete("playlist")
    @playlist_add.autocomplete("playlist")
    @playlist_remove.autocomplete("playlist")
    @playlist_info.autocomplete("playlist")
    @playlist_delete.autocomplete("playlist")
    async def playlist_autocomplete(self, inter: discord.Interaction, current: str):
        audio: Optional[Audio] = self.bot.get_cog("Audio")
        if not audio or not audio.playlist_api:
            return []
        try:
            global_matches = await get_all_playlist(
                PlaylistScope.GLOBAL.value, self.bot, audio.playlist_api, inter.guild, inter.user
            )
            guild_matches = await get_all_playlist(
                PlaylistScope.GUILD.value, self.bot, audio.playlist_api, inter.guild, inter.user
            )
            user_matches = await get_all_playlist(
                PlaylistScope.USER.value, self.bot, audio.playlist_api, inter.guild, inter.user
            )
            playlists = [*user_matches, *guild_matches, *global_matches]
            if current:
                results = [pl.name for pl in playlists if pl.name.lower().startswith(current.lower())]
                results += [pl.name for pl in playlists if current.lower() in pl.name.lower() and not pl.name.lower().startswith(current.lower())]
            else:
                results = [pl.name for pl in playlists]
            return [app_commands.Choice(name=pl, value=pl) for pl in results][:25]
        except:
            log.exception("Retrieving playlists")
