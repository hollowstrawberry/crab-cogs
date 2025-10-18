from .simplecasino import setup
from redbot.core.utils import get_end_user_data_statement

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)

_ = setup  # importing it is enough
