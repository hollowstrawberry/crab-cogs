from .emojisteal import EmojiSteal

def setup(bot):
    bot.add_cog(EmojiSteal(bot))
