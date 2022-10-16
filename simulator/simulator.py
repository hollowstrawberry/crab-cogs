import discord
import asyncio
import random
import re
import os
import sys
import aiosqlite as sql
from dataclasses import dataclass
from datetime import datetime, timedelta
from numbers import Number
from collections import deque
from collections.abc import Set, Mapping
from redbot.core import commands, Config
from typing import Optional, Dict, List

WEBHOOK_NAME = "Simulator"
DB_FILE = "messages.db"
DB_TABLE_MESSAGES = "messages"
COMMIT_SIZE = 1000

CHAIN_END = "🔚"
TOKENIZER = re.compile(r"( ?https?://[^\s>]+"                # URLs
                       r"| ?<(@|#|@!|@&|a?:\w+:)\d{10,20}>"  # mentions, emojis
                       r"| ?@everyone| ?@here"               # pings
                       r"| ?[\w'-]+"                         # words
                       r"|[^\w<]+|<)")                       # symbols
SUBTOKENIZER = re.compile(r"( ?https?://(?=[^\s>])|(?<=://)[^\s>]+"         # URLs
                          r"| ?<a?:(?=\w)|(?<=:)\w+:\d{10,20}>"             # emojis
                          r"| ?<[@#](?=[\d&!])|(?<=[@#])[!&]?\d{10,20}>)")  # mentions

CONVERSATION_CHANCE_ONEIN = 30
MESSAGE_CHANCE_ONEIN = 5
CONVERSATION_DELAY = 60
CONVERSATION_MIN = 4
CONVERSATION_MAX = 15

EMOJI_LOADING = '⌛'
EMOJI_SUCCESS = '✅'
EMOJI_FAILURE = '❌'

ZERO_DEPTH_BASES = (str, bytes, Number, range, bytearray)

def format_message(message: discord.Message) -> str:
    content = message.content
    if message.attachments and message.attachments[0].url:
        content += (' ' if content else '') + message.attachments[0].url
    return content

async def insert_message_db(message: discord.Message, db: sql.Connection):
    await db.execute(f'INSERT INTO {DB_TABLE_MESSAGES} VALUES (?, ?, ?);',
                     [message.id, message.author.id, format_message(message)])

async def delete_message_db(message: discord.Message, db: sql.Connection):
    await db.execute(f'DELETE FROM {DB_TABLE_MESSAGES} WHERE id=? LIMIT 1;',
                     [message.id])

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
        if isinstance(obj, ZERO_DEPTH_BASES):
            pass  # bypass remaining control flow and return
        elif isinstance(obj, (tuple, list, Set, deque)):
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

class Simulator(commands.Cog):
    """Designates a channel that will send automated messages mimicking your friend group.
    You may feed it messages from designated channels and it will create Markov chains from them.
    Inspired by /r/SubredditSimulator and similar concepts.
    Will only support a single guild set by the bot owner."""

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.running = False
        self.feeding = False
        self.guild: Optional[discord.Guild] = None
        self.input_channels: Optional[List[discord.TextChannel]] = None
        self.output_channel: Optional[discord.TextChannel] = None
        self.role: Optional[discord.Role] = None
        self.webhook: Optional[discord.Webhook] = None
        self.conversation_left = 0
        self.models: Dict[int, UserModel] = {}
        self.message_count = 0
        self.message_chance = 1 / MESSAGE_CHANCE_ONEIN
        self.conversation_chance = 1 / CONVERSATION_CHANCE_ONEIN
        self.config = Config.get_conf(self, identifier=7369756174)
        default_config = {
            "home_guild_id": 0,
            "input_channel_ids": [0],
            "output_channel_id": 0,
            "participant_role_id": 0,
            "message_chance_onein": MESSAGE_CHANCE_ONEIN,
            "conversation_chance_onein": CONVERSATION_CHANCE_ONEIN,
        }
        self.config.register_global(**default_config)
        if self.bot.is_ready():
            asyncio.create_task(self.on_ready())

    def cog_unload(self):
        self.running = False
        self.feeding = False

    @commands.command()
    async def simulatorstats(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Statistics about the simulator, globally or for a user"""
        if self.role not in ctx.author.roles:
            await ctx.message.add_reaction(EMOJI_FAILURE)
            return

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
                await ctx.send("User not found")
                return
            messages = self.models[user.id].frequency
            nodes = count_nodes(self.models[user.id].model)
            words = count_words(self.models[user.id].model)
        else:
            messages = self.message_count
            nodes = sum(count_nodes(x.model) for x in self.models.values())
            words = sum(count_words(x.model) for x in self.models.values())

        filesize = os.path.getsize(DB_FILE) / 1000000
        objectsize = getsize(self.models) / 1000000

        embed = discord.Embed(title="Simulator Stats", color=0x1DE417)
        embed.add_field(name="Messages", value=f"{messages:,}", inline=True)
        embed.add_field(name="Nodes", value=f"{nodes:,}", inline=True)
        embed.add_field(name="Words", value=f"{words:,}", inline=True)
        embed.add_field(name="Size", value=f"{round(filesize, 2)} MB (Database), {round(objectsize, 2)} MB (Model)")
        await ctx.send(embed=embed)

    @commands.command()
    async def simulatorcount(self, ctx: commands.Context, word: str, user: Optional[discord.Member] = None):
        """Count instances of a word, globally or for a user"""
        sword = ' ' + word
        if user:
            if user.id not in self.models:
                await ctx.send("This users' messages are not being recorded")
                return
            occurences = sum(x.get(word, 0) + x.get(sword, 0) for x in self.models[user.id].model.values())
            children = len(self.models[user.id].model.get(word, {}) | self.models[user.id].model.get(sword, {}))
        else:
            occurences = sum(sum(x.get(word, 0) + x.get(sword, 0) for x in m.model.values())
                             for m in self.models.values())
            children = sum(len(m.model.get(word, {}) | m.model.get(sword, {})) for m in self.models.values())
        await ctx.send(f"```yaml\nOccurrences: {occurences:,}\nWords that follow: {children:,}```")

    @commands.command()
    @commands.is_owner()
    async def startsimulator(self, ctx: commands.Context):
        """Start the simulator in the configured channel."""
        if self.role not in ctx.author.roles:
            await ctx.message.add_reaction(EMOJI_FAILURE)
            return
        if not self.running and not self.feeding:
            asyncio.create_task(self.on_ready())
        await ctx.message.add_reaction(EMOJI_SUCCESS)

    @commands.command()
    @commands.is_owner()
    async def stopsimulator(self, ctx: commands.Context):
        """Stop the simulator."""
        if self.role not in ctx.author.roles:
            await ctx.message.add_reaction(EMOJI_FAILURE)
            return
        self.running = False
        await ctx.message.add_reaction(EMOJI_SUCCESS)

    @commands.command()
    @commands.is_owner()
    async def feedsimulator(self, ctx: commands.Context, days: int):
        """Feed past messages into the simulator from the configured channels from scratch."""
        await ctx.message.add_reaction(EMOJI_LOADING)
        self.running = False
        self.feeding = True
        self.message_count = 0
        for user in self.models.values():
            user.model = {}
            user.frequency = 0
        try:
            async with sql.connect(DB_FILE) as db:
                await db.execute(f"DELETE FROM {DB_TABLE_MESSAGES}")
                await db.commit()
                start_date = datetime.now() - timedelta(days=days)
                for channel in self.input_channels:
                    async for message in channel.history(after=start_date, limit=None):
                        if not self.feeding:
                            break
                        if message.author.bot:
                            continue
                        if self.add_message(message=message):
                            await insert_message_db(message, db)
                            if self.message_count % COMMIT_SIZE == 0:
                                await db.commit()
                    await db.commit()
        except Exception as error:
            await ctx.send(f"{type(error).__name__}: {error}\n"
                           f"Loaded {self.message_count} messages, "
                           f"{self.message_count // COMMIT_SIZE * COMMIT_SIZE} to database")
        finally:
            self.feeding = False
        asyncio.create_task(self.run_simulator())
        await ctx.send(f"Loaded {self.message_count} messages")
        await ctx.message.remove_reaction(EMOJI_LOADING, self.bot.user)
        await ctx.message.add_reaction(EMOJI_SUCCESS)

    @commands.group(invoke_without_command=True)
    @commands.is_owner()
    async def simulatorset(self, ctx: commands.Context):
        """Set up your simulator."""
        await ctx.send_help()

    @simulatorset.command()
    @commands.is_owner()
    async def inputchannels(self, ctx: commands.Context, *channels: discord.TextChannel):
        """Set a series of channels that will feed the simulator."""
        await self.config.home_guild_id.set(ctx.guild.id)
        await self.config.input_channel_ids.set([channel.id for channel in channels])
        self.guild = ctx.guild
        self.input_channels = channels
        await ctx.react_quietly(EMOJI_SUCCESS)

    @simulatorset.command()
    @commands.is_owner()
    async def outputchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel the simulator will run in."""
        await self.config.output_channel_id.set(channel.id)
        self.output_channel = channel
        await ctx.react_quietly(EMOJI_SUCCESS)

    @simulatorset.command()
    @commands.is_owner()
    async def participantrole(self, ctx: commands.Context, role: discord.Role):
        """Members must have this role to participate in the simulator."""
        await self.config.participant_role_id.set(role.id)
        self.role = role
        await ctx.react_quietly(EMOJI_SUCCESS)

    @simulatorset.command()
    @commands.is_owner()
    async def conversationchance_onein(self, ctx: commands.Context, chance: int):
        """The chance that the simulator will start a conversation every minute."""
        await self.config.conversation_chance_onein.set(max(1, chance))
        self.conversation_chance = 1 / max(1, chance)
        await ctx.react_quietly(EMOJI_SUCCESS)

    @simulatorset.command()
    @commands.is_owner()
    async def messagechance_onein(self, ctx: commands.Context, chance: int):
        """The chance that the simulator will send a message every second during a conversation."""
        await self.config.message_chance_onein.set(max(1, chance))
        self.message_chance = 1 / max(1, chance)
        await ctx.react_quietly(EMOJI_SUCCESS)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.running:
            if await self.setup_simulator():
                await self.run_simulator()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Processes new incoming messages"""
        if message.channel in self.input_channels and not message.author.bot and self.role in message.author.roles:
            if self.add_message(message=message):
                async with sql.connect(DB_FILE) as db:
                    await insert_message_db(message, db)
                    await db.commit()
        elif message.channel == self.output_channel and not message.author.bot \
                and message.type == discord.MessageType.default:
            try:
                await message.delete()
            except:
                pass
            if self.role in message.author.roles:
                self.start_conversation()

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Processes deleted messages"""
        if message.channel in self.input_channels and not message.author.bot and self.role in message.author.roles:
            async with sql.connect(DB_FILE) as db:
                await delete_message_db(message, db)
                await db.commit()

    @commands.Cog.listener()
    async def on_message_edit(self, message: discord.Message, edited: discord.Message):
        """Processes edited messages"""
        if message.channel in self.input_channels and not message.author.bot and self.role in message.author.roles:
            async with sql.connect(DB_FILE) as db:
                await delete_message_db(message, db)
                if self.add_message(message=edited):
                    await insert_message_db(edited, db)
                await db.commit()

    def add_message(self,
                    user_id: Optional[int] = None,
                    content: Optional[str] = None,
                    message: Optional[discord.Message] = None) -> bool:
        """Add a message to the model"""
        if message:
            user_id = message.author.id
            content = format_message(message)
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
                    tokens.insert(i+j, subtokens[j])
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

    async def setup_simulator(self):
        """Set up the simulator"""
        try:
            guild_id = await self.config.home_guild_id()
            input_channel_ids = await self.config.input_channel_ids()
            output_channel_id = await self.config.output_channel_id()
            role_id = await self.config.participant_role_id()
            self.message_chance = 1 / await self.config.message_chance_onein()
            self.conversation_chance = 1 / await self.config.conversation_chance_onein()
            if guild_id == 0 or 0 in input_channel_ids or output_channel_id == 0 or role_id == 0:
                raise ValueError("You must first set the guild, role, input channels and output channel.")

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
            count = 0
            async with sql.connect(DB_FILE) as db:
                await db.execute(f"CREATE TABLE IF NOT EXISTS {DB_TABLE_MESSAGES} "
                                 f"(id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT NOT NULL);")
                await db.commit()
                async with db.execute(f"SELECT * FROM {DB_TABLE_MESSAGES}") as cursor:
                    async for row in cursor:
                        self.add_message(row[1], row[2])
                        count += 1
            print(f"Model built with {count} messages")
            return True
        except Exception as error:
            print(f'Failed to set up the simulator: {error}')
            await self.output_channel.send(f'Failed to set up: {error}')

    async def run_simulator(self):
        """Run the simulator"""
        self.running = True
        while self.running and not self.feeding:
            if self.conversation_left:
                if random.random() < self.message_chance:
                    try:
                        self.conversation_left -= 1
                        await self.send_generated_message()
                    except Exception as error:
                        print(f'{type(error).__name__}: {error}')
                        try:
                            await self.output_channel.send(f'{type(error).__name__}: {error}')
                        except:
                            pass
                await asyncio.sleep(1)
            else:
                if random.random() < self.conversation_chance:
                    self.start_conversation()
                for i in range(CONVERSATION_DELAY):
                    if self.conversation_left or not self.running:
                        break
                    await asyncio.sleep(1)

    def start_conversation(self):
        self.conversation_left = random.randrange(CONVERSATION_MIN, CONVERSATION_MAX + 1)

    async def send_generated_message(self):
        user_id, content = self.generate_message()
        user = self.guild.get_member(int(user_id))
        if user is None:
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
