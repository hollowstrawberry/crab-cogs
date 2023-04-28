import io
import asyncio
import discord
from redbot.core import commands, app_commands, Config
from typing import Optional
from collections import OrderedDict
from PIL import Image
from .stealth import read_info_from_image_stealth

class PromptInspector(commands.Cog):
    """Scans images for AI generation info."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.scan_channels = set()
        self.scan_limit = 10 * 1024**2
        self.config = Config.get_conf(self, identifier=7072707469)
        self.config.register_global(channels=[], scanlimit=self.scan_limit)
        self.context_menu = app_commands.ContextMenu(name='View Parameters', callback=self.viewparameters)
        self.bot.tree.add_command(self.context_menu)

    async def load_config(self):
        self.scan_channels = set(await self.config.channels())

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.context_menu.name, type=self.context_menu.type)

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    # Static methods

    @staticmethod
    def get_params_from_string(param_str):
        output_dict = {}
        parts = param_str.split('Steps: ')
        prompts = parts[0]
        params = 'Steps: ' + parts[1]
        if 'Negative prompt: ' in prompts:
            output_dict['Prompt'] = prompts.split('Negative prompt: ')[0]
            output_dict['Negative Prompt'] = prompts.split('Negative prompt: ')[1]
            if len(output_dict['Negative Prompt']) > 1000:
                output_dict['Negative Prompt'] = output_dict['Negative Prompt'][:1000] + '...'
        else:
            output_dict['Prompt'] = prompts
        if len(output_dict['Prompt']) > 1000:
            output_dict['Prompt'] = output_dict['Prompt'][:1000] + '...'
        params = params.split(', ')
        for param in params:
            try:
                key, value = param.split(': ')
                output_dict[key] = value
            except ValueError:
                pass
        return output_dict

    @staticmethod
    def get_embed(embed_dict: dict, author: discord.Member):
        embed = discord.Embed(title="Here's your image!", color=author.color)
        for key, value in embed_dict.items():
            embed.add_field(name=key, value=value, inline='Prompt' not in key)
        embed.set_footer(text=f'Posted by {author}', icon_url=author.display_avatar.url)
        return embed

    @staticmethod
    async def read_attachment_metadata(i: int, attachment: discord.Attachment, metadata: OrderedDict):
        try:
            image_data = await attachment.read()
            with Image.open(io.BytesIO(image_data)) as img:
                try:
                    info = img.info['parameters']
                except:
                    info = read_info_from_image_stealth(img)
                if info and "Steps" in info:
                    metadata[i] = info
        except Exception as error:
            print(f"{type(error).__name__}: {error}")
        else:
            print("Downloaded", i)

    # Events

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Scan images in allowed channels
        if not message.guild or message.author.bot:
            return
        channel_perms = message.channel.permissions_for(message.guild.me)
        if not channel_perms.add_reactions:
            return
        if message.channel.id not in self.scan_channels:
            return
        attachments = [a for a in message.attachments if a.filename.lower().endswith(".png") and a.size < self.scan_limit]
        if not attachments:
            return
        if not await self.is_valid_red_message(message):
            return
        for i, attachment in enumerate(attachments):  # Scan one at a time as usually the first image in a post is AI-generated
            metadata = OrderedDict()
            await self.read_attachment_metadata(i, attachment, metadata)
            if metadata:
                await message.add_reaction('🔎')
                return
                
    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return await self.bot.allowed_by_whitelist_blacklist(message.author) \
               and await self.bot.ignored_channel_or_guild(message) \
               and not await self.bot.cog_disabled_in_guild(self, message.guild)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, ctx: discord.RawReactionActionEvent):
        """Send image metadata in reacted post to user DMs"""
        if ctx.emoji.name != '🔎' or ctx.channel_id not in self.scan_channels or ctx.member.bot:
            return
        channel = self.bot.get_channel(ctx.channel_id)
        message = await channel.fetch_message(ctx.message_id)
        if not message:
            return
        attachments = [a for a in message.attachments if a.filename.lower().endswith(".png")]
        if not attachments:
            return
        metadata = OrderedDict()
        tasks = [self.read_attachment_metadata(i, attachment, metadata) for i, attachment in enumerate(attachments)]
        await asyncio.gather(*tasks)
        if not metadata:
            embed = self.get_embed({}, message.author)
            embed.description = f"This post contains no image generation data."
            embed.set_thumbnail(url=attachments[0].url)
            await ctx.member.send(embed=embed)
            return
        for attachment, data in [(attachments[i], data) for i, data in metadata.items()]:
            embed = self.get_embed(self.get_params_from_string(data), message.author)
            embed.set_thumbnail(url=attachment.url)
            await ctx.member.send(embed=embed)

    async def viewparameters(self, ctx: commands.Context, *, msg: str):
        """Get raw list of parameters for every image in this post. Meant to be used as a message command with slashtags."""
        msg_id = int(msg.split(' ')[1].split('=')[1])
        message = await ctx.channel.fetch_message(msg_id)
        attachments = [a for a in message.attachments if a.filename.lower().endswith(".png")]
        if not attachments:
            await ctx.reply("This post contains no images.")
            return
        # await ctx.defer(ephemeral=True)
        metadata = OrderedDict()
        tasks = [self.read_attachment_metadata(i, attachment, metadata) for i, attachment in enumerate(attachments)]
        await asyncio.gather(*tasks)
        if not metadata:
            await ctx.reply(f"This post contains no image generation data.")
            return
        response = "\n\n".join(metadata.values())
        if len(response) < 1980:
            await ctx.reply(f"```yaml\n{response}```")
        else:
            with io.StringIO() as f:
                f.write(response)
                f.seek(0)
                await ctx.reply(file=discord.File(f, "parameters.yaml"))

    # Config commands

    @commands.group(invoke_without_command=True)
    @commands.is_owner()
    async def piset(self, ctx: commands.Context):
        """Owner command to manage prompt inspector settings."""
        await ctx.send_help()

    @piset.command(invoke_without_command=True)
    async def scanlimit(self, ctx: commands.Context, newlimit: Optional[int]):
        """Views or set the filesize limit for scanned images in MB."""
        if not newlimit or newlimit < 0 or newlimit > 1024:
            await ctx.reply(f"The current prompt inspector scan limit is {self.scan_limit // 1024**2} MB.")
            return
        self.scan_limit = newlimit * 1024**2
        await self.config.scan_limit.set(self.scan_limit)
        await ctx.react_quietly("✅")

    @piset.group(invoke_without_command=True)
    async def channel(self, ctx: commands.Context):
        """Owner command to manage channels where images are scanned."""
        await ctx.send_help()

    @channel.command()
    async def add(self, ctx: commands.Context, *, channels: str):
        """Add a list of channels by ID to the scan list."""
        try:
            channel_ids = [int(s.strip()) for s in channels.split(' ') if s.strip()]
        except:
            await ctx.reply("Please enter valid numbers as channel IDs")
            return
        self.scan_channels.update(ch for ch in channel_ids)
        await self.config.channels.set(list(self.scan_channels))
        await ctx.react_quietly("✅")

    @channel.command()
    async def remove(self, ctx: commands.Context, *, channels: str):
        """Remove a list of channels by ID from the scan list."""
        try:
            channel_ids = [int(s.strip()) for s in channels.split(' ') if s.strip()]
        except:
            await ctx.reply("Please enter valid numbers as channel IDs")
            return
        self.scan_channels.difference_update(ch for ch in channel_ids)
        await self.config.channels.set(list(self.scan_channels))
        await ctx.react_quietly("✅")

    @channel.command()
    async def list(self, ctx: commands.Context):
        """Show all channels in the scan list."""
        await ctx.reply('\n'.join([f'<#{id}>' for id in self.scan_channels]) or "*None*")
