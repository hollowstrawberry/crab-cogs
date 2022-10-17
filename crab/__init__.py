from .crab import Crab

async def setup(bot):
    bot.add_cog(await Crab(bot).load_config())
