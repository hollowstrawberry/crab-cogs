import logging
import asyncio
import discord
import calendar
import aiofiles
from typing import List, Optional, Union
from datetime import datetime
from redbot.core import commands, app_commands, bank
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path
from redbot.cogs.economy.economy import Economy
from redbot.core.utils.chat_formatting import humanize_number
from redbot.core.utils.chat_formatting import humanize_timedelta

from simplecasino.base import BaseCasinoCog
from simplecasino.slots import slots
from simplecasino.poker import PokerGame
from simplecasino.blackjack import Blackjack
from simplecasino.utils import DISCORD_RED, POKER_MINIMUM_BET, POKER_RULES
from simplecasino.views.again_view import AgainView
from simplecasino.views.replace_view import ReplaceView

log = logging.getLogger("red.crab-cogs.simplecasino")

old_slot: Optional[commands.Command] = None
old_payouts: Optional[commands.Command] = None
old_blackjack: Optional[commands.Command] = None

MAX_CONCURRENT_SLOTS = 3
MAX_APP_EMOJIS = 2000
POKER_AFK_LIMIT = 10  # minutes
STARTING = "Starting game..."


class SimpleCasino(BaseCasinoCog):
    """Gamble virtual currency with Poker, Blackjack, and Slot Machines."""

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
                if game.players and not game.is_finished:
                    self.poker_games[cid] = game
                    if game.view:
                        self.bot.add_view(game.view)
            except Exception:
                log.error(f"Loading game in {cid}", exc_info=True)

        # Load custom emojis into config, creating them if necessary
        all_emojis = await self.bot.fetch_application_emojis()
        for emoji_name in ("dealer", "smallblind", "bigblind", "spades", "clubs"):
            emoji = next((emoji for emoji in all_emojis if emoji.name == emoji_name), None)
            if not emoji and len(all_emojis) < MAX_APP_EMOJIS:
                async with aiofiles.open(bundled_data_path(self) / f"{emoji_name}.png", "rb") as fp:
                    image = await fp.read()
                emoji = await self.bot.create_application_emoji(name=emoji_name, image=image)
            if emoji:
                await self.config.__getattr__("emoji_" + emoji_name).set(str(emoji))

    def cog_unload(self):
        global old_slot, old_payouts
        # clear views
        for game in self.poker_games.values():
            if game.view:
                game.view.stop()
        # restore old commands
        if old_slot:
            self.bot.remove_command(old_slot.name)
            self.bot.add_command(old_slot)
        if old_payouts:
            self.bot.remove_command(old_payouts.name)
            self.bot.add_command(old_payouts)
        if old_blackjack:
            self.bot.remove_command(old_blackjack.name)
            self.bot.add_command(old_blackjack)

    async def get_economy_cog(self, ctx: Union[discord.Interaction, commands.Context]) -> Optional[Economy]:
        cog: Optional[Economy] = self.bot.get_cog("Economy")  # type: ignore
        if cog:
            return cog
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message
        await reply("Economy cog not loaded! Contact the bot owner for more information.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    

    @commands.hybrid_command(name="blackjack", aliases=["bj"])
    @app_commands.describe(bet="How much currency to bet.")
    @commands.guild_only()
    async def blackjack_cmd(self, ctx: commands.Context, bet: int):
        """Play Blackjack against the bot. Get as close to 21 as possible!"""
        await self.blackjack(ctx, bet)

    async def blackjack(self, ctx: Union[discord.Interaction, commands.Context], bet: int):
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message
        assert ctx.guild and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)

        minimum_bid = await self.config.bjmin() if await bank.is_global() else await self.config.guild(ctx.guild).bjmin()
        maximum_bid = await self.config.bjmax() if await bank.is_global() else await self.config.guild(ctx.guild).bjmax()
        currency_name = await bank.get_currency_name(ctx.guild)
        if bet < 1 or bet < minimum_bid:
            return await reply(f"Your bet must be at least {humanize_number(minimum_bid)} {currency_name}", ephemeral=True)
        elif bet > maximum_bid:
            return await reply(f"Your bet cannot be greater than {humanize_number(maximum_bid)} {currency_name}", ephemeral=True)
        if not await bank.can_spend(author, bet):
            return await reply("You ain't got enough money, friend.", ephemeral=True)
        
        await bank.withdraw_credits(author, bet)
        include_author = isinstance(ctx, discord.Interaction) and ctx.type == discord.InteractionType.component
        blackjack = Blackjack(self, author, ctx.channel, bet, await self.bot.get_embed_color(ctx.channel), include_author)
        await blackjack.check_payout()
        view = AgainView(self.blackjack, bet, None, currency_name) if blackjack.is_over() else blackjack
        message = await reply(embed=await blackjack.get_embed(), view=view, allowed_mentions=discord.AllowedMentions.none())
        if isinstance(view, AgainView):
            view.message = message if isinstance(ctx, commands.Context) else await ctx.original_response()  # type: ignore


    @commands.hybrid_command(name="slot", aliases=["slots"])
    @commands.guild_only()
    @app_commands.describe(bet="How much currency to put in the slot machine.")
    async def slot_cmd(self, ctx: commands.Context, bet: int):
        """Play the slot machine."""
        try:
            if not ctx.interaction:
                self.concurrent_slots += 1
            await self.slot(ctx, bet)
        finally:
            if not ctx.interaction:
                self.concurrent_slots -= 1

    async def slot(self, ctx: Union[discord.Interaction, commands.Context], bet: int):
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message
        assert ctx.guild and isinstance(author, discord.Member)

        if not (economy := await self.get_economy_cog(ctx)):
            return

        if self.concurrent_slots > MAX_CONCURRENT_SLOTS and isinstance(ctx, commands.Context) and not ctx.interaction:
            content = f"Too many people are using the slot machine right now. "
            if self.bot.tree.get_command("slot") is None:
                content += "The bot owner could enable the `/slot` slash command, which would allow more people to use it at the same time."
            else:
                content += "Consider using the `/slot` slash command instead, which allows more people to use it at the same time."
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
        if bet < min_bid:
            await reply(f"Your bet must be at least {humanize_number(min_bid)} {currency_name}")
            return
        if bet > max_bid:
            await reply(f"Your bet cannot be greater than {humanize_number(max_bid)} {currency_name}")
            return
        if not await bank.can_spend(author, bet):
            await reply("You ain't got enough money, friend.")
            return
        
        if is_global:
            await economy.config.user(author).last_slot.set(cur_time)
        else:
            await economy.config.member(author).last_slot.set(cur_time)

        await slots(self, ctx, bet)


    @commands.command(name="poker")
    @commands.guild_only()
    async def poker_cmd(self, ctx: commands.Context, starting_bet: Optional[int]):
        """Start a new game of Poker with no players."""
        assert isinstance(ctx.author, discord.Member)
        await self.poker(ctx, [ctx.author], starting_bet)

    poker_app = app_commands.Group(name="poker", description="Play Texas Hold'em Poker with up to 8 people!", guild_only=True)

    @poker_app.command(name="new")
    @app_commands.describe(starting_bet="This bet may increase during the game.")
    async def poker_app_new(self, interaction: discord.Interaction, starting_bet: Optional[int]):
        """Start a new game of Poker with no players."""
        ctx = await commands.Context.from_interaction(interaction)
        assert isinstance(ctx.author, discord.Member)
        await self.poker(ctx, [ctx.author], starting_bet)

    @poker_app.command(name="rules")
    async def poker_app_rules(self, interaction: discord.Interaction):
        """Show the rules for Poker in this bot."""
        embed = discord.Embed(color=DISCORD_RED)
        bigblind_emoji = await self.config.emoji_bigblind()
        embed.title = f"{bigblind_emoji} Texas Hold'em Poker - Rules summary"
        embed.description = POKER_RULES
        filename = "pokerhands.jpg"
        file = discord.File(bundled_data_path(self) / filename, filename=filename)
        embed.set_image(url=f"attachment://{filename}")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    async def poker(self, ctx: Union[discord.Interaction, commands.Context], players: List[discord.Member], starting_bet: Optional[int]) -> bool:
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        assert ctx.guild and isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
        
        reply = ctx.reply if isinstance(ctx, commands.Context) else ctx.response.send_message

        minimum_starting_bet: int = await self.config.pokermin() if await bank.is_global() else await self.config.guild(ctx.guild).pokermin()
        maximum_starting_bet: int = await self.config.pokermax() if await bank.is_global() else await self.config.guild(ctx.guild).pokermax()
        currency_name = await bank.get_currency_name(ctx.guild)
        if starting_bet is None:
            starting_bet = minimum_starting_bet
        elif starting_bet < minimum_starting_bet:
            await reply(f"The starting bet must be at least {minimum_starting_bet} {currency_name}.")
            return False
        elif starting_bet > maximum_starting_bet:
            await reply(f"The starting bet must not be greater than {maximum_starting_bet} {currency_name}.")
            return False
        if not await bank.can_spend(author, starting_bet):
            await reply(f"You don't have enough {currency_name} to make that bet.")
            return False

        # Game already exists
        if ctx.channel.id in self.poker_games and not self.poker_games[ctx.channel.id].is_finished:
            if len(players) > 1:  # rematch
                await reply("Another game of Poker has already begun in this channel.", ephemeral=True)
                return False
            
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
                    nonlocal ctx, author, old_game, old_message
                    assert isinstance(author, discord.Member) and isinstance(ctx.channel, discord.TextChannel)
                    await old_game.cancel()
                    if old_message:
                        try:
                            await old_message.delete()
                        except discord.NotFound:
                            pass
                    game = PokerGame(self, players, ctx.channel, starting_bet)
                    self.poker_games[ctx.channel.id] = game
                    await game.update_message()

                content = f"Someone else is playing Checkers in this channel, here: {old_message.jump_url}, " \
                          f"but {humanize_timedelta(seconds=seconds_passed)} have passed since their last interaction. Do you want to start a new game?"
                embed = discord.Embed(title="Confirmation", description=content, color=await self.bot.get_embed_color(ctx.channel))
                view = ReplaceView(self, callback, author)
                message = await reply(embed=embed, view=view)
                view.message = message if isinstance(ctx, commands.Context) else await ctx.original_response()  # type: ignore
                return False
            
            else:
                content = f"There is still an active game in this channel, here: {old_message.jump_url}\nTry again in a few minutes"
                permissions = ctx.channel.permissions_for(author)
                content += " or consider creating a thread." if permissions.create_public_threads or permissions.create_private_threads else "."
                await reply(content, ephemeral=True)
                return False
        
        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(STARTING, ephemeral=True)
        elif ctx.interaction:
            await ctx.interaction.response.send_message(STARTING, ephemeral=True)

        # New game
        game = PokerGame(self, players, ctx.channel, starting_bet)
        self.poker_games[ctx.channel.id] = game
        await game.update_message()
        return True


    @commands.command(name="blackjackstats", aliases=["bjstats"])
    @commands.guild_only()
    async def blackjackstats(self, ctx: commands.Context, member: Optional[discord.Member]):
        """View your own or someone else's stats in Blackjack."""
        assert isinstance(ctx.author, discord.Member)
        member = member or ctx.author
        stats = await self.config.user(member).all() if await bank.is_global() else await self.config.member(member).all()
        currency_name = await bank.get_currency_name(ctx.guild)
        embed = discord.Embed(title="2️⃣1️⃣ Blackjack Stats", color=await self.bot.get_embed_color(ctx.channel))
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.add_field(name="Times played", value=humanize_number(stats["bjcount"]))
        embed.add_field(name="Total betted", value=f"{humanize_number(stats['bjbetted'])} {currency_name}")
        embed.add_field(name="Total payout", value=f"{humanize_number(stats['bjprofit'])} {currency_name}")
        embed.add_field(name="Wins", value=humanize_number(stats["bjwincount"]))
        embed.add_field(name="Losses", value=humanize_number(stats["bjlosscount"]))
        embed.add_field(name="Ties", value=humanize_number(stats["bjtiecount"]))
        embed.add_field(name="21s gotten", value=humanize_number(stats["bj21count"]))
        embed.add_field(name="Blackjacks gotten", value=humanize_number(stats["bjnatural21count"]))
        await ctx.send(embed=embed)

    @commands.command(name="slotstats", aliases=["slotsstats"])
    @commands.guild_only()
    async def slotstats(self, ctx: commands.Context, member: Optional[discord.Member]):
        """View your own or someone else's stats in the Slot machine."""
        assert ctx.guild and isinstance(ctx.author, discord.Member)
        member = member or ctx.author
        is_global = await bank.is_global()
        stats = await self.config.user(member).all() if is_global else await self.config.member(member).all()
        currency_name = await bank.get_currency_name(ctx.guild)
        embed = discord.Embed(title="7️⃣ Slot Machine Stats", color=await self.bot.get_embed_color(ctx.channel))
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.add_field(name="Times played", value=humanize_number(stats["slotcount"]))
        embed.add_field(name="Total betted", value=f"{humanize_number(stats['slotbetted'])} {currency_name}")
        embed.add_field(name="Total payout", value=f"{humanize_number(stats['slotprofit'])} {currency_name}")
        freespinenabled = await self.config.coinfreespin() if is_global else await self.config.guild(ctx.guild).coinfreespin()
        if freespinenabled:
            embed.add_field(name="Free spins", value=humanize_number(stats["slotfreespincount"]))
        embed.add_field(name="2 symbol payouts", value=humanize_number(stats["slot2symbolcount"]))
        embed.add_field(name="3 symbol payouts", value=humanize_number(stats["slot3symbolcount"]))
        embed.add_field(name="Jackpots", value=humanize_number(stats["slotjackpotcount"]))
        embed.add_field(name="Jackpot near-misses", value=humanize_number(stats["slotjackpotwhiffcount"]))
        await ctx.send(embed=embed)


    casinostats_app = app_commands.Group(name="casinostats", description="View your stats in Blackjack and Slots.", guild_only=True)

    @casinostats_app.command(name="blackjack")
    @app_commands.describe(member="The user to view stats for. Views your own stats by default.")
    async def blackjackstats_app(self, interaction: discord.Interaction, member: Optional[discord.Member]):
        """View your or someone else's stats with Blackjack."""
        ctx = await commands.Context.from_interaction(interaction)
        await self.blackjackstats(ctx, member)

    @casinostats_app.command(name="slot")
    @app_commands.describe(member="The user to view stats for. Views your own stats by default.")
    async def slotstats_app(self, interaction: discord.Interaction, member: Optional[discord.Member]):
        """View your or someone else's stats with the Slot Machine."""
        ctx = await commands.Context.from_interaction(interaction)
        await self.slotstats(ctx, member)


    @commands.group(name="simplecasinoset", aliases=["setcasino"])  # type: ignore
    @commands.admin_or_permissions(manage_guild=True)
    @bank.is_owner_if_bank_global()
    async def simplecasinoset(self, _: commands.Context):
        """Settings for the SimpleCasino cog."""
        pass

    @simplecasinoset.command(name="bjmin", aliases=["blackjackmin"])
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

    @simplecasinoset.command(name="bjmax", aliases=["blackjackmax"])
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

    @simplecasinoset.command(name="pokermin")
    async def casinoset_pokermin(self, ctx: commands.Context, bet: Optional[int]):
        """The minimum starting bet for Poker."""
        assert ctx.guild
        is_global = await bank.is_global()
        config_pokermin = self.config.pokermin if is_global else self.config.guild(ctx.guild).pokermin
        config_pokermax = self.config.pokermax if is_global else self.config.guild(ctx.guild).pokermax
        currency = await bank.get_currency_name(None if is_global else ctx.guild)
        if bet is None:
            min_bet = await config_pokermin()
            return await ctx.send(f"Current minimum **starting bet** in Poker is {humanize_number(min_bet)} {currency}.\n"
                                  f"The maximum bet with this starting bet will be 100x, so {humanize_number(min_bet * 100)} {currency}.")
        if bet < POKER_MINIMUM_BET:
            return await ctx.send(f"You cannot set a minimum starting bet for Poker lower than {POKER_MINIMUM_BET} {currency}.")
        await config_pokermin.set(bet)
        if await config_pokermax() < bet:  # maximum bet can't be lower than the minimum bet
            await config_pokermax.set(bet)
        await ctx.send(f"New minimum **starting bet** in Poker is {humanize_number(bet)} {currency}.\n"
                       f"The maximum bet with this starting bet will be 100x, so {humanize_number(bet * 100)} {currency}.")
        
    @simplecasinoset.command(name="pokermax")
    async def casinoset_pokermax(self, ctx: commands.Context, bet: Optional[int]):
        """The maximum starting bet for Poker."""
        assert ctx.guild
        is_global = await bank.is_global()
        config_pokermax = self.config.pokermax if is_global else self.config.guild(ctx.guild).pokermax
        config_pokermin = self.config.pokermin if is_global else self.config.guild(ctx.guild).pokermin
        currency = await bank.get_currency_name(None if is_global else ctx.guild)
        if bet is None:
            max_bet: int = await config_pokermax()
            return await ctx.send(f"Current maximum **starting bet** in Poker is {humanize_number(max_bet)} {currency}.\n"
                                  f"The maximum bet with this starting bet will be 100x, so {humanize_number(max_bet * 100)} {currency}.")
        min_bet: int = await config_pokermin()
        if bet < min_bet:
            return await ctx.send(f"The maximum starting bet cannot be lower than the minimum starting bet, which is currently {humanize_number(min_bet)} {currency}.")
        await config_pokermax.set(bet)
        await ctx.send(f"New maximum **starting bet** in Poker is {humanize_number(bet)} {currency}.\n"
                       f"The maximum bet with this starting bet will be 100x, so {humanize_number(bet * 100)} {currency}.")

    @simplecasinoset.command(name="coinfreespin")
    @bank.is_owner_if_bank_global()
    async def casinoset_coinfreespin(self, ctx: commands.Context):
        """
        Toggles whether a coin in the slot machine will give a free spin.
        This increases the expected player returns to be similar to real slot machines.
        """
        assert ctx.guild
        is_global = await bank.is_global()
        config_value = self.config.coinfreespin if is_global else self.config.guild(ctx.guild).coinfreespin
        value = await config_value()
        await config_value.set(not value)
        if not value:
            await ctx.send(f"Coins will give free spins in the slot machine.")
        else:
            await ctx.send(f"Coins won't give free spins in the slot machine.")

    @simplecasinoset.command(name="sloteasy")
    @bank.is_owner_if_bank_global()
    async def casinoset_sloteasy(self, ctx: commands.Context):
        """
        Removes one of the symbols from the slot machine, further increasing the expected player returns into a very slightly net positive.
        """
        assert ctx.guild
        is_global = await bank.is_global()
        config_value = self.config.sloteasy if is_global else self.config.guild(ctx.guild).sloteasy
        value = await config_value()
        await config_value.set(not value)
        if not value:
            await ctx.send(f"Removed the 10th symbol from the slot machine.")
        else:
            await ctx.send(f"Added back the 10th symbol to the slot machine.")


async def setup(bot: Red):
    async def add_cog():
        global old_slot, old_payouts, old_blackjack
        await asyncio.sleep(1)  # hopefully economy cog has finished loading

        if old_slot := bot.get_command("slot"):
            bot.remove_command(old_slot.name)
        if old_payouts := bot.get_command("payouts"):
            bot.remove_command(old_payouts.name)
        if old_blackjack := bot.get_command("blackjack"):  # so we can load this cog alongside jumper-plugins's casino
            bot.remove_command(old_blackjack.name)

        await bot.add_cog(SimpleCasino(bot))
        await bot.tree.red_check_enabled()  # type: ignore  # register slash commands

    _ = asyncio.create_task(add_cog())
