from .draw import Draw

__red_end_user_data_statement__ = "This cog does not store any user data."

def setup(bot):
    bot.add_cog(Draw(bot))