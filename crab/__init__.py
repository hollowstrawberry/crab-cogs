from .crab import Crab

async def setup(bot):
    cog = Crab(bot)
    await cog.load_config()
    bot.add_cog(cog)
