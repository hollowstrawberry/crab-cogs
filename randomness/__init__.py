from .randomness import Randomness

__red_end_user_data_statement__ = "This cog stores user IDs to keep track of your donut score."

async def setup(bot):
    bot.add_cog(Randomness(bot))
