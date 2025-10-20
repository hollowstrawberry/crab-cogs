import json
import logging
import discord
from typing import List, Optional, Tuple, Dict, Union
from datetime import datetime
from dataclasses import dataclass, field
from dataclasses_json import DataClassJsonMixin, config
from redbot.core import bank, errors
from redbot.core.utils.chat_formatting import humanize_number

from simplecasino.base import BaseCasinoCog, BasePokerGame
from simplecasino.card import CARD_VALUE_STR, Card, CardSuit, CardValue
from simplecasino.utils import (HandType, PlayerState, PlayerType, PokerState, InsufficientFundsError, humanize_camel_case,
                                DISCORD_RED, EMPTY_ELEMENT, POKER_MAX_PLAYERS, POKER_STAGE_NAMES)
from simplecasino.views.poker_rematch_view import PokerRematchView
from simplecasino.views.poker_view import PokerView
from simplecasino.views.poker_waiting_view import PokerWaitingView

log = logging.getLogger("red.crab-cogs.simplecasino")


@dataclass
class HandResult(DataClassJsonMixin):
    type: HandType = field(metadata=config(encoder=lambda x: x.value, decoder=HandType))
    cards: List[Card]

    def __post_init__(self):
        if len(self.cards) != 5:
            raise RuntimeError("HandResult must contain exactly 5 cards")

    def _compare_key(self):
        # comparison key: (handtype, pokervalues...)
        return (int(self.type),) + tuple(c.poker_value for c in self.cards)

    def __lt__(self, other: "HandResult") -> bool:
        return self._compare_key() < other._compare_key()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HandResult):
            return False
        return self._compare_key() == other._compare_key()


@dataclass
class PokerPlayer(DataClassJsonMixin):
    id: int
    index: int
    type: PlayerType = field(init=False, metadata=config(encoder=lambda x: x.value, decoder=PlayerType))
    hand: List[Card] = field(default_factory=list)
    state: PlayerState = field(default=PlayerState.Pending, metadata=config(encoder=lambda x: x.value, decoder=PlayerState))
    total_betted: int = 0
    current_bet: int = 0
    hand_result: Optional[HandResult] = None
    winnings: int = 0

    def __post_init__(self):
        # type is min(index, Normal)
        self.type = PlayerType(min(self.index, PlayerType.Normal.value))

    def member(self, game: BasePokerGame) -> discord.Member:
        member = game.channel.guild.get_member(self.id)
        if not member:
            raise RuntimeError(f"Where did poker player with id {self.id} go?")
        return member

    async def bet(self, game: BasePokerGame, bet_amount: int) -> int:
        if bet_amount < self.current_bet:
            raise ValueError("New bet must be higher than previous")

        additional = bet_amount - self.current_bet
        if additional == 0:
            return 0

        member = self.member(game)

        bal = await bank.get_balance(member)
        if bal <= 0:
            raise InsufficientFundsError

        # all in
        if bal < additional:
            await bank.withdraw_credits(member, bal)
            self.total_betted += bal
            self.current_bet += bal
            self.state = PlayerState.AllIn
            return bal

        # normal bet
        await bank.withdraw_credits(member, additional)
        self.total_betted += additional
        self.current_bet = bet_amount
        return additional


class PokerGame(BasePokerGame):
    def __init__(self, cog: BaseCasinoCog, players: List[discord.Member], channel: Union[discord.TextChannel, discord.Thread], minimum_bet: int):
        super().__init__(cog, players, channel, minimum_bet)
        self.players: List[PokerPlayer] = [PokerPlayer(id=p, index=i) for i, p in enumerate(self.players_ids)]

    async def save_state(self) -> None:
        channel_conf = self.cog.config.channel(self.channel)
        if self.is_finished:
            await channel_conf.game.set({})
        else:
            await channel_conf.game.set({
                "players": json.dumps([p.to_dict(encode_json=True) for p in self.players]),
                "table": json.dumps([c.to_dict(encode_json=True) for c in self.table]),
                "deck": json.dumps([c.to_dict(encode_json=True) for c in self.deck]),
                "state": int(self.state),
                "minimum_bet": self.minimum_bet,
                "current_bet": self.current_bet,
                "pot": self.pot,
                "turn": self.turn,
                "finished": self.all_hands_finished,
                "message": self.message.id if self.message else None
            })

    @staticmethod
    async def from_config(cog: BaseCasinoCog, channel: Union[discord.TextChannel, discord.Thread], config: dict) -> "PokerGame":
        game = PokerGame(cog, [], channel, config["minimum_bet"])
        game.players = [PokerPlayer.from_dict(p) for p in json.loads(config["players"])]
        game.players_ids = [p.id for p in game.players]
        game.table = [Card.from_dict(c) for c in json.loads(config["table"])]
        game.deck = [Card.from_dict(c) for c in json.loads(config["deck"])]
        game.state = PokerState(config["state"])
        game.current_bet = config["current_bet"]
        game.pot = config["pot"]
        game.turn = config["turn"]
        game.all_hands_finished = config["finished"]
        if config["message"]:
            try:
                game.message = await channel.fetch_message(config["message"])
            except discord.NotFound:
                pass
        game.view = await game.get_view()
        return game

    @property
    def is_finished(self) -> bool:
        return self.all_hands_finished or self.is_cancelled

    def current_player(self) -> Optional[PokerPlayer]:
        return self.players[self.turn] if self.turn is not None and 0 <= self.turn < len(self.players) else None

    def find_player(self, ptype: PlayerType) -> Optional[PokerPlayer]:
        return next((p for p in self.players if p.type == ptype), None)

    def find_player_by_id(self, user_id: int) -> Optional[PokerPlayer]:
        return next((p for p in self.players if p.id == user_id), None)

    def get_previous_player(self) -> Optional[PokerPlayer]:
        if not (self.turn is not None and 0 <= self.turn < len(self.players)):
            return None
        assert self.turn is not None
        t = self.turn
        for _ in range(len(self.players)):
            t = t - 1 if t > 0 else len(self.players) - 1
            if self.players[t].state != PlayerState.Folded:
                return self.players[t]
        return None

    def get_next_player(self) -> Optional[PokerPlayer]:
        if not (self.turn is not None and 0 <= self.turn < len(self.players)):
            return None
        t = self.turn
        for _ in range(len(self.players)):
            t = t + 1 if t < len(self.players) - 1 else 0
            if self.players[t].state != PlayerState.Folded:
                return self.players[t]
        return None

    @property
    def can_check(self) -> bool:
        current = self.current_player()
        previous = self.get_previous_player()
        if previous is None or current is None:
            return False
        if previous.state in (PlayerState.Pending, PlayerState.Checked):
            return True
        if self.state == PokerState.PreFlop and current and current.type == PlayerType.BigBlind:
            return all(p.current_bet <= current.current_bet for p in self.players)
        return False

    def try_add_player(self, user_id: int) -> Tuple[bool, str]:
        if self.state != PokerState.WaitingForPlayers:
            return False, "The game already started."
        if len(self.players) >= POKER_MAX_PLAYERS:
            return False, "This game is full."
        if any(p.id == user_id for p in self.players):
            return False, "You're already playing."
        self.players.append(PokerPlayer(id=user_id, index=len(self.players)))
        self.players_ids = [p.id for p in self.players]
        return True, ""
    
    def try_remove_player(self, user_id: int) -> Tuple[bool, str]:
        if len(self.players) == 1:
            return False, "You can't leave. Try cancelling the game instead."
        if self.state != PokerState.WaitingForPlayers:
            return False, "The game already started."
        pl = self.find_player_by_id(user_id)
        if pl is None:
            return False, "You're not even playing, why are you trying to leave?"
        self.players.remove(pl)
        # re-index players
        for i, p in enumerate(self.players):
            p.index = i
            p.type = PlayerType(min(i, PlayerType.Normal.value))
        return True, ""
    
    async def cancel(self) -> None:
        if self.is_cancelled:
            return
        self.is_cancelled = True
        await self.save_state()
        if self.message:
            try:
                await self.message.delete()
            except discord.NotFound:
                pass
        for player in self.players:
            if player.total_betted > 0:
                member = player.member(self)
                try:
                    await bank.deposit_credits(member, player.total_betted)
                except errors.BalanceTooHigh as err:
                    await bank.set_balance(member, err.max_balance)

    async def start_hand(self) -> None:
        if self.state != PokerState.WaitingForPlayers:
            raise ValueError("Game already started")
        if len(self.players) < 2:
            raise ValueError("Not enough players")
        elif len(self.players) == 2:
            self.players[0].type = PlayerType.SmallBlind
            self.players[1].type = PlayerType.BigBlind

        for _ in range(2):
            for p in self.players:
                p.hand.append(self.deck.pop())

        sb = self.find_player(PlayerType.SmallBlind)
        bb = self.find_player(PlayerType.BigBlind)
        assert sb is not None and bb is not None
        self.pot += await sb.bet(self, self.minimum_bet // 2)
        sb.state = PlayerState.Betted
        self.pot += await bb.bet(self, self.minimum_bet)
        bb.state = PlayerState.Betted

        start_player = (bb.index if bb else (sb.index if sb else 0))
        self.turn = self.get_next(start_player)
        self.state = PokerState.PreFlop
        await self.save_state()

    def get_next(self, start_index: int) -> int:
        i = start_index
        for _ in range(len(self.players)):
            i = i + 1 if i < len(self.players) - 1 else 0
            if self.players[i].state != PlayerState.Folded:
                return i
        return start_index

    async def fold(self, user_id: int) -> None:
        current = self.current_player()
        if current is None or current.id != user_id:
            raise ValueError("Not your turn")
        
        current.state = PlayerState.Folded
        current.current_bet = 0

        # check elimination
        not_folded = [p for p in self.players if p.state != PlayerState.Folded]
        if len(not_folded) == 1:
            await self.end_hand(force_winner=not_folded[0])
            return
        
        # special case: nobody bet the first round
        if len(not_folded) == 2 and self.state == PokerState.PreFlop \
                and all(p.type in (PlayerType.SmallBlind, PlayerType.BigBlind) for p in not_folded):
            sb = self.find_player(PlayerType.SmallBlind)
            assert sb is not None
            sb.state = PlayerState.Pending

        await self.advance_turn()

    async def check(self, user_id: int) -> None:
        current = self.current_player()
        if current is None or current.id != user_id:
            raise ValueError("Not your turn")
        if not self.can_check:
            raise ValueError("Cannot check")
        
        current.state = PlayerState.Checked
        await self.advance_turn()

    async def bet(self, user_id: int, bet: int) -> None:
        current = self.current_player()
        if current is None or current.id != user_id:
            raise ValueError("Not your turn")
        if bet < self.current_bet:
            raise ValueError("Bet must be higher than the previous")

        additional = await current.bet(self, bet)
        if additional == 0:
            await self.advance_turn()
            return

        self.pot += additional
        if current.state != PlayerState.AllIn:
            current.state = PlayerState.Betted
        self.current_bet = max(self.current_bet, current.current_bet)

        for p in self.players:
            if p.state not in (PlayerState.Folded, PlayerState.AllIn) and p.current_bet < self.current_bet:
                p.state = PlayerState.Pending

        # live blind
        if self.state == PokerState.PreFlop and self.current_bet == self.minimum_bet and current.type != PlayerType.BigBlind:
            bb = self.find_player(PlayerType.BigBlind)
            if bb is not None and bb.state != PlayerState.Folded:
                bb.state = PlayerState.Pending

        await self.advance_turn()

    async def advance_turn(self) -> None:
        self.last_interacted = datetime.now()

        # keep advancing rounds while there are no non-all-in pending players
        while True:
            active_non_folded = [p for p in self.players if p.state != PlayerState.Folded]
            non_allin_active = [p for p in active_non_folded if p.state != PlayerState.AllIn]
            pending_non_allin = [p for p in non_allin_active if p.state == PlayerState.Pending]
            if active_non_folded and not pending_non_allin:
                self.state = PokerState(min(self.state.value + 1, PokerState.Showdown.value))
                self.current_bet = 0
                if len(non_allin_active) > 1:
                    for p in self.players:
                        if p.state not in (PlayerState.Folded, PlayerState.AllIn):
                            p.state = PlayerState.Pending
                            p.current_bet = 0
                # deal cards
                if self.state == PokerState.Flop:
                    self.deck.pop()
                    for _ in range(3):
                        self.table.append(self.deck.pop())
                elif self.state in (PokerState.Turn, PokerState.River):
                    self.deck.pop()
                    self.table.append(self.deck.pop())
                elif self.state == PokerState.Showdown:
                    await self.end_hand()
                    return
                continue  # keep going
            break

        found = False
        if self.turn is None:
            for i, p in enumerate(self.players):
                if p.state == PlayerState.Pending:
                    self.turn = i
                    found = True
                    break
        else:
            start = self.turn
            n = len(self.players)
            for i in range(1, n + 1):
                idx = (start + i) % n
                if self.players[idx].state == PlayerState.Pending:
                    self.turn = idx
                    found = True
                    break

        if not found:
            self.turn = None

        await self.save_state()

    async def end_hand(self, force_winner: Optional[PokerPlayer] = None) -> None:
        if force_winner:
            force_winner.winnings += self.pot
            self.state = PokerState.Showdown  # ui
            member = force_winner.member(self)
            if self.pot > 0:
                try:
                    await bank.deposit_credits(member, self.pot)
                except errors.BalanceTooHigh as err:
                    await bank.set_balance(member, err.max_balance)
        else:
            # evaluate hands
            for player in self.players:
                if player.state != PlayerState.Folded:
                    player.hand_result = get_hand_result(self.table, player.hand)

            pots = self.build_side_pots()

            # For each pot, find the best hand among eligible players
            for pot_amount, eligible_players in pots:
                if not eligible_players or pot_amount == 0:
                    continue  # shouldn't happen

                contenders = [p for p in eligible_players if p.state != PlayerState.Folded]
                if not contenders:
                    continue  # shouldn't happen

                # find best HandResult among contenders
                best = max((p.hand_result for p in contenders), default=None)  # type: ignore
                if best is None:
                    continue  # shouldn't happen

                winners = [p for p in contenders if p.hand_result == best]

                # split pot among winners with deterministic remainder
                per = pot_amount // len(winners)
                remainder = pot_amount % len(winners)
                winners_sorted = sorted(winners, key=lambda p: p.index)
                for i, winner in enumerate(winners_sorted):
                    member = winner.member(self)
                    amount = per + (1 if i < remainder else 0)
                    winner.winnings += amount
                    try:
                        await bank.deposit_credits(member, amount)
                    except errors.BalanceTooHigh as err:
                        await bank.set_balance(member, err.max_balance)
        # cleanup
        self.all_hands_finished = True
        self.turn = None
        await self.save_state()

    def build_side_pots(self) -> List[Tuple[int, List[PokerPlayer]]]:
        # consider all players who put chips into the pot (could include folded players)
        contributors = [p for p in self.players if p.total_betted > 0]
        if not contributors:
            return []

        remaining = sorted(contributors, key=lambda p: p.total_betted)
        pots: List[Tuple[int, List[PokerPlayer]]] = []
        last = 0

        while remaining:
            smallest = remaining[0].total_betted
            contribution = smallest - last  # how much each remaining player contributes to this slice
            pot_amount = contribution * len(remaining)

            # eligible players for this pot are remaining players who did NOT fold
            eligible = [p for p in remaining if p.state != PlayerState.Folded]
            pots.append((pot_amount, eligible))

            # move forward: remove players who only contributed up to smallest
            last = smallest
            remaining = [p for p in remaining if p.total_betted > smallest]

        return pots
    

    async def get_suit_emojis(self):
        return {
            CardSuit.HEARTS: "♥️",
            CardSuit.DIAMONDS: "♦️",
            CardSuit.SPADES: await self.cog.config.emoji_spades(),
            CardSuit.CLUBS: await self.cog.config.emoji_clubs(),
        }
    
    async def get_player_type_emojis(self):
        return {
            PlayerType.Dealer: await self.cog.config.emoji_dealer(),
            PlayerType.SmallBlind: await self.cog.config.emoji_smallblind(),
            PlayerType.BigBlind: await self.cog.config.emoji_bigblind(),
            PlayerType.Normal: "",
        }

    async def get_embed(self) -> discord.Embed:
        suit_emojis = await self.get_suit_emojis()
        player_emojis = await self.get_player_type_emojis()
        currency_name = await bank.get_currency_name(self.channel.guild)

        def card_str(card: Card):
            return f"{CARD_VALUE_STR[card.value]}{suit_emojis[card.suit]}"

        embed = discord.Embed()
        desc_lines: List[str] = []

        # title
        winners = [p for p in self.players if p.winnings - p.total_betted > 0]
        hand_finished = len(winners) > 0
        if len(winners) == 0:
            title_extra = POKER_STAGE_NAMES[self.state]
        elif len(winners) == 1:
            title_extra = f"Winner: {winners[0].member(self).display_name}"
        else:
            title_extra = "Winners"

        if self.state == PokerState.Showdown:
            title_left = player_emojis[PlayerType.BigBlind]
            title_right = player_emojis[PlayerType.BigBlind]
        else:
            title_left = suit_emojis[CardSuit.SPADES] + suit_emojis[CardSuit.HEARTS]
            title_right = suit_emojis[CardSuit.DIAMONDS] + suit_emojis[CardSuit.CLUBS]

        embed.title = f"{title_left} Poker - {title_extra} {title_right}"

        # pre-game summary
        if self.state == PokerState.WaitingForPlayers:
            desc_lines.append(f"**💵 Starting bet:** {humanize_number(self.minimum_bet)} {currency_name}\n")
            for player in self.players:
                desc_lines.append(f"<@{player.id}> {player_emojis[player.type]}")
            embed.description = "\n".join(desc_lines)
            embed.color = await self.cog.bot.get_embed_color(self.channel)
            return embed
        else:
            embed.color = DISCORD_RED

        # common
        desc_lines.append(f"**💰 Pot:** {humanize_number(self.pot)} {currency_name}\n")
        table_str = " ".join(card_str(c) for c in self.table) if self.table else "*Empty*"
        desc_lines.append(f"**🃏 Table:**{EMPTY_ELEMENT} {table_str}\n{EMPTY_ELEMENT}\n")

        # showdown information
        if self.state == PokerState.Showdown and hand_finished:
            for i, player in enumerate(self.players):
                content_lines: List[str] = []
                decorator = ""
                if player.state == PlayerState.Folded:
                    decorator = f"❌ "
                elif player in winners:
                    decorator = f"👑 "

                if player.state != PlayerState.Folded:
                    content_lines.append(f"`🖐` {' '.join(card_str(c) for c in player.hand)}")
                    if player.hand_result is not None:
                        content_lines.append(f"`🃏` {' '.join(card_str(c) for c in player.hand_result.cards)}")
                        content_lines.append(f"`📜` {humanize_camel_case(player.hand_result.type.name).title()}")

                if player in winners:
                    content_lines.append(f"`💵` +{humanize_number(player.winnings - player.total_betted)} {currency_name}")
                elif player.total_betted > 0:
                    content_lines.append(f"`💵` -{humanize_number(player.total_betted - player.winnings)} {currency_name}")

                inline = i % 3 != 2  # move every 3rd field to its own row to give enough space for the hands to display in full width
                embed.add_field(name=f"{decorator}{player.member(self).display_name}", value="\n".join(content_lines) or "\u200b", inline=inline)
        # player summary
        else:
            for player in self.players:
                line = ""
                if player.state == PlayerState.Folded:
                    line += f"❌ "
                if (self.turn is not None) and (player.index == self.turn) and not hand_finished:
                    line += f"▶️ "
                if player in winners:
                    line += f"👑 "

                line += player.member(self).mention

                if not hand_finished:
                    line += player_emojis[player.type]
                    if player.state == PlayerState.Betted:
                        line += f" - `betted {humanize_number(player.current_bet)}`"
                    elif player.state == PlayerState.Checked:
                        line += f" - `checked`"
                    elif player.state == PlayerState.AllIn:
                        line += f" - `all in`"
                    elif player.state == PlayerState.Pending:
                        line += " `...`"
                if player in winners:
                    line += f" (+{humanize_number(player.winnings - player.total_betted)} {currency_name})"
                elif player.total_betted > 0:
                    line += f" (-{humanize_number(player.total_betted - player.winnings)} {currency_name})"

                desc_lines.append(line)

        # thumbnail
        thumbnail_url = None
        if len(winners) == 1:
            winner_member = winners[0].member(self)
            thumbnail_url = winner_member.display_avatar.url
            embed.color = winner_member.color
        elif self.turn is not None:
            turn_player = self.players[self.turn]
            member = turn_player.member(self)
            if member:
                thumbnail_url = member.display_avatar.url

        # send it
        embed.description = "\n".join(desc_lines) if desc_lines else EMPTY_ELEMENT
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        return embed
    

    async def get_view(self) -> Optional[discord.ui.View]:
        if self.state == PokerState.WaitingForPlayers:
            return PokerWaitingView(self)
        elif self.is_finished:
            return PokerRematchView(self)
        else:
            if self.turn is None or not 0 <= self.turn < len(self.players):
                raise RuntimeError("Invalid turn during game")
            cur_player = self.players[self.turn]
            money = await bank.get_balance(cur_player.member(self))
            currency_name = await bank.get_currency_name(self.channel.guild)
            return PokerView(self, money, cur_player.current_bet, currency_name)
    

    async def update_message(self, interaction: Optional[discord.Interaction] = None):
        content = None
        if self.state != PokerState.WaitingForPlayers and not self.is_finished and self.turn is not None and 0 <= len(self.players):
            content = self.players[self.turn].member(self).mention
        
        self.view = await self.get_view()
        embed = await self.get_embed()

        if interaction:
            await interaction.response.edit_message(content=content, embed=embed, view=self.view)
        else:
            old_message = self.message
            self.message = await self.channel.send(content=content, embed=embed, view=self.view or discord.ui.View(timeout=0))
            if old_message:
                try:
                    await old_message.delete()
                except discord.NotFound:
                    pass

        async with self.cog.config.channel(self.channel).game() as game:
            game["message"] = self.message.id if self.message else None
    

    async def send_cards(self, interaction: discord.Interaction) -> None:
        player = self.find_player_by_id(interaction.user.id)
        if player is None:
            raise ValueError("Not a player")
        SUIT_EMOJIS = await self.get_suit_emojis()
        embed = discord.Embed(color=0x000000)
        embed.description = " ".join(f"{CARD_VALUE_STR[card.value]}{SUIT_EMOJIS[card.suit]}" for card in player.hand)
        embed.set_author(name="Here are your cards", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)



def is_straight(original_cards: List[Card]) -> Tuple[bool, Optional[Card]]:
    if len(original_cards) < 5:
        return False, None

    # unique by rank, keep any representative (we later look up by rank)
    rank_map = {}
    for c in original_cards:
        rank_map[c.value.value] = c
    ranks = sorted(rank_map.keys())  # ascending list of ints

    # ace is special
    if set([10, 11, 12, 13, 1]).issubset(set(ranks)):
        return True, rank_map[1]

    # sliding window
    for i in range(0, len(ranks) - 4):
        window = ranks[i:i+5]
        if window[4] - window[0] == 4 and all(window[j+1] - window[j] == 1 for j in range(4)):
            return True, rank_map[window[-1]]
    return False, None


def get_hand_result(table: List[Card], hand: List[Card]) -> HandResult:
    if len(table) != 5 or len(hand) != 2:
        raise ValueError("Invalid number of cards for evaluation")
    cards = table + hand

    # check flush
    suits_group: Dict[CardSuit, List[Card]] = {}
    for c in cards:
        suits_group.setdefault(c.suit, []).append(c)
    flush = None
    for suit_cards in suits_group.values():
        if len(suit_cards) >= 5:
            flush = sorted(suit_cards, key=lambda x: x.poker_value, reverse=True)
            break
    if flush:
        is_straight_flush, highest = is_straight(flush)
        if is_straight_flush and highest is not None:
            index_highest = flush.index(highest)
            straightflush = flush[index_highest:index_highest+5]
            if len(straightflush) == 4:  # janky edge case: ace-5-4-3-2
                straightflush.append(flush[0])
            htype = HandType.RoyalFlush if highest.value == CardValue.ACE else HandType.StraightFlush
            return HandResult(htype, straightflush)
        return HandResult(HandType.Flush, flush[:5])

    # group by value
    by_value: Dict[CardValue, List[Card]] = {}
    for c in cards:
        by_value.setdefault(c.value, []).append(c)
    groups = list(by_value.values())

    # quadruple
    quad = next((g for g in groups if len(g) == 4), None)
    if quad:
        extra = sorted((c for c in cards if c not in quad), key=lambda x: x.poker_value, reverse=True)[:1]
        return HandResult(HandType.Quadruple, quad + extra)

    # triple
    triple = next((g for g in groups if len(g) == 3), None)
    if triple:
        remaining = [g for g in groups if g is not triple]
        pair = next((g for g in remaining if len(g) >= 2), None)
        if pair:
            return HandResult(HandType.FullHouse, triple + pair[:2])
        extra = sorted((c for c in cards if c not in triple), key=lambda x: x.poker_value, reverse=True)[:2]
        return HandResult(HandType.Triple, triple + extra)

    # straight
    distinct: List[Card] = []
    seen_vals = set()
    for c in sorted(cards, key=lambda x: x.poker_value, reverse=True):
        if c.value not in seen_vals:
            distinct.append(c)
            seen_vals.add(c.value)
    is_str, highest = is_straight(list(reversed(distinct)))  # function expects ascending order
    if is_str and highest is not None:
        index_highest = distinct.index(highest)
        straight_cards = distinct[index_highest:index_highest+5]
        if len(straight_cards) == 4:  # janky edge case: ace-5-4-3-2
            straight_cards.append(distinct[0])
        return HandResult(HandType.Straight, straight_cards)

    # pairs
    ordered = sorted(cards, key=lambda x: x.poker_value, reverse=True)
    pair = next((g for g in groups if len(g) == 2), None)
    if pair:
        remaining_groups = [g for g in groups if g is not pair]
        second_pair = next((g for g in remaining_groups if len(g) == 2), None)
        if second_pair:
            # sort pairs by value
            pair_vals = sorted([pair, second_pair], key=lambda g: g[0].poker_value, reverse=True)
            doublepair = pair_vals[0] + pair_vals[1]
            extra = sorted((c for c in cards if c not in doublepair), key=lambda x: x.poker_value, reverse=True)[:1]
            return HandResult(HandType.DoublePair, doublepair + extra)
        extra = [c for c in ordered if c not in pair][:3]
        return HandResult(HandType.Pair, pair + extra)

    return HandResult(HandType.HighCard, ordered[:5])
