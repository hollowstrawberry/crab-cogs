from .emojisteal import EmojiSteal

__red_end_user_data_statement__ = "This cog does not store any user data."

def setup(bot):
    bot.add_cog(EmojiSteal(bot))
