import random
import asyncio
import discord
from typing import List
from redbot.core import bank, errors
from redbot.core.utils.chat_formatting import humanize_number

from simplecasino.base import BaseCasinoCog
from simplecasino.card import Card, CardValue, CARD_EMOJI, make_deck
from simplecasino.views.again_view import AgainView


TWENTYONE = 21
DEALER_STAND = 17
ERROR_PLAYER = "You're not the one playing!"


def get_hand_value(hand: List[Card]) -> int:
    total = 0
    aces = 0
    for card in hand:
        if card.value == CardValue.ACE:
            aces += 1
            total += 11  # assume Ace is 11 for now
        else:
            total += min(10, card.value.value)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


class BlackjackHand:
    """Represents a single blackjack hand"""
    def __init__(self, cards: List[Card], bet: int, is_split: bool = False, is_doubled: bool = False):
        self.cards = cards
        self.bet = bet
        self.is_split = is_split
        self.is_doubled = is_doubled
        self.is_complete = False
    
    def get_value(self) -> int:
        return get_hand_value(self.cards)
    
    def can_split(self) -> bool:
        """Check if this hand can be split"""
        if len(self.cards) != 2 or self.is_split:
            return False
        # Cards can be split if they have the same rank (10, J, Q, K all count as 10)
        val1 = min(10, self.cards[0].value.value) if self.cards[0].value != CardValue.ACE else 11
        val2 = min(10, self.cards[1].value.value) if self.cards[1].value != CardValue.ACE else 11
        return val1 == val2
    
    def can_double(self) -> bool:
        """Check if this hand can be doubled"""
        return len(self.cards) == 2 and not self.is_doubled


class Blackjack(discord.ui.View):
    def __init__(self,
                 cog: BaseCasinoCog,
                 player: discord.Member,
                 channel: discord.TextChannel,
                 bet: int,
                 embed_color: discord.Color,
                 include_author: bool,
                 ):
        super().__init__(timeout=None)
        self.cog = cog
        self.player = player
        self.channel = channel
        self.initial_bet = bet
        self.embed_color = embed_color
        self.include_author = include_author
        self.dealer: List[Card] = []
        self.hands: List[BlackjackHand] = []
        self.current_hand_index = 0
        self.deck = make_deck()
        random.shuffle(self.deck)
        
        # Deal initial cards
        initial_cards = [self.deck.pop(), self.deck.pop()]
        self.hands.append(BlackjackHand(initial_cards, bet))
        self.dealer.append(self.deck.pop())
        self.dealer.append(self.deck.pop())
        
        self.facedown = True
        self.dealer_turn_started = False
        self.payout_done = False
        self.total_bet = bet

        # Create buttons
        self.hit_button = discord.ui.Button(label="Hit", style=discord.ButtonStyle.green)
        self.stand_button = discord.ui.Button(label="Stand", style=discord.ButtonStyle.red)
        self.double_button = discord.ui.Button(label="Double", style=discord.ButtonStyle.blurple)
        self.split_button = discord.ui.Button(label="Split", style=discord.ButtonStyle.grey)
        
        self.hit_button.callback = self.hit
        self.stand_button.callback = self.stand
        self.double_button.callback = self.double_down
        self.split_button.callback = self.split
        
        self.update_buttons()

    def update_buttons(self):
        """Update which buttons are available based on current hand"""
        self.clear_items()
        
        current_hand = self.hands[self.current_hand_index]
        
        # Check if current hand has blackjack
        if current_hand.get_value() == TWENTYONE and len(current_hand.cards) == 2:
            current_hand.is_complete = True
            self._move_to_next_hand()
            return
        
        # Add appropriate buttons
        if current_hand.get_value() < TWENTYONE and not current_hand.is_doubled:
            self.add_item(self.hit_button)
            self.add_item(self.stand_button)
            
            # Can only double or split on initial 2 cards
            if current_hand.can_double():
                self.add_item(self.double_button)
            
            if current_hand.can_split() and len(self.hands) < 4:  # Limit to 4 hands
                self.add_item(self.split_button)
        elif current_hand.is_doubled or current_hand.get_value() >= TWENTYONE:
            current_hand.is_complete = True
            self._move_to_next_hand()

    def _move_to_next_hand(self):
        """Move to the next hand or start dealer turn"""
        self.current_hand_index += 1
        if self.current_hand_index < len(self.hands):
            self.update_buttons()
        else:
            self.facedown = False
            self.dealer_turn_started = True

    def is_over(self) -> bool:
        """Check if the entire game is over"""
        if not self.dealer_turn_started:
            return False
        
        dealer_total = get_hand_value(self.dealer)
        return dealer_total > TWENTYONE or dealer_total >= DEALER_STAND

    def is_tie(self, hand: BlackjackHand) -> bool:
        player_total = hand.get_value()
        dealer_total = get_hand_value(self.dealer)
        return player_total <= TWENTYONE and dealer_total <= TWENTYONE and player_total == dealer_total

    def is_win(self, hand: BlackjackHand) -> bool:
        player_total = hand.get_value()
        dealer_total = get_hand_value(self.dealer)
        if player_total > TWENTYONE:
            return False
        if dealer_total > TWENTYONE:
            return True
        return player_total > dealer_total
    
    def payout_amount(self, hand: BlackjackHand) -> int:
        """Calculate payout for a specific hand"""
        if self.is_tie(hand):
            return hand.bet  # Push - return bet
        if not self.is_win(hand):
            return 0
        
        player_total = hand.get_value()
        dealer_total = get_hand_value(self.dealer)
        is_player_natural = len(hand.cards) == 2 and player_total == TWENTYONE and not hand.is_split
        is_dealer_natural = len(self.dealer) == 2 and dealer_total == TWENTYONE
        
        # Natural blackjack pays 3:2 (but not on split hands)
        if is_player_natural and not is_dealer_natural:
            return hand.bet + (hand.bet * 3 // 2)
        else:
            return 2 * hand.bet

    def total_payout(self) -> int:
        """Calculate total payout across all hands"""
        return sum(self.payout_amount(hand) for hand in self.hands)

    async def get_embed(self) -> discord.Embed:
        currency_name = await bank.get_currency_name(self.channel.guild)
        dealer_str = " ".join("⬇️" if self.facedown and i == 1 else CARD_EMOJI[card.value] for i, card in enumerate(self.dealer))

        embed = discord.Embed(color=self.embed_color)
        embed.add_field(name=f"Dealer ({'?' if self.facedown else get_hand_value(self.dealer)})", value=dealer_str, inline=False)
        
        # Display all hands
        for idx, hand in enumerate(self.hands):
            hand_str = " ".join(CARD_EMOJI[card.value] for card in hand.cards)
            hand_label = f"Hand {idx + 1}" if len(self.hands) > 1 else "Hand"
            
            # Mark current hand and show bet
            if idx == self.current_hand_index and not self.dealer_turn_started and len(self.hands) > 1:
                hand_label += " ⬅️"
            
            status = ""
            if hand.is_doubled:
                status = " (Doubled)"
            elif hand.is_split:
                status = " (Split)"
            
            hand_label += f" ({hand.get_value()}{status})"
            embed.add_field(name=hand_label, value=hand_str, inline=False)
        
        embed.add_field(name="Total Bet", value=f"{humanize_number(self.total_bet)} {currency_name}")
        
        if self.dealer_turn_started and self.is_over():
            total_payout = self.total_payout()
            net_profit = total_payout - self.total_bet
            
            #embed.add_field(name="Total Payout", value=f"{humanize_number(total_payout)} {currency_name}")
            embed.add_field(name="Net Result", value=f"{'+' if net_profit > 0 else ''}{humanize_number(net_profit)} {currency_name}")
            embed.add_field(name="Balance", value=f"{humanize_number(await bank.get_balance(self.player))} {currency_name}")
            
            if net_profit > 0:
                embed.title = "🎉 Blackjack (Win)"
            elif net_profit == 0:
                embed.title = "👔 Blackjack (Tie)"
            else:
                embed.title = "💀 Blackjack (Lost)"
        else:
            embed.title = "Blackjack"

        if self.include_author:
            embed.set_footer(text=self.player.display_name, icon_url=self.player.display_avatar.url)

        return embed
    
    async def dealer_turn(self, interaction: discord.Interaction):
        """Execute the dealer's turn"""
        self.stop()
        self.facedown = False
        self.dealer_turn_started = True
        
        await self.check_payout()
        self.update_buttons()
        currency_name = await bank.get_currency_name(interaction.guild)
        view = AgainView(self.cog.blackjack, self.initial_bet, interaction.message, currency_name) if self.is_over() else self
        await interaction.response.edit_message(embed=await self.get_embed(), view=view)
        
        while not self.is_over():
            self.dealer.append(self.deck.pop())
            await asyncio.sleep(1)
            await self.check_payout()
            self.update_buttons()
            view = AgainView(self.cog.blackjack, self.initial_bet, interaction.message, currency_name) if self.is_over() else self
            await interaction.edit_original_response(embed=await self.get_embed(), view=view)

    async def check_payout(self):
        """Process payout when game is over"""
        if not self.payout_done and self.is_over():
            self.payout_done = True
            total_payout = self.total_payout()
            if total_payout > 0:
                try:
                    await bank.deposit_credits(self.player, total_payout)
                except errors.BalanceTooHigh:
                    await bank.deposit_credits(self.player, await bank.get_max_balance(self.channel.guild))

    async def hit(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            return await interaction.response.send_message(ERROR_PLAYER, ephemeral=True)
        
        current_hand = self.hands[self.current_hand_index]
        current_hand.cards.append(self.deck.pop())
        
        if current_hand.get_value() >= TWENTYONE:
            current_hand.is_complete = True
            self._move_to_next_hand()
            
            if self.dealer_turn_started:
                await self.dealer_turn(interaction)
            else:
                await interaction.response.edit_message(embed=await self.get_embed(), view=self)
        else:
            self.update_buttons()
            await interaction.response.edit_message(embed=await self.get_embed(), view=self)
        
    async def stand(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            return await interaction.response.send_message(ERROR_PLAYER, ephemeral=True)
        
        current_hand = self.hands[self.current_hand_index]
        current_hand.is_complete = True
        self._move_to_next_hand()
        
        if self.dealer_turn_started:
            await self.dealer_turn(interaction)
        else:
            await interaction.response.edit_message(embed=await self.get_embed(), view=self)
    
    async def double_down(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            return await interaction.response.send_message(ERROR_PLAYER, ephemeral=True)
        
        current_hand = self.hands[self.current_hand_index]
        
        # Check if player has enough balance for the split bet
        if not bank.can_spend(self.player, current_hand.bet):
            currency_name = await bank.get_currency_name(interaction.guild)
            return await interaction.response.send_message(f"You don't have enough {currency_name} to double down!", ephemeral=True)
        await bank.withdraw_credits(self.player, current_hand.bet)
        
        # Double the bet and mark as doubled
        self.total_bet += current_hand.bet
        current_hand.bet *= 2
        current_hand.is_doubled = True
        
        # Deal one card and automatically stand
        current_hand.cards.append(self.deck.pop())
        current_hand.is_complete = True
        self._move_to_next_hand()
        
        if self.dealer_turn_started:
            await self.dealer_turn(interaction)
        else:
            await interaction.response.edit_message(embed=await self.get_embed(), view=self)
    
    async def split(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            return await interaction.response.send_message(ERROR_PLAYER, ephemeral=True)
        
        current_hand = self.hands[self.current_hand_index]
        
        # Check if player has enough balance for the split bet
        if not bank.can_spend(self.player, current_hand.bet):
            currency_name = await bank.get_currency_name(interaction.guild)
            return await interaction.response.send_message(f"You don't have enough {currency_name} to split!", ephemeral=True)
        await bank.withdraw_credits(self.player, current_hand.bet)
        
        # Split the hand
        self.total_bet += current_hand.bet
        card1 = current_hand.cards[0]
        card2 = current_hand.cards[1]
        
        # First hand gets first card + new card
        current_hand.cards = [card1, self.deck.pop()]
        current_hand.is_split = True
        
        # Create second hand with second card + new card
        new_hand = BlackjackHand([card2, self.deck.pop()], current_hand.bet, is_split=True)
        self.hands.insert(self.current_hand_index + 1, new_hand)
        
        self.update_buttons()
        await interaction.response.edit_message(embed=await self.get_embed(), view=self)
