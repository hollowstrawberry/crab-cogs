import logging
import asyncio
import discord
import calendar
import aiofiles
from typing import Optional, Union
from datetime import datetime
from redbot.core import commands, app_commands, bank
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path
from redbot.cogs.economy.economy import Economy
from redbot.core.utils.chat_formatting import humanize_number
from redbot.core.utils.chat_formatting import humanize_timedelta

from casino.base import BaseCasinoCog
from casino.slots import slots
from casino.poker import PokerGame
from casino.blackjack import Blackjack
from casino.utils import POKER_MINIMUM_BET
from casino.views.again_view import AgainView
from casino.views.replace_view import ReplaceView

log = logging.getLogger("red.crab-cogs.casino")

old_slot: Optional[commands.Command] = None
old_payouts: Optional[commands.Command] = None

MAX_CONCURRENT_SLOTS = 3
POKER_AFK_LIMIT = 0  # minutes
STARTING = "Starting game..."


class Casino(BaseCasinoCog):
    """Improves the builtin slot command and adds blackjack."""

    def __init__(self, bot: Red):
        super().__init__(bot)
        self.concurrent_slots = 0

    async def cog_load(self) -> None:
        # Load existing games
        all_channels = await self.config.all_channels()
        for cid, conf in all_channels.items():
            try:
                channel = self.bot.get_channel(cid)
                assert isinstance(channel, (discord.TextChannel, discord.Thread))
                if not channel:
                    continue
                game_config = conf.get("game", {})
                if not game_config:
                    continue
                game = await PokerGame.from_config(self, channel, game_config)
                self.poker_games[cid] = game
                if game.view:
                    self.bot.add_view(game.view)
            except Exception:
                log.error(f"Loading game in {cid}", exc_info=True)

        # Load custom emojis into the current application. I don't want to touch this honestly.
        if not await self.config.emoji_dealer():
            async with aiofiles.open(bundled_data_path(self) / "dealer.png", "rb") as fp:
                image_dealer = await fp.read()
            emoji_dealer = await self.bot.create_application_emoji(name="dealer", image=image_dealer)
            await self.config.emoji_dealer.set(str(emoji_dealer))
        if not await self.config.emoji_smallblind():
            async with aiofiles.open(bundled_data_path(self) / "smallblind.png", "rb") as fp:
                image_smallblind = await fp.read()
            emoji_smallblind = await self.bot.create_application_emoji(name="smallblind", image=image_smallblind)
            await self.config.emoji_smallblind.set(str(emoji_smallblind))
        if not await self.config.emoji_bigblind():
            async with aiofiles.open(bundled_data_path(self) / "bigblind.png", "rb") as fp:
                image_bigblind = await fp.read()
            emoji_bigblind = await self.bot.create_application_emoji(name="bigblind", image=image_bigblind)
            await self.config.emoji_bigblind.set(str(emoji_bigblind))
        if not await self.config.emoji_spades():
            async with aiofiles.open(bundled_data_path(self) / "spades.png", "rb") as fp:
                image_spades = await fp.read()
            emoji_spades = await self.bot.create_application_emoji(name="spades", image=image_spades)
            await self.config.emoji_spades.set(str(emoji_spades))
        if not await self.config.emoji_clubs():
            async with aiofiles.open(bundled_data_path(self) / "clubs.png", "rb") as fp:
                image_clubs = await fp.read()
            emoji_clubs = await self.bot.create_application_emoji(name="clubs", image=image_clubs)
            await self.config.emoji_clubs.set(str(emoji_clubs))

    def cog_unload(self):
        global old_slot, old_payouts
        for game in self.poker_games.values():
            if game.view:
                game.view.stop()
        if old_slot:
            self.bot.remove_command(old_slot.name)
            self.bot.add_command(old_slot)
        if old_payouts:
            self.bot.remove_command(old_payouts.name)
            self.bot.add_command(old_payouts)

    async def get_economy_cog(self, ctx: Union[discord.Interaction, commands.Context]) -> Optional[Economy]:
        cog: Optional[Economy] = self.bot.get_cog("Economy")  # type: ignore
        if cog:
            return cog
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message
        await reply("Economy cog not loaded! Contact the bot owner for more information.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    

    @commands.hybrid_command(name="blackjack", aliases=["bj"])
    @app_commands.describe(bid="How much currency to bet.")
    @commands.guild_only()
    async def blackjack_cmd(self, ctx: commands.Context, bid: int):
        """Play Blackjack against the bot. Get as close to 21 as possible!"""
        await self.blackjack(ctx, bid)

    async def blackjack(self, ctx: Union[discord.Interaction, commands.Context], bid: int):
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message
        assert ctx.guild and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)

        minimum_bid = await self.config.bjmin() if await bank.is_global() else await self.config.guild(ctx.guild).bjmin()
        maximum_bid = await self.config.bjmax() if await bank.is_global() else await self.config.guild(ctx.guild).bjmax()
        currency_name = await bank.get_currency_name(ctx.guild)
        if bid < 1 or bid < minimum_bid:
            return await reply(f"Your bid must be at least {humanize_number(minimum_bid)} {currency_name}", ephemeral=True)
        elif bid > maximum_bid:
            return await reply(f"Your bid cannot be greater than {humanize_number(maximum_bid)} {currency_name}", ephemeral=True)
        if not await bank.can_spend(author, bid):
            return await reply("You ain't got enough money, friend.", ephemeral=True)
        
        await bank.withdraw_credits(author, bid)
        blackjack = Blackjack(self, author, ctx.channel, bid, await self.bot.get_embed_color(ctx.channel))
        await blackjack.check_payout()
        view = AgainView(self.blackjack, bid, None, currency_name) if blackjack.is_over() else blackjack
        message = await reply(embed=await blackjack.get_embed(), view=view)
        if isinstance(view, AgainView):
            view.message = message if isinstance(ctx, commands.Context) else await ctx.original_response()  # type: ignore


    @commands.hybrid_command(name="slot")
    @commands.guild_only()
    @app_commands.describe(bid="How much currency to put in the slot machine.")
    async def slot_cmd(self, ctx: commands.Context, bid: int):
        """Play the slot machine."""
        try:
            if not ctx.interaction:
                self.concurrent_slots += 1
            await self.slot(ctx, bid)
        finally:
            if not ctx.interaction:
                self.concurrent_slots -= 1

    async def slot(self, ctx: Union[discord.Interaction, commands.Context], bid: int):
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message
        assert ctx.guild and isinstance(author, discord.Member)

        if not (economy := await self.get_economy_cog(ctx)):
            return

        if self.concurrent_slots > MAX_CONCURRENT_SLOTS and isinstance(ctx, commands.Context) and not ctx.interaction:
            content = f"Too many people are using the slot machine right now. "
            if self.bot.tree.get_command("slots") is None:
                content += "The bot owner could enable the `/slots` slash command, which would allow more people to use it at the same time."
            else:
                content += "Consider using the `/slots` slash command instead, which allows more people to use it at the same time."
            return await reply(content)
        
        is_global = await bank.is_global()
        if await bank.is_global():
            min_bid = await economy.config.SLOT_MIN()
            max_bid = await economy.config.SLOT_MAX()
            slot_time = await economy.config.SLOT_TIME()
            last_slot = await economy.config.user(author).last_slot()
        else:
            min_bid = await economy.config.guild(ctx.guild).SLOT_MIN()
            max_bid = await economy.config.guild(ctx.guild).SLOT_MAX()
            slot_time = await economy.config.guild(ctx.guild).SLOT_TIME()
            last_slot = await economy.config.member(author).last_slot()
        
        created_at = ctx.created_at if isinstance(ctx, discord.Interaction) else ctx.message.created_at
        cur_time = calendar.timegm(created_at.utctimetuple())
        currency_name = await bank.get_currency_name(ctx.guild)

        if (cur_time - last_slot) < max(3, slot_time):
            await reply("You're on cooldown, try again in a few seconds.")
            return
        if bid < min_bid:
            await reply(f"Your bid must be at least {humanize_number(min_bid)} {currency_name}")
            return
        if bid > max_bid:
            await reply(f"Your bid cannot be greater than {humanize_number(max_bid)} {currency_name}")
            return
        if not await bank.can_spend(author, bid):
            await reply("You ain't got enough money, friend.")
            return
        
        if is_global:
            await economy.config.user(author).last_slot.set(cur_time)
        else:
            await economy.config.member(author).last_slot.set(cur_time)

        await slots(self, ctx, bid)


    @commands.command(name="poker")
    @commands.guild_only()
    async def poker_cmd(self, ctx: commands.Context, starting_bet: int):
        """Start a new game of Poker with no players and a starting bid."""
        await self.poker(ctx, starting_bet)

    async def poker(self, ctx: Union[discord.Interaction, commands.Context], starting_bet: int):
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        assert ctx.guild and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
        
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message

        minimum_starting_bet = await self.config.pokermin() if await bank.is_global() else await self.config.guild(ctx.guild).pokermin()
        currency_name = await bank.get_currency_name(ctx.guild)
        if starting_bet < minimum_starting_bet:
            return await reply(f"The starting bet must be at least {minimum_starting_bet} {currency_name}.")
        if not await bank.can_spend(author, starting_bet):
            return await reply(f"You don't have enough {currency_name} to make that bet.")

        # Game already exists
        if ctx.channel.id in self.poker_games and not self.poker_games[ctx.channel.id].is_finished:
            old_game = self.poker_games[ctx.channel.id]
            try:
                old_message = await ctx.channel.fetch_message(old_game.message.id) if old_game.message else None # re-fetch
            except discord.NotFound:
                old_message = None

            if not old_message:
                await old_game.update_message()
                old_message = old_game.message
                assert old_message

            seconds_passed = int((datetime.now() - old_game.last_interacted).total_seconds())
            if seconds_passed // 60 >= POKER_AFK_LIMIT:
                async def callback():
                    nonlocal ctx, author, old_game
                    assert isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
                    await old_game.cancel()
                    await old_game.update_message()
                    game = PokerGame(self, [author], ctx.channel, starting_bet)
                    self.poker_games[ctx.channel.id] = game
                    await game.update_message()

                content = f"Someone else is playing Checkers in this channel, here: {old_message.jump_url}, " \
                          f"but {humanize_timedelta(seconds=seconds_passed)} have passed since their last interaction. Do you want to start a new game?"
                embed = discord.Embed(title="Confirmation", description=content, color=await self.bot.get_embed_color(ctx.channel))
                view = ReplaceView(self, callback, author)
                message = await reply(embed=embed, view=view)
                view.message = message if isinstance(ctx, commands.Context) else await ctx.original_response()  # type: ignore
                return
            
            else:
                content = f"There is still an active game in this channel, here: {old_message.jump_url}\nTry again in a few minutes"
                permissions = ctx.channel.permissions_for(author)
                content += " or consider creating a thread." if permissions.create_public_threads or permissions.create_private_threads else "."
                await reply(content, ephemeral=True)
                return
        
        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(STARTING, ephemeral=True)
        elif ctx.interaction:
            await ctx.interaction.response.send_message(STARTING, ephemeral=True)

        # New game
        game = PokerGame(self, [author], ctx.channel, starting_bet)
        self.poker_games[ctx.channel.id] = game
        await game.update_message()


    @commands.group(name="casinoset", aliases=["setcasino"])  # type: ignore
    @commands.admin_or_permissions(manage_guild=True)
    @bank.is_owner_if_bank_global()
    async def casinoset(self, _: commands.Context):
        """Settings for the Casino cog."""
        pass

    @casinoset.command(name="bjmin", aliases=["blackjackmin"])
    async def casinoset_bjmin(self, ctx: commands.Context, bid: Optional[int]):
        """The minimum bid for blackjack."""
        assert ctx.guild
        is_global = await bank.is_global()
        config_bjmin = self.config.bjmin if is_global else self.config.guild(ctx.guild).bjmin
        currency = await bank.get_currency_name(None if is_global else ctx.guild)
        if bid is None:
            bid = await config_bjmin()
            return await ctx.send(f"Current minimum bid for Blackjack is {bid} {currency}.")
        if bid < 1:
            return await ctx.send("Bid must be a positive number.")
        await config_bjmin.set(bid)
        await ctx.send(f"New minimum bid for Blackjack is {bid} {currency}.")

    @casinoset.command(name="bjmax", aliases=["blackjackmax"])
    async def casinoset_bjmax(self, ctx: commands.Context, bid: Optional[int]):
        """The maximum bid for blackjack."""
        assert ctx.guild
        is_global = await bank.is_global()
        config_bjmax = self.config.bjmax if is_global else self.config.guild(ctx.guild).bjmax
        currency = await bank.get_currency_name(None if is_global else ctx.guild)
        if bid is None:
            bid = await config_bjmax()
            return await ctx.send(f"Current maximum bid for Blackjack is {bid} {currency}.")
        if bid < 1:
            return await ctx.send("Bid must be a positive number.")
        await config_bjmax.set(bid)
        await ctx.send(f"New maximum bid for Blackjack is {bid} {currency}.")

    @casinoset.command(name="pokermin")
    async def casinoset_pokermin(self, ctx: commands.Context, bet: Optional[int]):
        """The minimum bet for Poker."""
        assert ctx.guild
        is_global = await bank.is_global()
        config_pokermin = self.config.pokermin if is_global else self.config.guild(ctx.guild).pokermin
        currency = await bank.get_currency_name(None if is_global else ctx.guild)
        if bet is None:
            bet = await config_pokermin()
            return await ctx.send(f"Current minimum bet in Poker is {bet} {currency}.")
        if bet < POKER_MINIMUM_BET:
            return await ctx.send("Bid must be a positive number.")
        await config_pokermin.set(bet)
        await ctx.send(f"New minimum bet in Poker is {bet} {currency}.")

    @casinoset.command(name="coinfreespin")
    @bank.is_owner_if_bank_global()
    async def casinoset_coinfreespin(self, ctx: commands.Context):
        """
        Toggles whether a coin in the slot machine will give a free spin.
        This increases the expected player returns from 68% to 91%, which is similar to real slot machines.
        """
        assert ctx.guild
        is_global = await bank.is_global()
        config_value = self.config.coinfreespin if is_global else self.config.guild(ctx.guild).coinfreespin
        value = await config_value()
        await config_value.set(not value)
        if not value:
            await ctx.send(f"Coins will give free spins. Expected player returns: 91%")
        else:
            await ctx.send(f"Coins won't give free spins. Expected player returns: 68%")


async def setup(bot: Red):
    global old_slot, old_payouts
    old_slot = bot.get_command("slot")
    old_payouts = bot.get_command("payouts")
    if old_slot and old_payouts:
        bot.remove_command(old_slot.name)
        bot.remove_command(old_payouts.name)
        await bot.add_cog(Casino(bot))
    else:
        async def add_cog():
            global old_slot, old_payouts
            await asyncio.sleep(1)  # hopefully economy cog has finished loading
            old_slot = bot.get_command("slot")
            old_payouts = bot.get_command("payouts")
            if old_slot and old_payouts:
                bot.remove_command(old_slot.name)
                bot.remove_command(old_payouts.name)
            await bot.add_cog(Casino(bot))
        _ = asyncio.create_task(add_cog())
