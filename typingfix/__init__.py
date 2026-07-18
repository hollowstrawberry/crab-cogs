from .typingfix import TypingFix
from redbot.core.utils import get_end_user_data_statement

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)

async def setup(_):
    await bot.add_cog(TypingFix())
