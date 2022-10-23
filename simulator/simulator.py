import discord
import asyncio
import random
import re
import os
import sys
import logging
import enum
import json
import aiosqlite as sql
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from typing import *

log = logging.getLogger("red.crab-cogs.simulator")

WEBHOOK_NAME = "Simulator"
DB_FILE = "messages.db"
DB_TABLE_MESSAGES = "messages"
COMMIT_SIZE = 1000

CHAIN_END = "🔚"
TOKENIZER = re.compile(
    r"( ?https?://[^\s>]+"                # URLs
    r"| ?<(@|#|@!|@&|a?:\w+:)\d{10,20}>"  # mentions, emojis
    r"| ?@everyone| ?@here"               # pings
    r"| ?[\w'-]+"                         # words
    r"|[^\w<]+|<)"                        # symbols
)
SUBTOKENIZER = re.compile(
    r"( ?https?://(?=[^\s>])|(?<=://)[^\s>]+"         # URLs
    r"| ?<a?:(?=\w)|(?<=:)\w+:\d{10,20}>"             # emojis
    r"| ?<[@#](?=[\d&!])|(?<=[@#])[!&]?\d{10,20}>)"   # mentions
)

COMMENT_DELAY = 5
CONVERSATION_DELAY = 30
CONVERSATION_MIN = 4
CONVERSATION_MAX = 15

EMOJI_LOADING = '⌛'
EMOJI_SUCCESS = '✅'

ERROR_CONFIG = "You must configure the simulator input role, input channels and output channel. They must be in the same guild."
ERROR_SETUP = "Failed to set up the simulator. Make sure it is configured correctly and check your logs for errors."
ERROR_FEEDING = "The simulator is currently feeding on past messages. Please wait a few minutes."
ERROR_BOOTING = "The simulator is booting up. Wait a minute for it to finish."
ERROR_CHANNELS = "A channel cannot be simulator input and output at the same time."


def getsize(obj_0):
    """Recursively iterate to sum size of object & members.
    https://stackoverflow.com/a/30316760"""
    _seen_ids = set()
    def inner(obj):
        obj_id = id(obj)
        if obj_id in _seen_ids:
            return 0
        _seen_ids.add(obj_id)
        size = sys.getsizeof(obj)
        if isinstance(obj, (str, bytes, int, float, range, bytearray)):
            pass  # bypass remaining control flow and return
        elif isinstance(obj, (tuple, list, Set, Deque)):
            size += sum(inner(i) for i in obj)
        elif isinstance(obj, Mapping) or hasattr(obj, 'items'):
            size += sum(inner(k) + inner(v) for k, v in getattr(obj, 'items')())
        # Check for custom object instances - may subclass above too
        if hasattr(obj, '__dict__'):
            size += inner(vars(obj))
        if hasattr(obj, '__slots__'):  # can have __slots__ with __dict__
            size += sum(inner(getattr(obj, s)) for s in obj.__slots__ if hasattr(obj, s))
        return size
    return inner(obj_0)


@dataclass
class UserModel:
    user_id: int
    frequency: int
    model: dict


class Stage(enum.Enum):
    NONE = enum.auto()
    SETTING_UP = enum.auto()
    READY = enum.auto()


class Simulator(commands.Cog):
    """Designates a channel that will send automated messages mimicking your friends using Markov chains. They will have your friends' avatars and nicknames too!
    Please use the `[p]simulator info` command for more information.
    """

    def __init__(self, bot: Red):
        super().__init__()
        # Define variables
        self.bot = bot
        self.guild: Optional[discord.Guild] = None
        self.input_channels: List[discord.TextChannel] = []
        self.output_channel: Optional[discord.TextChannel] = None
        self.role: Optional[discord.Role] = None
        self.webhook: Optional[discord.Webhook] = None
        self.blacklisted_users: List[int] = []
        self.models: Dict[int, UserModel] = {}
        self.comment_chance = 1 / COMMENT_DELAY
        self.conversation_chance = 1 / CONVERSATION_DELAY
        self.stage = Stage.NONE
        self.feeding_task: Optional[asyncio.Task] = None
        self.message_count = 0
        self.seconds = 0
        self.conversation_left = 0
        # Config
        self.config = Config.get_conf(self, identifier=7369756174)
        default_config = {
            "home_guild_id": 0,
            "input_channel_ids": [0],
            "output_channel_id": 0,
            "participant_role_id": 0,
            "blacklisted_users": [],
            "comment_delay": COMMENT_DELAY,
            "conversation_delay": CONVERSATION_DELAY,
        }
        self.config.register_global(**default_config)
        # Start simulator if possible
        self.simulator_loop.start()

    def cog_unload(self):
        self.simulator_loop.stop()
        if self.feeding_task and not self.feeding_task.done():
            self.feeding_task.cancel()

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        self.models.pop(user_id, None)
        async with sql.connect(cog_data_path(self).joinpath(DB_FILE)) as db:
            await db.execute(f"DELETE FROM {DB_TABLE_MESSAGES} WHERE user_id = ?", [user_id])
            await db.commit()

    # Commands

    @commands.group(name="simulator", aliases=["sim"], invoke_without_command=True)
    async def simulator(self, ctx: commands.Context):
        """Main simulator command. Use me!"""
        await ctx.send_help()

    @simulator.command(aliases=["help"])
    async def info(self, ctx: commands.Context):
        """How this works"""
        info_json = Path(__file__).parent.absolute() / "info.json"
        with info_json.open(encoding="utf-8") as file:
            document = json.load(file)
            log.info(info_json)
        embed = discord.Embed(title="Simulator", color=await ctx.embed_color())
        embed.description = document["description"]
        usage_warning = re.search(r"(?im)Usage Warning: ([^\n]+)", document["install_msg"])
        if usage_warning:
            embed.add_field(name="⚠ Usage Warning", value=usage_warning.group(1))
        await ctx.send(embed=embed)

    @simulator.command()
    async def stats(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Statistics about the simulator, globally or for a user"""
        if not await self.check_participant(ctx):
            return
        await ctx.trigger_typing()

        def count_nodes(tree: dict) -> int:
            count = 0
            for node in tree.values():
                if isinstance(node, dict):
                    count += count_nodes(node) + 1
                else:
                    count += 1
            return count

        def count_words(tree: dict) -> int:
            count = 0
            for node in tree.values():
                if isinstance(node, dict):
                    count += count_words(node)
                elif isinstance(node, int):
                    count += node
            return count

        if user:
            if user.id not in self.models:
                await ctx.send("No data found for this user.")
                return
            messages = self.models[user.id].frequency
            nodes = count_nodes(self.models[user.id].model)
            words = count_words(self.models[user.id].model)
            modelsize = getsize(self.models[user.id]) / 2 ** 20
            filesize = None
        else:
            messages = self.message_count
            nodes = sum(count_nodes(x.model) for x in self.models.values())
            words = sum(count_words(x.model) for x in self.models.values())
            modelsize = getsize(self.models) / 2 ** 20
            filesize = os.path.getsize(cog_data_path(self).joinpath(DB_FILE)) / 2 ** 20

        embed = discord.Embed(title="Simulator Stats", color=await ctx.embed_color())
        embed.add_field(name="Messages", value=f"{messages:,}", inline=True)
        embed.add_field(name="Nodes", value=f"{nodes:,}", inline=True)
        embed.add_field(name="Words", value=f"{words:,}", inline=True)
        embed.add_field(name="Memory", value=f"{round(modelsize, 2)} MB", inline=True)
        if filesize:
            embed.add_field(name="Database", value=f"{round(filesize, 2)} MB", inline=True)
        await ctx.send(embed=embed)

    @simulator.command()
    async def count(self, ctx: commands.Context, word: str, user: Optional[discord.Member] = None):
        """Count instances of a word, globally or for a user"""
        if not await self.check_participant(ctx):
            return
        sword = ' ' + word
        if user:
            if user.id not in self.models:
                await ctx.send("No data found for this user.")
                return
            occurences = sum(x.get(word, 0) + x.get(sword, 0) for x in self.models[user.id].model.values())
            children = len(self.models[user.id].model.get(word, {}) | self.models[user.id].model.get(sword, {}))
        else:
            occurences = sum(sum(x.get(word, 0) + x.get(sword, 0) for x in m.model.values())
                             for m in self.models.values())
            children = sum(len(m.model.get(word, {}) | m.model.get(sword, {})) for m in self.models.values())
        await ctx.send(f"```yaml\nOccurrences: {occurences:,}\nWords that follow: {children:,}```")

    @simulator.command()
    @commands.is_owner()
    @commands.bot_has_permissions(manage_webhooks=True)
    async def start(self, ctx: commands.Context):
        """Start the simulator in the configured channel."""
        if self.feeding_task and not self.feeding_task.done():
            await ctx.send(ERROR_FEEDING)
            return
        if not self.simulator_loop.is_running():
            if not self.is_configured(await self.config.get_raw()):
                await ctx.send(ERROR_CONFIG)
                return
            if self.stage == Stage.NONE and not await self.setup_simulator():
                await ctx.send(ERROR_SETUP)
                return
            self.simulator_loop.start()
        self.start_conversation()
        await ctx.message.add_reaction(EMOJI_SUCCESS)

    @simulator.command()
    @commands.is_owner()
    async def stop(self, ctx: commands.Context):
        """Stop the simulator."""
        self.simulator_loop.stop()
        await ctx.message.add_reaction(EMOJI_SUCCESS)

    @simulator.command()
    @commands.is_owner()
    async def feed(self, ctx: commands.Context, days: Optional[int] = None):
        """Feed past messages into the simulator from the configured channels from scratch."""
        if self.feeding_task and not self.feeding_task.done():
            self.feeding_task.cancel()
            return
        if self.stage == Stage.NONE and not await self.setup_simulator():
            await ctx.send(ERROR_SETUP)
            return
        if self.stage == Stage.SETTING_UP:
            await ctx.send(ERROR_BOOTING)
            return
        if days is None or days < 0:
            await ctx.send_help()
            return
        await ctx.message.add_reaction(EMOJI_LOADING)
        self.simulator_loop.stop()
        self.message_count = 0
        for user in self.models.values():
            user.model = {}
            user.frequency = 0
        self.feeding_task = asyncio.create_task(self.feeder(ctx, days))
        await ctx.send("```Started feeding. This may take 1 minute per 5000 messages, so be patient!\n"
                       "When the process is finished or interrupted, the summary will be sent in this channel.```")

    @commands.command()
    async def dontsimulateme(self, ctx: commands.Context):
        """Excludes you from your messages being read and analyzed by the simulator."""
        async with self.config.blacklisted_users() as blacklisted_users:
            if ctx.author.id in blacklisted_users:
                blacklisted_users.remove(ctx.author.id)
                if ctx.author.id in self.blacklisted_users: self.blacklisted_users.remove(ctx.author.id)
                await ctx.send("You will now be able to participate in the simulator again.")
            else:
                blacklisted_users.append(ctx.author.id)
                self.blacklisted_users.append(ctx.author.id)
                await self.red_delete_data_for_user(user_id=ctx.author.id, requester="user")
                await ctx.send("All your simulator data has been erased and your messages won't be analyzed anymore.")

    # Settings

    @simulator.group(invoke_without_command=True)
    async def set(self, ctx: commands.Context):
        """Set up your simulator."""
        await ctx.send_help()

    @set.command()
    async def showsettings(self, ctx: commands.Context):
        """Show the current simulator settings"""
        embed = discord.Embed(title="Simulator Settings", color=await ctx.embed_color())
        embed.add_field(name="Input Role", value=self.role.mention if self.role else "None", inline=True)
        embed.add_field(name="Input Channels", value=' '.join(ch.mention if ch else '' for ch in self.input_channels) or "None", inline=True)
        embed.add_field(name="Output Channel", value=self.output_channel.mention if self.output_channel else "None", inline=True)
        embed.add_field(name="Time between conversations", value=f"~{round(1 / self.conversation_chance)} minutes", inline=True)
        embed.add_field(name="Time between comments", value=f"~{round(1 / self.comment_chance)} seconds", inline=True)
        await ctx.send(embed=embed)

    @set.command()
    @commands.is_owner()
    async def inputchannels(self, ctx: commands.Context, *channels: discord.TextChannel):
        """Set a series of channels that will feed the simulator."""
        if self.output_channel and self.output_channel in channels:
            await ctx.send(ERROR_CHANNELS)
            return
        await self.config.home_guild_id.set(ctx.guild.id)
        await self.config.input_channel_ids.set([channel.id for channel in channels])
        self.guild = ctx.guild
        self.input_channels = channels
        await ctx.react_quietly(EMOJI_SUCCESS)

    @set.command()
    @commands.is_owner()
    async def outputchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel the simulator will run in."""
        if channel in self.input_channels:
            await ctx.send(ERROR_CHANNELS)
            return
        await self.config.output_channel_id.set(channel.id)
        self.output_channel = channel
        await ctx.react_quietly(EMOJI_SUCCESS)

    @set.command()
    @commands.is_owner()
    async def inputrole(self, ctx: commands.Context, role: discord.Role):
        """Members must have this role to participate in the simulator."""
        await self.config.participant_role_id.set(role.id)
        self.role = role
        await ctx.react_quietly(EMOJI_SUCCESS)

    @set.command()
    @commands.is_owner()
    async def conversationdelay(self, ctx: commands.Context, minutes: int):
        """Simulated conversations will occur randomly according to this value in minutes."""
        await self.config.conversation_delay.set(max(1, minutes))
        self.conversation_chance = 1 / max(1, minutes)
        await ctx.react_quietly(EMOJI_SUCCESS)

    @set.command()
    @commands.is_owner()
    async def commentdelay(self, ctx: commands.Context, chance: int):
        """Messages will be sent randomly during simulated conversations according to this value in seconds."""
        await self.config.comment_delay.set(max(1, chance))
        self.comment_chance = 1 / max(1, chance)
        await ctx.react_quietly(EMOJI_SUCCESS)

    # Listeners

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Processes new incoming messages"""
        if not self.is_valid_event_message(message):
            return
        if self.is_valid_input_message(message):
            if not await self.is_valid_red_message(message):
                return
            if self.add_message(message=message):
                async with sql.connect(cog_data_path(self).joinpath(DB_FILE)) as db:
                    await self.insert_message_db(message, db)
                    await db.commit()
        elif message.channel == self.output_channel:
            if not await self.is_valid_red_message(message):
                return
            try:
                await message.delete()
            except:
                pass
            if self.role in message.author.roles:
                self.start_conversation()

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Processes deleted messages"""
        if not self.is_valid_event_message(message):
            return
        if not self.is_valid_input_message(message):
            return
        if not await self.is_valid_red_message(message):
            return
        async with sql.connect(cog_data_path(self).joinpath(DB_FILE)) as db:
            await self.delete_message_db(message, db)
            await db.commit()
        self.message_count -= 1

    @commands.Cog.listener()
    async def on_message_edit(self, message: discord.Message, edited: discord.Message):
        """Processes edited messages"""
        if not self.is_valid_event_message(message):
            return
        if not self.is_valid_input_message(message):
            return
        if not await self.is_valid_red_message(message):
            return
        async with sql.connect(cog_data_path(self).joinpath(DB_FILE)) as db:
            await self.delete_message_db(message, db)
            await db.commit()
            if self.add_message(message=edited):
                await self.insert_message_db(edited, db)
                await db.commit()

    # Loop

    @tasks.loop(seconds=1, reconnect=True)
    async def simulator_loop(self):
        if self.conversation_left:
            if random.random() < self.comment_chance:
                try:
                    self.conversation_left -= 1
                    await self.send_generated_message()
                except Exception as error:
                    error_msg = f'{type(error).__name__}: {error}'
                    log.error(error_msg, exc_info=True)
                    try:
                        await self.output_channel.send(error_msg)
                    except:
                        pass
        else:
            self.seconds = (self.seconds + 1) % 60
            if self.seconds == 0 and random.random() < self.conversation_chance:
                self.start_conversation()

    @simulator_loop.before_loop
    async def setup_simulator(self) -> bool:
        self.stage = Stage.SETTING_UP
        try:
            await self.bot.wait_until_red_ready()
            # config
            config_dict = await self.config.get_raw()
            if not self.is_configured(config_dict):
                self.simulator_loop.stop()
                return False
            guild_id = config_dict['home_guild_id']
            input_channel_ids = config_dict['input_channel_ids']
            output_channel_id = config_dict['output_channel_id']
            role_id = config_dict['participant_role_id']
            self.comment_chance = 1 / config_dict['comment_delay']
            self.conversation_chance = 1 / config_dict['conversation_delay']
            # discord entities
            self.guild = self.bot.get_guild(guild_id)
            if self.guild is None: raise KeyError(self.guild.__name__)
            self.role = self.guild.get_role(role_id)
            self.input_channels = [self.guild.get_channel(i) for i in input_channel_ids]
            self.output_channel = self.guild.get_channel(output_channel_id)
            if self.role is None: raise KeyError(self.role.__name__)
            if any(c is None for c in self.input_channels): raise KeyError(self.input_channels.__name__)
            if self.output_channel is None: raise KeyError(self.output_channel.__name__)
            webhooks = await self.output_channel.webhooks()
            webhooks = [w for w in webhooks if w.user == self.bot.user and w.name == WEBHOOK_NAME]
            self.webhook = webhooks[0] if webhooks else await self.output_channel.create_webhook(name=WEBHOOK_NAME)
            # database
            async with sql.connect(cog_data_path(self).joinpath(DB_FILE)) as db:
                await db.execute(f"CREATE TABLE IF NOT EXISTS {DB_TABLE_MESSAGES} "
                                 f"(id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT NOT NULL);")
                await db.commit()
                async with db.execute(f"SELECT * FROM {DB_TABLE_MESSAGES}") as cursor:
                    async for row in cursor:
                        self.add_message(row[1], row[2])
            log.info(f"Simulator model built from {self.message_count} messages")
            self.stage = Stage.READY
            return True
        except Exception as error:
            error_msg = f'Failed to set up the simulator - {type(error).__name__}: {error}'
            log.error(error_msg, exc_info=True)
            self.simulator_loop.stop()
            self.stage = Stage.NONE
            try:
                await self.output_channel.send(error_msg)
            except Exception:
                pass
            return False

    async def feeder(self, ctx: commands.Context, days: int):
        embed = discord.Embed(color=await ctx.embed_color())
        try:
            async with sql.connect(cog_data_path(self).joinpath(DB_FILE)) as db:
                await db.execute(f"DELETE FROM {DB_TABLE_MESSAGES}")
                await db.commit()
                start_date = datetime.now() - timedelta(days=days)
                for channel in self.input_channels:
                    async for message in channel.history(after=start_date, limit=None):
                        if message.author.bot:
                            continue
                        if self.add_message(message=message):
                            await self.insert_message_db(message, db)
                            if self.message_count % COMMIT_SIZE == 0:
                                await db.commit()
                    await db.commit()
        except asyncio.CancelledError:
            self.message_count = self.message_count // COMMIT_SIZE * COMMIT_SIZE
            embed.title = "⚠ Simulator - Stopped"
            embed.description = "Feeding has been interrupted.\n"
        except Exception as error:
            embed.title = "⚠ Simulator - Error"
            embed.description = f"Feeding stopped due to an error.\n"
            embed.add_field(name=type(error).__name__, value=str(error))
            self.message_count = self.message_count // COMMIT_SIZE * COMMIT_SIZE
        else:
            embed.title = f"{EMOJI_SUCCESS} Simulator - Success"
            embed.description = "Feeding has completed and the simulator will start now.\n"
            self.simulator_loop.start()
            self.start_conversation()
        finally:
            embed.add_field(name="🧠 Model Built", value=f"Analyzed {self.message_count} messages")
            await ctx.send(embed=embed)
            try:
                await ctx.message.remove_reaction(EMOJI_LOADING, self.bot.user)
                await ctx.message.add_reaction(EMOJI_SUCCESS)
            except Exception:
                pass

    # Helper Functions

    async def check_participant(self, ctx: commands.Context) -> bool:
        if self.stage == Stage.NONE:
            await ctx.send(f"The simulator is not set up yet. Configure it with `{ctx.prefix}simulator set`")
            return False
        if self.stage == Stage.SETTING_UP:
            await ctx.send(ERROR_BOOTING)
            return False
        if self.feeding_task and not self.feeding_task.done():
            await ctx.send(ERROR_FEEDING)
        if self.guild != ctx.guild:
            await ctx.send(f"The simulator only runs in the {self.guild.name} server.")
            return False
        if self.role not in ctx.author.roles and not ctx.author.guild_permissions.administrator and not self.bot.is_owner(ctx.author):
            await ctx.send(f"You must have the {self.role.name} role to participate in the simulator and view stats.")
            return False
        return True

    @staticmethod
    def is_configured(config: dict) -> bool:
        guild_id = config['home_guild_id']
        input_channel_ids = config['input_channel_ids']
        output_channel_id = config['output_channel_id']
        role_id = config['participant_role_id']
        return guild_id != 0 and output_channel_id != 0 and role_id != 0 and input_channel_ids and 0 not in input_channel_ids

    @staticmethod
    def is_valid_event_message(message: discord.Message) -> bool:
        return message.guild and not message.author.bot and message.type == discord.MessageType.default

    def is_valid_input_message(self, message: discord.Message) -> bool:
        return self.input_channels and message.channel in self.input_channels  \
               and self.role and self.role in message.author.roles \
               and message.author.id not in self.blacklisted_users

    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return await self.bot.allowed_by_whitelist_blacklist(message.author) \
               and await self.bot.ignored_channel_or_guild(message) \
               and not await self.bot.cog_disabled_in_guild(self, message.guild)

    @staticmethod
    def format_message(message: discord.Message) -> str:
        content = message.content
        if message.attachments and message.attachments[0].url:
            content += (' ' if content else '') + message.attachments[0].url
        return content

    @staticmethod
    async def insert_message_db(message: discord.Message, db: sql.Connection):
        await db.execute(f'INSERT INTO {DB_TABLE_MESSAGES} VALUES (?, ?, ?)',
                         [message.id, message.author.id, Simulator.format_message(message)])

    @staticmethod
    async def delete_message_db(message: discord.Message, db: sql.Connection):
        await db.execute(f'DELETE FROM {DB_TABLE_MESSAGES} WHERE id=?',
                         [message.id])

    # Simulator Functions

    def add_message(self, user_id: Optional[int] = None, content: Optional[str] = None, message: Optional[discord.Message] = None) -> bool:
        """Add a message to the model"""
        if message:
            user_id = message.author.id
            content = self.format_message(message)
        content = content.replace(CHAIN_END, '') if content else ''
        if not content:
            return False
        tokens = [m.group(1) for m in TOKENIZER.finditer(content)]
        if not tokens:
            return False
        for i in range(len(tokens)):  # treat special objects as 2 separate tokens, for better chains
            subtokens = [m.group(0) for m in SUBTOKENIZER.finditer(tokens[i])]
            if ''.join(subtokens) == tokens[i]:
                tokens.pop(i)
                for j in range(len(subtokens)):
                    tokens.insert(i + j, subtokens[j])
        tokens.append(CHAIN_END)
        previous = ""
        self.models.setdefault(int(user_id), UserModel(int(user_id), 0, {}))
        user = self.models[int(user_id)]
        user.frequency += 1
        for token in tokens:
            # Add token or increment its weight by 1
            user.model.setdefault(previous, {})
            user.model[previous][token] = user.model[previous].get(token, 0) + 1
            previous = token
        self.message_count += 1
        return True

    def start_conversation(self):
        self.conversation_left = random.randrange(CONVERSATION_MIN, CONVERSATION_MAX + 1)

    async def send_generated_message(self):
        user_id, content = self.generate_message()
        user = self.guild.get_member(int(user_id))
        if not user or not content or user.id in self.blacklisted_users:
            return
        await self.webhook.send(username=user.display_name,
                                avatar_url=user.avatar_url,
                                content=content,
                                allowed_mentions=discord.AllowedMentions.none())

    def generate_message(self) -> Tuple[int, str]:
        """Generate text based on the models"""
        user_id, = random.choices(population=list(self.models.keys()),
                                  weights=[x.frequency for x in self.models.values()],
                                  k=1)
        result = []
        token = ""
        previous = token
        while token != CHAIN_END:
            token, = random.choices(population=list(self.models[user_id].model[previous].keys()),
                                    weights=list(self.models[user_id].model[previous].values()),
                                    k=1)
            result.append(token)
            previous = token
        result = "".join(result[:-1]).strip()
        # formatting
        if result.count('(') != result.count(')'):
            result = re.sub(r"((?<=\w)[)]|[(](?=\w))", "", result)  # remove them and ignore smiley faces
        for left, right in [('[', ']'), ('“', '”'), ('‘', '’'), ('«', '»')]:
            if result.count(left) != result.count(right):
                if result.count(left) > result.count(right) and not result.endswith(left):
                    result += right
                else:
                    result = result.replace(left, '').replace(right, '')
        for char in ['"', '||', '**', '__', '```', '`']:
            if result.count(char) % 2 == 1:
                if not result.endswith(char):
                    result += char
                else:
                    result = result.replace(char, '')
        return user_id, result
