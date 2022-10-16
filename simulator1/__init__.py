from .simulator import Simulator

def setup(bot):
    bot.add_cog(Simulator(bot))
