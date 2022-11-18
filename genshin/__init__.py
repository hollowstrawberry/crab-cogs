from .genshin import Genshin
from redbot.core.utils import get_end_user_data_statement

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)

def setup(bot):
    cog = Genshin(bot)
    bot.add_cog(cog)
