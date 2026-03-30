import re
import discord
from typing import Optional
from redbot.core import commands

from imagescanner.base import ImageScannerBase


class ImageScannerCommands(ImageScannerBase):

    @commands.group(invoke_without_command=True)  # type: ignore
    @commands.is_owner()
    async def scanset(self, ctx: commands.Context):
        """Owner command to manage image scanner settings."""
        await ctx.send_help()

    @scanset.command(name="maxsize")
    async def scanset_maxsize(self, ctx: commands.Context, newlimit: Optional[int]):
        """Views or set the filesize limit for scanned images in MB."""
        if not newlimit or newlimit < 0 or newlimit > 1024:
            await ctx.reply(f"The current image scan limit is {self.scan_limit // 1024**2} MB.")
            return
        self.scan_limit = newlimit * 1024**2
        await self.config.scan_limit.set(self.scan_limit)
        await ctx.tick(message="Max size set")

    @scanset.group(name="channel", invoke_without_command=True)
    async def scanset_channel(self, ctx: commands.Context):
        """Owner command to manage channels where images are scanned."""
        await ctx.send_help()

    @scanset_channel.command(name="add")
    async def scanset_channel_add(self, ctx: commands.Context, *, channels: str):
        """Add a list of channels by ID to the scan list."""
        channel_ids = [int(ch) for ch in re.findall(r"(\d+)", channels)]
        if not channel_ids:
            return await ctx.reply("Please enter one or more valid channels.")
        self.scan_channels.update(ch for ch in channel_ids)
        await self.config.channels.set(list(self.scan_channels))
        await ctx.tick(message="Channel(s) added")

    @scanset_channel.command(name="remove")
    async def scanset_channel_remove(self, ctx: commands.Context, *, channels: str):
        """Remove a list of channels from the scan list."""
        channel_ids = [int(ch) for ch in re.findall(r"(\d+)", channels)]
        if not channel_ids:
            return await ctx.reply("Please enter one or more valid channels.")
        self.scan_channels.difference_update(ch for ch in channel_ids)
        await self.config.channels.set(list(self.scan_channels))
        await ctx.tick(message="Channel(s) removed")

    @scanset_channel.command(name="list")
    async def scanset_channel_list(self, ctx: commands.Context):
        """Show all channels in the scan list."""
        await ctx.reply('\n'.join([f'<#{cid}>' for cid in self.scan_channels]) or "*None*")

    @scanset.command(name="attachimages")
    async def scanset_attachimages(self, ctx: commands.Context):
        """Toggles whether images sent in DMs will be attached or linked."""
        self.attach_images = not self.attach_images
        await self.config.attach_images.set(self.attach_images)
        if self.attach_images:
            await ctx.reply("Images sent in DMs will now be attached as a file and embedded in full size.")
        else:
            await ctx.reply("Images sent in DMs will now be added as a link and embedded as a thumbnail.")

    @scanset.command(name="civitai")
    async def scanset_civitai(self, ctx: commands.Context):
        """Toggles whether images should look for models on Civitai."""
        self.use_civitai = not self.use_civitai
        await self.config.use_civitai.set(self.use_civitai)
        if self.use_civitai:
            await ctx.reply("Images sent in DMs will now try to find models on Civitai.")
        else:
            await ctx.reply("Images sent in DMs will no longer search for models on Civitai.")

    @scanset.command(name="arcenciel")
    async def scanset_arcenciel(self, ctx: commands.Context):
        """Toggles whether images should look for models on Arc en Ciel."""
        self.use_arcenciel = not self.use_arcenciel
        await self.config.use_arcenciel.set(self.use_arcenciel)
        if self.use_arcenciel:
            await ctx.reply("Images sent in DMs will now try to find models on Arc en Ciel.")
        else:
            await ctx.reply("Images sent in DMs will no longer search for models on Arc en Ciel.")

    @scanset.command(name="civitaiemoji")
    async def scanset_civitaiemoji(self, ctx: commands.Context, emoji: Optional[discord.Emoji]):
        """Add your own Civitai custom emoji with this command."""
        if emoji is None:
            self.civitai_emoji = ""
            await self.config.civitai_emoji.set("")
            await ctx.reply("No emoji will appear when Civitai links are shown to users, only the word \"Civitai\".")
            return
        try:
            await ctx.react_quietly(emoji)
        except (discord.NotFound, discord.Forbidden):
            await ctx.reply("I don't have access to that emoji. I must be in the same server to use it.")
        else:
            self.civitai_emoji = str(emoji)
            await self.config.civitai_emoji.set(str(emoji))
            await ctx.reply(f"{emoji} will now appear when Civitai links are shown to users.")

    @scanset.command(name="arcencielemoji")
    async def scanset_arcencielemoji(self, ctx: commands.Context, emoji: Optional[discord.Emoji]):
        """Add your own arcenciel custom emoji with this command."""
        if emoji is None:
            self.arcenciel_emoji = ""
            await self.config.arcenciel_emoji.set("")
            await ctx.reply("No emoji will appear when arcenciel links are shown to users, only \"Arc en Ciel\".")
            return
        try:
            await ctx.react_quietly(emoji)
        except (discord.NotFound, discord.Forbidden):
            await ctx.reply("I don't have access to that emoji. I must be in the same server to use it.")
        else:
            self.arcenciel_emoji = str(emoji)
            await self.config.arcenciel_emoji.set(str(emoji))
            await ctx.reply(f"{emoji} will now appear when arcenciel links are shown to users.")

    @scanset.command(name="cache")
    async def scanset_cache(self, ctx: commands.Context, size: Optional[int]):
        """How many images to cache in memory."""
        if size is None:
            size = await self.config.image_cache_size()
            await ctx.reply(f"Up to {size} recent images will be cached in memory to prevent duplicate downloads. "
                            "Images are removed from cache after 24 hours.")
        elif size < 0 or size > 1000:
            await ctx.reply("Please choose a value between 0 and 1000, or none to see the current value.")
        else:
            await self.config.image_cache_size.set(size)
            await ctx.reply(f"Up to {size} recent images will be cached in memory to prevent duplicate downloads. "
                            "Images are removed from cache after 24 hours."
                            "\nRequires a cog reload to apply the new value, which will clear the cache.")
            
    @scanset.command(name="scangenerated")
    async def scanset_scangenerated(self, ctx: commands.Context):
        """Toggles always scanning images generated by the bot itself, regardless of channel whitelisting in ImageScanner."""
        always_scan_generated_images = not await self.config.always_scan_generated_images()
        await self.config.always_scan_generated_images.set(always_scan_generated_images)
        if always_scan_generated_images:
            await ctx.reply("Scanning of images generated by the bot always enabled.")
        else:
            await ctx.reply("Scanning of images generated by the bot enabled only for ImageScanner whistelisted channels.")
