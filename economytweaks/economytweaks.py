import calendar
import asyncio
import discord
from typing import Optional
from datetime import datetime, timedelta, timezone

from redbot.core import Config, commands, app_commands, bank, errors
from redbot.core.bot import Red
from redbot.cogs.economy.economy import Economy
from redbot.core.utils.chat_formatting import humanize_number
from redbot.core.commands.converter import TimedeltaConverter

old_payday: Optional[commands.Command] = None


class EconomyTweaks(commands.Cog):
    """Adds slash commands for the economy cog and a configurable bonus for the payday command."""

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.concurrent_slots = 0
        default_timer = {
            "last_payday_bonus": 0,
        }
        default_config = {
            "bonus_amount": 1000,
            "bonus_time": 86400,
        }
        self.config = Config.get_conf(self, identifier=557574777)
        self.config.register_user(**default_timer)
        self.config.register_member(**default_timer)
        self.config.register_global(**default_config)
        self.config.register_guild(**default_config)

    def cog_unload(self):
        global old_payday
        if old_payday:
            self.bot.remove_command(old_payday.name)
            self.bot.add_command(old_payday)

    async def get_economy_cog(self, ctx: commands.Context) -> Optional[Economy]:
        cog: Optional[Economy] = self.bot.get_cog("Economy")  # type: ignore
        if cog:
            return cog
        await ctx.reply("Economy cog not loaded! Contact the bot owner for more information.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


    @commands.hybrid_command(name="payday")
    @commands.guild_only()
    async def payday(self, ctx: commands.Context):
        """
        Get some free currency.
        """
        assert ctx.guild and isinstance(ctx.author, discord.Member)
        guild = ctx.guild
        author = ctx.author
        mention = "" if ctx.interaction else f"{author.mention} "

        if not (economy := await self.get_economy_cog(ctx)):
            return

        cur_time = calendar.timegm(ctx.message.created_at.utctimetuple())
        credits_name = await bank.get_currency_name(guild)
        is_global = await bank.is_global()
        if is_global:
            next_payday = await economy.config.user(author).next_payday() + await economy.config.PAYDAY_TIME()
            bonus_time = await self.config.bonus_time()
            next_payday_bonus = await self.config.user(author).last_payday_bonus() + bonus_time
            payday_amount = await economy.config.PAYDAY_CREDITS()
            bonus_amount = await self.config.bonus_amount()
        else:
            next_payday = await economy.config.member(author).next_payday() + await economy.config.guild(guild).PAYDAY_TIME()
            bonus_time = await self.config.guild(guild).bonus_time()
            next_payday_bonus = await self.config.member(author).last_payday_bonus() + bonus_time
            payday_amount = await economy.config.guild(guild).PAYDAY_CREDITS()
            bonus_amount = await self.config.guild(guild).bonus_amount()

        if cur_time < next_payday:
            now = datetime.now(timezone.utc)
            relative_time = discord.utils.format_dt(now + timedelta(seconds=next_payday - cur_time), "R")
            relative_bonus = discord.utils.format_dt(now + timedelta(seconds=max(next_payday - cur_time, next_payday_bonus - cur_time)), "R")
            content = f"{mention}Too soon. Your next payday is {relative_time}."
            if bonus_amount > 0 and bonus_amount > payday_amount:
                content += f" Your next bonus is {relative_bonus}."
            return await ctx.send(content, ephemeral=True)

        is_bonus = cur_time >= next_payday_bonus and bonus_amount > 0 and bonus_amount > payday_amount
        reward = bonus_amount if is_bonus else payday_amount
        if not is_global:
            for role in author.roles:
                role_reward = await economy.config.role(role).PAYDAY_CREDITS()
                if role_reward > reward:
                    reward = role_reward

        if is_global:
            await economy.config.user(author).next_payday.set(cur_time)
            if is_bonus:
                await self.config.user(author).last_payday_bonus.set(cur_time)
        else:
            await economy.config.member(author).next_payday.set(cur_time)
            if is_bonus:
                await self.config.member(author).last_payday_bonus.set(cur_time)

        try:
            await bank.deposit_credits(author, reward)
        except errors.BalanceTooHigh as exc:
            await bank.set_balance(author, exc.max_balance)
            return await ctx.send(f"{mention}You've reached the maximum amount of {credits_name}!"
                                  f" You currently have {humanize_number(exc.max_balance)} {credits_name}", ephemeral=True)

        pos = await bank.get_leaderboard_position(author)
        position = f"#{humanize_number(pos)}" if pos else "unknown"
        amount = humanize_number(reward)
        new_balance = humanize_number(await bank.get_balance(author))
        if is_bonus:
            relative_time = discord.utils.format_dt(datetime.now(timezone.utc) + timedelta(seconds=bonus_time), "R")
            await ctx.send(f"{mention}Bonus! Take {amount} {credits_name}. You now have {new_balance} {credits_name}!"
                           f"\nYou are currently {position} on the leaderboard."
                           f"\nNext bonus {relative_time}", ephemeral=True)
        else:
            await ctx.send(f"{mention}Here, take {amount} {credits_name}. You now have {new_balance} {credits_name}!"
                           f"\nYou are currently {position} on the leaderboard.", ephemeral=True)


    @app_commands.command(name="leaderboard")
    @app_commands.describe(top="How many positions on the leaderboard to show. 10 by default.",
                           show_global="Whether to include results from all servers. False by default.")
    @app_commands.guild_only()
    async def leaderboard_app(self, interaction: discord.Interaction, top: app_commands.Range[int, 1, 1000] = 10, show_global: bool = False):
        """Views the economy leaderboard."""
        ctx = await commands.Context.from_interaction(interaction)
        if not (economy := await self.get_economy_cog(ctx)):
            return
        await economy.leaderboard(ctx, top=top, show_global=show_global)


    bank_app = app_commands.Group(name="bank", description="Manage your currency with the bot.", guild_only=True)

    @bank_app.command(name="balance")
    @app_commands.describe(user="The user to check the balance of. If omitted, defaults to your own balance.")
    @app_commands.guild_only()
    async def balance_app(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """Show the user's account balance."""
        assert isinstance(interaction.user, discord.Member)
        user = user or interaction.user
        bal = humanize_number(await bank.get_balance(user))
        currency = await bank.get_currency_name(interaction.guild)
        content = f"Your balance is {bal} {currency}." if user == interaction.user else f"{user.mention}'s balance is {bal} {currency}."
        await interaction.response.send_message(content, ephemeral=True)


    @bank_app.command(name="transfer")
    @app_commands.describe(to="The user to give currency to.",
                           amount="The amount of currency to give.")
    @app_commands.guild_only()
    async def transfer_app(self, interaction: discord.Interaction, to: discord.Member, amount: app_commands.Range[int, 1]):
        """Transfer currency to other users."""
        try:
            await bank.transfer_credits(interaction.user, to, amount)
        except (ValueError, errors.BalanceTooHigh) as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        currency = await bank.get_currency_name(interaction.guild)
        await interaction.response.send_message(f"Transferred {humanize_number(amount)} {currency} to {to.mention}")


    @commands.group(name="economytweakset", aliases=["economytweaksset"])  # type: ignore
    @commands.admin_or_permissions(manage_guild=True)
    async def economytweakset(self, ctx: commands.Context):
        """Settings for the economytweaks cog."""
        pass

    @economytweakset.command(name="bonusamount")
    @bank.is_owner_if_bank_global()
    async def economytweakset_bonusamount(self, ctx: commands.Context, creds: Optional[int]):
        """Set the amount earned with each payday bonus, must be greater than the payday amount itself, 0 to disable"""
        assert ctx.guild
        is_global = await bank.is_global()
        config_amount = self.config.bonus_amount if is_global else self.config.guild(ctx.guild).bonus_amount
        currency = await bank.get_currency_name(None if is_global else ctx.guild)
        if creds is None:
            creds = await config_amount()
            return await ctx.send(f"Current payday bonus is {creds} {currency}.")
        if creds < 0:
            return await ctx.send("Payout must be a positive number or 0.")
        await config_amount.set(creds)
        await ctx.send(f"Current payday bonus is {creds} {currency}.")

    @economytweakset.command(name="bonustime")
    @bank.is_owner_if_bank_global()
    async def economytweakset_bonustime(self, ctx: commands.Context, *, duration: TimedeltaConverter(default_unit="seconds")):  # type: ignore
        """Set the time between each payday bonus. Example: 24 hours"""
        assert ctx.guild
        is_global = await bank.is_global()
        config_time = self.config.bonus_time if is_global else self.config.guild(ctx.guild).bonus_time
        if duration is None:
            seconds = await config_time()
            return await ctx.send(f"Current payday bonus time is {seconds} seconds.")
        seconds = duration.total_seconds()
        await config_time.set(seconds)
        await ctx.send(f"Current payday bonus time is {seconds} seconds.")


async def setup(bot: Red):
    global old_payday
    old_payday = bot.get_command("payday")
    if old_payday:
        bot.remove_command(old_payday.name)
        await bot.add_cog(EconomyTweaks(bot))
    else:
        async def add_cog():
            global old_payday
            await asyncio.sleep(1)  # hopefully economy cog has finished loading
            old_payday = bot.get_command("payday")
            if old_payday:
                bot.remove_command(old_payday.name)
            await bot.add_cog(EconomyTweaks(bot))
        _ = asyncio.create_task(add_cog())
