import io
import os
import gzip
import asyncio
import discord
from discord import Intents, Message, Member, Embed
from redbot.core import commands, Config
from collections import OrderedDict
from PIL import Image

SCAN_LIMIT_BYTES = 20 * 1024**2

class PromptInspector(commands.Cog):
    """Scans images for AI generation info."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.scan_channels = set()
        self.config = Config.get_conf(self, identifier=7072707469)
        self.config.register_global(channels=[])

    async def load_config(self):
        self.scan_channels = set(await self.config.channels())

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    # Static methods

    @staticmethod
    def read_info_from_image_stealth(image):
        # trying to read stealth pnginfo
        width, height = image.size
        pixels = image.load()

        has_alpha = True if image.mode == 'RGBA' else False
        mode = None
        compressed = False
        binary_data = ''
        buffer_a = ''
        buffer_rgb = ''
        index_a = 0
        index_rgb = 0
        sig_confirmed = False
        confirming_signature = True
        reading_param_len = False
        reading_param = False
        read_end = False
        for x in range(width):
            for y in range(height):
                if has_alpha:
                    r, g, b, a = pixels[x, y]
                    buffer_a += str(a & 1)
                    index_a += 1
                else:
                    r, g, b = pixels[x, y]
                buffer_rgb += str(r & 1)
                buffer_rgb += str(g & 1)
                buffer_rgb += str(b & 1)
                index_rgb += 3
                if confirming_signature:
                    if index_a == len('stealth_pnginfo') * 8:
                        decoded_sig = bytearray(int(buffer_a[i:i + 8], 2) for i in
                                                range(0, len(buffer_a), 8)).decode('utf-8', errors='ignore')
                        if decoded_sig in {'stealth_pnginfo', 'stealth_pngcomp'}:
                            confirming_signature = False
                            sig_confirmed = True
                            reading_param_len = True
                            mode = 'alpha'
                            if decoded_sig == 'stealth_pngcomp':
                                compressed = True
                            buffer_a = ''
                            index_a = 0
                        else:
                            read_end = True
                            break
                    elif index_rgb == len('stealth_pnginfo') * 8:
                        decoded_sig = bytearray(int(buffer_rgb[i:i + 8], 2) for i in
                                                range(0, len(buffer_rgb), 8)).decode('utf-8', errors='ignore')
                        if decoded_sig in {'stealth_rgbinfo', 'stealth_rgbcomp'}:
                            confirming_signature = False
                            sig_confirmed = True
                            reading_param_len = True
                            mode = 'rgb'
                            if decoded_sig == 'stealth_rgbcomp':
                                compressed = True
                            buffer_rgb = ''
                            index_rgb = 0
                elif reading_param_len:
                    if mode == 'alpha':
                        if index_a == 32:
                            param_len = int(buffer_a, 2)
                            reading_param_len = False
                            reading_param = True
                            buffer_a = ''
                            index_a = 0
                    else:
                        if index_rgb == 33:
                            pop = buffer_rgb[-1]
                            buffer_rgb = buffer_rgb[:-1]
                            param_len = int(buffer_rgb, 2)
                            reading_param_len = False
                            reading_param = True
                            buffer_rgb = pop
                            index_rgb = 1
                elif reading_param:
                    if mode == 'alpha':
                        if index_a == param_len:
                            binary_data = buffer_a
                            read_end = True
                            break
                    else:
                        if index_rgb >= param_len:
                            diff = param_len - index_rgb
                            if diff < 0:
                                buffer_rgb = buffer_rgb[:diff]
                            binary_data = buffer_rgb
                            read_end = True
                            break
                else:
                    # impossible
                    read_end = True
                    break
            if read_end:
                break
        if sig_confirmed and binary_data != '':
            # Convert binary string to UTF-8 encoded text
            byte_data = bytearray(int(binary_data[i:i + 8], 2) for i in range(0, len(binary_data), 8))
            try:
                if compressed:
                    decoded_data = gzip.decompress(bytes(byte_data)).decode('utf-8')
                else:
                    decoded_data = byte_data.decode('utf-8', errors='ignore')
                return decoded_data
            except:
                pass
        return None

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
    def get_embed(embed_dict: dict, author: Member):
        embed = Embed(title="Here's your image!", color=author.color)
        for key, value in embed_dict.items():
            embed.add_field(name=key, value=value, inline='Prompt' not in key)
        pfp = author.avatar if author.avatar else author.default_avatar_url
        embed.set_footer(text=f'Posted by {author.name}#{author.discriminator}', icon_url=pfp)
        return embed

    @staticmethod
    async def read_attachment_metadata(i: int, attachment: discord.Attachment, metadata: OrderedDict):
        try:
            image_data = await attachment.read()
            with Image.open(io.BytesIO(image_data)) as img:
                try:
                    info = img.info['parameters']
                except:
                    info = PromptInspector.read_info_from_image_stealth(img)
                if info and "Steps" in info:
                    metadata[i] = info
        except Exception as error:
            print(f"{type(error).__name__}: {error}")
        else:
            print("Downloaded", i)

    # Events

    @commands.event
    async def on_message(self, message: Message):
        # Scan images in allowed channels
        if message.channel.id in self.scan_channels:
            attachments = [a for a in message.attachments if a.filename.lower().endswith(".png") and a.size < SCAN_LIMIT_BYTES]
            for i, attachment in enumerate(attachments): # Scan one at a time as usually the first image in a post is AI-generated
                metadata = OrderedDict()
                await self.read_attachment_metadata(i, attachment, metadata)
                if metadata:
                    await message.add_reaction('🔎')
                    return


    @commands.event
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
        user_dm = await self.bot.get_user(ctx.user_id).create_dm()
        if not metadata:
            embed = self.get_embed({}, message.author)
            embed.description = f"This post contains no image generation data.\nTell {message.author.mention} to install [this extension](<https://github.com/ashen-sensored/sd_webui_stealth_pnginfo>)."
            embed.set_thumbnail(url=attachments[0].url)
            await user_dm.send(embed=embed)
            return
        for attachment, data in [(attachments[i], data) for i, data in metadata.items()]:
            embed = self.get_embed(self.get_params_from_string(data), message.author)
            embed.set_thumbnail(url=attachment.url)
            await user_dm.send(embed=embed)

    # Commands

    @commands.command(hidden=True)
    async def viewparameters(self, ctx: discord.ApplicationContext, msg: str):
        """Get raw list of parameters for every image in this post."""
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

    @commands.group(invoke_without_command=True)
    @commands.is_owner()
    async def piset(self, ctx: commands.Context):
        """Owner command to manage channels where images are scanned."""
        await ctx.send_help()

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
        await ctx.reply('✅')

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
        await ctx.reply('✅')

    @channel.command()
    async def list(self, ctx: commands.Context):
        """Show all channels in the scan list."""
        await ctx.reply('\n'.join([f'<#{id}>' for id in self.scan_channels]) or "*None*")
