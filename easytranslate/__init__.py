from .easytranslate import EasyTranslate
from redbot.core.utils import get_end_user_data_statement
from redbot.core.commands import Bot

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)

async def setup(bot: Bot):
    await bot.add_cog(EasyTranslate(bot))
    await bot.tree.sync()
