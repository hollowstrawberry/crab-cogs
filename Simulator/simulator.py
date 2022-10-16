import discord
import asyncio
import random
import re
import aiosqlite as sql
from dataclasses import dataclass
from datetime import datetime, timedelta
from discord.ext import commands
from typing import *

HOME_GUILD_ID = 930471371128061962
INPUT_CHANNEL_IDS = [930471825668988959, 930471371128061965]
OUTPUT_CHANNEL_ID = 930472235527983174
ROLE_ID = 930489841421004830
WEBHOOK_NAME = "CrabSimulator"

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
MESSAGE_CHANCE = 1/10
CONVERSATION_CHANCE = 1/40
CONVERSATION_DELAY = 60
CONVERSATION_MIN = 4
CONVERSATION_MAX = 15

EMOJI_LOADING = '<a:loading:410612084527595520>'
EMOJI_SUCCESS = '✅'
EMOJI_FAILURE = '❌'

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

@dataclass
class UserModel:
    user_id: int
    frequency: int
    model: dict

class Simulator(commands.Cog):
    def __init__(self, bot: commands.Bot):
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
        if self.bot.is_ready():
            asyncio.create_task(self.on_ready())

    def cog_unload(self):
        self.running = False
        self.feeding = False

    @commands.command()
    async def startsimulator(self, ctx: commands.Context):
        """Start the simulator"""
        if self.role not in ctx.author.roles:
            await ctx.message.add_reaction(EMOJI_FAILURE)
            return
        if not self.running and not self.feeding:
            asyncio.create_task(self.run_simulator())
        await ctx.message.add_reaction(EMOJI_SUCCESS)

    @commands.command()
    async def stopsimulator(self, ctx: commands.Context):
        """Stop the simulator"""
        if self.role not in ctx.author.roles:
            await ctx.message.add_reaction(EMOJI_FAILURE)
            return
        self.running = False
        await ctx.message.add_reaction(EMOJI_SUCCESS)

    @commands.command()
    async def stats(self, ctx: commands.Context, user: Optional[discord.Member]):
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
        await ctx.send(f"```yaml\nMessages: {messages:,}\nNodes: {nodes:,}\nWords: {words:,}```")

    @commands.command()
    async def count(self, ctx: commands.Context, word: str, user: Optional[discord.Member] = None):
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
    async def feedsimulator(self, ctx: commands.Context, days: int):
        """Feed past messages into the simulator"""
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

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.running:
            await self.setup_simulator()
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
            # discord entities
            self.guild = self.bot.get_guild(HOME_GUILD_ID)
            if self.guild is None: raise KeyError(self.guild.__name__)
            self.role = self.guild.get_role(ROLE_ID)
            self.input_channels = [self.guild.get_channel(i) for i in INPUT_CHANNEL_IDS]
            self.output_channel = self.guild.get_channel(OUTPUT_CHANNEL_ID)
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
        except Exception as error:
            print(f'Failed to set up crab simulator: {error}')
            await self.output_channel.send(f'Failed to set up: {error}')

    async def run_simulator(self):
        """Run the simulator"""
        self.running = True
        while self.running and not self.feeding:
            if self.conversation_left:
                if random.random() < MESSAGE_CHANCE:
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
                if random.random() < CONVERSATION_CHANCE:
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
