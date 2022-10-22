from types import MethodType
from redbot.core import commands
from discord.ext.commands import Context as DPYContext

old_ctx_send = commands.Context.send

class CustomContext(commands.Context):
    async def send(self, content: str = None, **kwargs):
        _filter = kwargs.pop("filter", None)

        if _filter and content:
            content = _filter(str(content))

        if 'reference' not in kwargs:
            kwargs['reference'] = self.message

        return await super(DPYContext).send(content, **kwargs)

class AlwaysReply(commands.Cog):
    """Makes the bot always reply to commands"""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        commands.Context.send = MethodType(CustomContext.send, commands.Context)

    def cog_unload(self):
        commands.Context.send = old_ctx_send

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        pass




