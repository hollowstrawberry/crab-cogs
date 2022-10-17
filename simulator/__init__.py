from .simulator import Simulator

__red_end_user_data_statement__ =\
    "This cog will locally store and analyze past and future messages sent by participating users, " \
    "in order to generate new messages in an owner-configured output channel. " \
    "You may opt out completely and delete your simulator data with the [p]dontsimulateme command."

def setup(bot):
    bot.add_cog(Simulator(bot))
