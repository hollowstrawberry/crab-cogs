import os
import shutil
import logging
import asyncio
import lavalink
from gtts import gTTS
from copy import deepcopy
from typing import Optional
from googletrans import Translator
from discord.ext import tasks
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.commands import Cog
from redbot.cogs.audio.core import Audio

log = logging.getLogger("red.crab-cogs.tts")


class TextToSpeech(Cog):
    """Plays text to speech in voice chat. Overrides music."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.tts_storage = cog_data_path(cog_instance=self).joinpath("tts")
        self.translator = Translator()
        self.clear_old_tts.start()

    async def red_delete_data_for_user(self, *args, **kwargs):
        """Nothing to delete"""
        pass

    @tasks.loop(hours=1)
    async def clear_old_tts(self):
        try:
            if os.path.exists(self.tts_storage):
                shutil.rmtree(self.tts_storage)
        except OSError:
            log.exception("Trying to clear old TTS audio files")

    async def cog_unload(self):
        self.clear_old_tts.stop()


    @commands.hybrid_command()
    @commands.guild_only()
    async def tts(self, ctx: commands.Context, *, text: str):
        """Speak in voice chat. Overrides music. Detects the language."""
        assert ctx.guild

        audio: Optional[Audio] = self.bot.get_cog("Audio")  # type: ignore
        if audio is None:
            return await ctx.send("Audio cog is not loaded!")
        if not ctx.guild.me.voice:
            if await ctx.invoke(audio.command_summon):
                return  # failed to join voicechat

        try:
            result = await asyncio.to_thread(self.translator.detect, text)
            tts = gTTS(text, lang=result.lang)
        except Exception as error:
            if not isinstance(error, ValueError):
                log.exception("Trying to detect language")
            tts = gTTS(text)

        self.tts_storage.mkdir(parents=True, exist_ok=True)
        audio_path = str(self.tts_storage.joinpath(f"{ctx.message.id}.mp3"))

        try:
            await asyncio.to_thread(tts.save, audio_path)
        except OSError:
            log.exception("Trying to save TTS audio")
            return ctx.send("There was an error saving the voice message. Check the logs for more details.")

        player = lavalink.get_player(ctx.guild.id)
        player.store("channel", ctx.channel.id)
        load_result = await player.load_tracks(audio_path)
        if load_result.has_error or load_result.load_type != lavalink.enums.LoadType.TRACK_LOADED:
            await ctx.send("There was an error playing the voice message. Check the logs for more details.")
            log.error(f"Failed to load the TTS track: {load_result._raw}")
            return

        if player and player.current:
            old_track = player.current
            old_track.start_timestamp = old_track.position
            player.queue.insert(0, old_track)
        new_track = load_result.tracks[0]
        new_track.requester = ctx.author  # type: ignore
        player.queue.insert(0, new_track)
        await player.play()

        if ctx.interaction:
            await ctx.reply("🗣 Playing speech...")
        else:
            await ctx.react_quietly("🗣")
