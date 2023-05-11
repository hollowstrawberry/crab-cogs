import discord
from typing import Optional
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.menus import SimpleMenu

LATEST_LOGS = "/data/core/logs/latest.log"
MAX_PAGE_LENGTH = 1970

class Logs(commands.Cog):
    """Owner cog to show the latest logs."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=66677363)
        self.config.register_global(private=True)

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass

    @commands.is_owner()
    @commands.group(invoke_without_command=True)
    async def logs(self, ctx: commands.Context, lines: Optional[int]):
        """Sends the last n lines of the latest log file (default 100)."""
        private = await self.config.private()
        channel = (ctx.author.dm_channel or await ctx.author.create_dm()) if private else ctx.channel
        if not lines or lines < 0:
            lines = 100
        pages = []
        with open(LATEST_LOGS, 'r') as f:
            result = [line.strip() for line in f.readlines()[-lines:]]
        while result:
            page = ""
            while result:
                if len(page) + 1 + len(result[-1]) <= MAX_PAGE_LENGTH:
                    page = result.pop() + "\n" + page
                else:
                    break
            pages.append(f"```py\n{page.strip()}```")
        if not pages:
            await channel.send("Empty")
        elif len(pages) == 1:
            await channel.send(content=pages[0])
        else:
            pages.reverse()
            for i, page in enumerate(pages):
                page += f"`Page {i+1}/{len(pages)}`"
            ctx.message.channel = channel
            await SimpleMenu(pages, timeout=7200, page_start=len(pages)-1).start(ctx)

    @logs.command(name="file")
    async def logs_file(self, ctx: commands.Context):
        """Sends the entire latest log file."""
        private = await self.config.private()
        channel = (ctx.author.dm_channel or await ctx.author.create_dm()) if private else ctx.channel
        file = discord.File(LATEST_LOGS, filename="latest.log")
        return await channel.send(file=file)

    @logs.command(name="private")
    async def logs_private(self, ctx: commands.Context):
        """Whether logs should be sent to your DMs."""
        new_value = not await self.config.private()
        await self.config.private.set(new_value)
        await ctx.send("Logs will now be sent " + ("in your DMs" if new_value else "in the same channel"))
