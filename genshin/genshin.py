import discord
from random import random, choice
from redbot.core import commands, Config

BANNERS = {
    "Hu Tao": {
        "5starfeatured": ["Hu Tao"],
        "5star": ["Keqing", "Mona", "Qiqi", "Diluc", "Jean"],
        "5starweapon": [],
        "4starfeatured": ["Chongyun", "Xingqiu", "Xiangling"],
        "4star": [
            "Xinyan", "Sucrose", "Diona", "Noelle", "Bennett", "Fischl", "Ningguang", "Beidou", "Razor", "Barbara"],
        "4starweapon": [
            "Rust", "Sacrificial Bow", "The Stringless", "Favonius Warbow", "Eye of Perception",
            "Sacrificial Fragments", "The Widsith", "Favonius Codex", "Favonius Lance", "Dragon's Bane",
            "Rainslasher", "Sacrificial Greatsword", "The Bell", "Favonius Greatsword", "Lions Roar",
            "Sacrificial Sword", "The Flute", "Favonius Sword"],
        "3star": [
            "Slingshot", "Sharpshooter's Oath", "Raven Bow", "Emerald Orb", "Thrilling Tales of Dragon Slayers",
            "Magic Guide", "Black Tassel", "Debate Club", "Bloodtainted Greatsword", "Ferrous Shadow",
            "Skyrider Sword", "Harbinger of Dawn", "Cool Steel"]
    }
}

FIVESTARS = set(sum([banner["5star"] + banner["5starfeatured"] + banner["5starweapon"] for banner in BANNERS.values()], []))
FOURSTARS = set(sum([banner["4star"] + banner["4starfeatured"] + banner["4starweapon"] for banner in BANNERS.values()], []))
PULL_IMG = {
    "Hu Tao": "https://cdn.discordapp.com/attachments/541768631445618689/818653017892061194/unknown.png"
}
WISH_IMG3 = "https://cdn.discordapp.com/attachments/541768631445618689/818649843202916362/unknown.png"
WISH_IMG4 = "https://media.discordapp.net/attachments/541768631445618689/879785351579832371/wish4.png"
WISH_IMG5 = "https://cdn.discordapp.com/attachments/541768631445618689/879785356382330901/wish5.png"


class Genshin(commands.Cog):
    """Simulates Genshin Impact gacha pulls."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=6765673686)
        default_config = {"no4star": 0, "no4starf": 0, "no5star": 0, "no5starf": 0, "inv": {}}
        self.config.register_user(**default_config)
        self.banner = BANNERS["Hu Tao"]

    async def red_delete_data_for_user(self, requester: str, user_id: int):
        await self.config.user_from_id(user_id).clear()

    # Commands

    def pull(self, userdata):
        roll = random()
        if userdata["no5starf"] >= 179:  # featured 5 star pity
            possible = self.banner["5starfeatured"]
        elif userdata["no5star"] >= 89 or roll < 0.006:  # 5 star
            if random() > 0.5:
                possible = self.banner["5starfeatured"]
            elif random() > 0.5 and self.banner["5starweapon"]:
                possible = self.banner["5starweapon"]
            else:
                possible = self.banner["5star"]
        elif userdata["no4starf"] >= 19:  # featured 4 star pity
            possible = self.banner["4starfeatured"]
        elif userdata["no4star"] >= 9 or roll < 0.051:  # 4 star
            if random() > 0.5:
                possible = self.banner["4starfeatured"]
            elif random() > 0.5 and self.banner["4starweapon"]:
                possible = self.banner["4starweapon"]
            else:
                possible = self.banner["4star"]
        else:  # 3 star
            possible = self.banner["3star"]

        result = choice(possible)
        if result in FOURSTARS:
            userdata["no4star"] = 0
            if result in self.banner["4starfeatured"]:
                userdata["no4starf"] = 0
            else:
                userdata["no4starf"] += 1
            userdata["no5star"] += 1
            userdata["no5starf"] += 1
        else:
            userdata["no4star"] += 1
            userdata["no4starf"] += 1
            if result in FIVESTARS:
                userdata["no5star"] = 0
                if result in self.banner["5starfeatured"]:
                    userdata["no5starf"] = 0
                else:
                    userdata["no5starf"] += 1
            else:
                userdata["no5star"] += 1

        userdata["inv"][result] = userdata["inv"].get(result, 0) + 1
        return result

    async def pullx(self, user: discord.User, x: int):
        userdata = await self.config.user(user).get_raw()
        pulled = []
        for _ in range(x):
            pulled.append(self.pull(userdata))
        await self.config.user(user).set_raw(value=userdata)
        return pulled

    @classmethod
    def formatitem(cls, item):
        return f'{item}{" ⭐⭐⭐⭐⭐" if item in FIVESTARS else ""}{" ⭐⭐⭐⭐" if item in FOURSTARS else ""}'

    @commands.group(aliases=["genshinimpact"], invoke_without_command=True)
    async def genshin(self, ctx: commands.Context):
        """Base genshin command. Use me!"""
        await ctx.send_help()

    @genshin.command(aliases=["pull", "wish", "summon"])
    async def pull1(self, ctx: commands.Context, *, etc=""):
        """Makes 1 Genshin Impact wish (Hu Tao banner)"""
        if etc == '10':
            return await self.pull10(ctx)
        pulled = (await self.pullx(ctx.author, 1))[0]
        embed = discord.Embed(title="Your pull", description=self.formatitem(pulled), color=await ctx.embed_color())
        embed.set_thumbnail(url=WISH_IMG5 if pulled in FIVESTARS else WISH_IMG4 if pulled in FOURSTARS else WISH_IMG3)
        embed.set_image(url=PULL_IMG.get(pulled, ""))
        await ctx.send(embed=embed)

    @genshin.command(aliases=["wish10", "summon10"])
    async def pull10(self, ctx: commands.Context):
        """Makes 10 Genshin Impact wishes (Hu Tao banner)"""
        pulled = await self.pullx(ctx.author, 10)
        pulledf = "\n".join(self.formatitem(p) for p in pulled)
        embed = discord.Embed(title="Your pulls", description=f"```md\n{pulledf}```", color=await ctx.embed_color())
        embed.set_thumbnail(url=WISH_IMG5 if any(p in FIVESTARS for p in pulled) else
                            WISH_IMG4 if any(p in FOURSTARS for p in pulled) else WISH_IMG3)
        embed.set_image(url=next((PULL_IMG.get(p) for p in pulled if p in PULL_IMG), ""))
        await ctx.send(embed=embed)

    @genshin.command(aliases=["inventory"])
    async def inv(self, ctx: commands.Context):
        """View your Genshin Impact inventory"""
        inv = await self.config.user(ctx.author).inv()
        if not inv:
            await ctx.send("You haven't pulled anything yet.")
        else:
            s = "```md"
            for key, value in inv.items():
                if key not in self.banner["3star"]:
                    s += f'\n{value} x {key}{" ⭐⭐⭐⭐⭐" if key in FIVESTARS else ""}'
            embed = discord.Embed(title="Your inventory", description=s + "```", color=await ctx.embed_color())
            await ctx.send(embed=embed)
