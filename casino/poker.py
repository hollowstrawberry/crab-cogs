import discord
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass, field
from redbot.core import bank
from redbot.core.utils.chat_formatting import humanize_number

from casino.base import BaseCasinoCog, BasePokerGame
from casino.card import CARD_VALUE_STR, Card, CardSuit, CardValue
from casino.utils import (HandType, PlayerState, PlayerType, PokerState,
                          InsufficientFundsError, humanize_camel_case, DISCORD_RED, MAX_PLAYERS)


@dataclass
class HandResult:
    type: HandType
    cards: List[Card]

    def __post_init__(self):
        if len(self.cards) != 5:
            raise ValueError("HandResult must contain exactly 5 cards")

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
class PokerPlayer:
    id: int
    index: int
    type: PlayerType = field(init=False)
    hand: List[Card] = field(default_factory=list)
    state: PlayerState = PlayerState.Pending
    total_betted: int = 0
    current_bet: int = 0
    hand_result: Optional[HandResult] = None

    def __post_init__(self):
        # type is min(index, Normal)
        self.type = PlayerType(min(self.index, PlayerType.Normal.value))

    def member(self, game: BasePokerGame) -> discord.Member:
        member = game.channel.guild.get_member(self.id)
        if not member:
            raise ValueError(f"Where did poker player with id {self.id} go?")
        return member

    async def bet(self, game: BasePokerGame, bet_amount: int) -> int:
        """Attempt to place a bet. Delegates actual money transfer to the cog.
        Returns the actual amount deducted (additional bet).
        May raise appropriate exceptions if you implement economy.
        """
        if bet_amount <= self.current_bet:
            raise ValueError("New bet must be higher than previous")

        additional = bet_amount - self.current_bet
        member = self.member(game)
        if not await bank.can_spend(member, additional):
            raise InsufficientFundsError
        await bank.withdraw_credits(member, additional)

        self.total_betted += additional
        self.current_bet = bet_amount
        return additional


class PokerGame(BasePokerGame):
    def __init__(self, cog: BaseCasinoCog, players: List[discord.Member], channel: discord.TextChannel, minimum_bet: int = 10):
        super().__init__(cog, players, channel, minimum_bet)
        self.players: List[PokerPlayer] = [PokerPlayer(id=p, index=i) for i, p in enumerate(self.players_ids)]

    async def save_state(self) -> None:
        if not self.cog.config:
            return
        channel_conf = self.cog.config.channel(self.channel)
        await channel_conf.game.set({
            "table": [str(c) for c in self.table],
            "players": [p.id for p in self.players],
            "player_states": [p.state.name for p in self.players],
            "player_total_betted": [p.total_betted for p in self.players],
            "player_current_bet": [p.current_bet for p in self.players],
            "state": int(self.state),
            "minimum_bet": self.minimum_bet,
            "current_bet": self.current_bet,
            "pot": self.pot,
        })

    @property
    def is_finished(self) -> bool:
        return self.all_hands_finished

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
        while True:
            t = t - 1 if t > 0 else len(self.players) - 1
            if self.players[t].state != PlayerState.Folded:
                return self.players[t]

    def get_next_player(self) -> Optional[PokerPlayer]:
        if not (self.turn is not None and 0 <= self.turn < len(self.players)):
            return None
        t = self.turn
        while True:
            t = t + 1 if t < len(self.players) - 1 else 0
            if self.players[t].state != PlayerState.Folded:
                return self.players[t]

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

    # ---------------- Core actions ----------------
    def try_add_player(self, user_id: int) -> bool:
        if self.state != PokerState.WaitingForPlayers:
            return False
        if len(self.players) >= MAX_PLAYERS:
            return False
        if any(p.id == user_id for p in self.players):
            return False
        self.players.append(PokerPlayer(id=user_id, index=len(self.players)))
        return True

    def try_remove_player(self, user_id: int) -> bool:
        if len(self.players) == 1:
            return False
        if self.state != PokerState.WaitingForPlayers:
            return False
        pl = self.find_player_by_id(user_id)
        if pl is None:
            return False
        self.players.remove(pl)
        # re-index players
        for i, p in enumerate(self.players):
            p.index = i
            p.type = PlayerType(min(i, PlayerType.Normal.value))
        return True

    async def start_hand(self) -> None:
        if self.state != PokerState.WaitingForPlayers:
            raise ValueError("Game already started")
        if len(self.players) < 2:
            raise ValueError("Not enough players")

        # deal two cards to each player
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
        # return next index of a non-folded player
        i = start_index
        for _ in range(len(self.players)):
            i = i + 1 if i < len(self.players) - 1 else 0
            if self.players[i].state != PlayerState.Folded:
                return i
        return start_index

    async def fold(self, user_id: int) -> None:
        cur = self.current_player()
        if cur is None or cur.id != user_id:
            raise RuntimeError("Not your turn")
        cur.state = PlayerState.Folded
        cur.current_bet = 0
        # check elimination
        not_folded = [p for p in self.players if p.state != PlayerState.Folded]
        if len(not_folded) == 1:
            await self.end_hand(not_folded[0].index)
            return
        # special case: nobody bet the first round
        if len(not_folded) == 2 and self.state == PokerState.PreFlop \
                and all(p.type in (PlayerType.SmallBlind, PlayerType.BigBlind) for p in not_folded):
            sb = self.find_player(PlayerType.SmallBlind)
            assert sb is not None
            sb.state = PlayerState.Pending
        await self.advance_turn()

    async def check(self, user_id: int) -> None:
        cur = self.current_player()
        if cur is None or cur.id != user_id:
            raise RuntimeError("Not your turn")
        if not self.can_check:
            raise RuntimeError("Cannot check")
        cur.state = PlayerState.Checked
        await self.advance_turn()

    async def call(self, user_id: int) -> None:
        cur = self.current_player()
        if cur is None or cur.id != user_id:
            raise RuntimeError("Not your turn")
        additional = self.current_bet - cur.current_bet
        if additional <= 0:
            return
        self.pot += await cur.bet(self, self.current_bet)
        cur.state = PlayerState.Betted
        await self.advance_turn()

    async def raise_to(self, user_id: int, bet: int) -> None:
        cur = self.current_player()
        if cur is None or cur.id != user_id:
            raise ValueError("Not your turn")
        if bet < self.current_bet:
            raise ValueError("Bet must be higher than current")
        self.pot += await cur.bet(self, bet)
        cur.state = PlayerState.Betted
        self.current_bet = bet
        # set pending for players who haven't matched
        for p in self.players:
            if p.state != PlayerState.Folded and p.current_bet < self.current_bet:
                p.state = PlayerState.Pending
        await self.advance_turn()

    async def advance_turn(self) -> None:
        # if hand finished, nothing to do
        if any(p for p in self.players if p.state != PlayerState.Folded) and all(p.state != PlayerState.Pending for p in self.players if p.state != PlayerState.Folded):
            # advance the state
            self.state = PokerState(min(int(self.state) + 1, int(PokerState.Showdown)))
            self.current_bet = self.minimum_bet
            for p in self.players:
                if p.state != PlayerState.Folded:
                    p.state = PlayerState.Pending
                    p.current_bet = 0
            # deal cards according to state
            if self.state == PokerState.Flop:
                self.deck.pop()
                for _ in range(3):
                    self.table.append(self.deck.pop())
            elif self.state in (PokerState.Turn, PokerState.River):
                self.deck.pop()
                self.table.append(self.deck.pop())
            elif self.state == PokerState.Showdown:
                # evaluate hands
                results = {p.index: get_hand_result(self.table, p.hand) for p in self.players if p.state != PlayerState.Folded}
                max_res = max(results.values())
                winners = [idx for idx, res in results.items() if res == max_res]
                for idx, res in results.items():
                    self.players[idx].hand_result = res
                await self.end_hand(*winners)
                return
        # otherwise move to next pending player
        # find next pending player index
        if self.turn is None:
            self.turn = 0
            return
        start = self.turn
        n = len(self.players)
        for i in range(1, n + 1):
            idx = (start + i) % n
            if self.players[idx].state == PlayerState.Pending:
                self.turn = idx
                return
        # fallback: keep current

    async def end_hand(self, *winners_indices: int) -> None:
        if not winners_indices:
            raise ValueError("No winners")
        
        self.winners = list(winners_indices)
        self.turn = None

        per = self.pot // len(self.winners)
        for idx in self.winners:
            await bank.deposit_credits(self.players[idx].member(self), per)

        self.pot = 0
        self.all_hands_finished = True
        await self.save_state()


    async def get_embed(self) -> discord.Embed:
        SUIT_EMOJIS = {
            CardSuit.HEARTS: "♥️",
            CardSuit.DIAMONDS: "♦️",
            CardSuit.SPADES: "♠️",
            CardSuit.CLUBS: "♣️",
        }
        PLAYER_TYPE_EMOJIS = {
            PlayerType.Dealer: "(D)",
            PlayerType.SmallBlind: "(SB)",
            PlayerType.BigBlind: "(BB)",
            PlayerType.Normal: "",
        }
        EMPTY_ELEMENT = "\u200b"

        def card_str(card: Card):
            return f"{CARD_VALUE_STR[card.value]}{SUIT_EMOJIS[card.suit]}"

        winners_count = len(self.winners or [])
        if winners_count == 0:
            title_extra = humanize_camel_case(self.state.name)
        elif winners_count == 1:
            member = self.players[self.winners[0]].member(self)
            title_extra = f"Winner: {member.display_name}"
        else:
            title_extra = "Winners"

        if self.state == PokerState.Showdown:
            title_left = PLAYER_TYPE_EMOJIS[PlayerType.BigBlind]
            title_right = PLAYER_TYPE_EMOJIS[PlayerType.BigBlind]
        else:
            title_left = SUIT_EMOJIS[CardSuit.SPADES] + SUIT_EMOJIS[CardSuit.HEARTS]
            title_right = SUIT_EMOJIS[CardSuit.DIAMONDS] + SUIT_EMOJIS[CardSuit.CLUBS]

        title = f"{title_left} Poker - {title_extra} {title_right}"

        desc_lines: List[str] = []
        embed = discord.Embed()

        if self.state == PokerState.WaitingForPlayers:
            for p in self.players:
                desc_lines.append(f"<@{p.id}> {PLAYER_TYPE_EMOJIS[p.type]}")
            embed.title = title
            embed.description = "\n".join(desc_lines)
            embed.color = await self.cog.bot.get_embed_color(self.channel)
            return embed
        else:
            embed.color = DISCORD_RED

        # Common: pot / table
        desc_lines.append(f"**💰 Pot:** {humanize_number(self.pot)}\n")
        table_str = " ".join(card_str(c) for c in self.table) if self.table else "*Empty*"
        desc_lines.append(f"**🃏 Table:** {table_str}\n{EMPTY_ELEMENT}\n")

        hand_finished = winners_count > 0

        # Showdown with results: add one inline field per player
        if self.state == PokerState.Showdown and hand_finished:
            for p in self.players:
                content_lines: List[str] = []
                decorator = ""
                if p.state == PlayerState.Folded:
                    decorator = f"❌ "
                elif (p.index in (self.winners or [])):
                    decorator = f"👑 "

                if p.state != PlayerState.Folded:
                    # show player's hand
                    content_lines.append(f"`🖐` {' '.join(card_str(c) for c in p.hand)}")
                    # show evaluation if present
                    if p.hand_result is not None:
                        content_lines.append(f"`➡️` {' '.join(card_str(c) for c in p.hand_result.cards)}")
                        # human readable hand type
                        content_lines.append(f"`📜` {humanize_camel_case(p.hand_result.type.name).title()}")

                # money delta lines
                if p.index in (self.winners or []):
                    # prize roughly pot - total_betted (C# had this logic)
                    gain = (self.pot - p.total_betted) if hasattr(self, "pot") else 0
                    content_lines.append(f"`💵` +{gain}")
                elif p.total_betted > 0:
                    content_lines.append(f"`💵` -{p.total_betted}")

                # field title = decorator + player's visual name
                member = self.channel.guild.get_member(p.id) if self.channel.guild else None
                title_name = member.display_name if member else f"<@{p.id}>"
                embed.add_field(name=f"{decorator}{title_name}", value="\n".join(content_lines) or "\u200b", inline=True)

        else:
            # Non-showdown: summary list of players (text description)
            for p in self.players:
                line = ""
                if p.state == PlayerState.Folded:
                    line += f"❌ "
                if (self.turn is not None) and (p.index == self.turn) and not hand_finished:
                    line += f"▶️ "
                if p.index in (self.winners or []):
                    line += f"👑 "

                member = p.member(self)
                mention = member.mention if member else f"<@{p.id}>"
                line += mention

                if not hand_finished:
                    line += PLAYER_TYPE_EMOJIS[p.type]
                    if p.state == PlayerState.Betted:
                        line += f" - `betted {humanize_number(p.current_bet)}`"
                    elif p.state == PlayerState.Checked:
                        line += f" - `checked`"
                    elif p.state == PlayerState.Pending:
                        line += " `...`"

                if p.index in (self.winners or []):
                    gain = (self.pot - p.total_betted) if hasattr(self, "pot") else 0
                    line += f" (+{gain})"
                elif p.total_betted > 0:
                    line += f" (-{p.total_betted})"

                desc_lines.append(line)

        thumbnail_url = None
        if winners_count == 1:
            winner = self.players[self.winners[0]].member(self)
            thumbnail_url = winner.display_avatar.url
            embed.color = winner.color
        elif self.turn is not None:
            turn_player = self.players[self.turn]
            member = turn_player.member(self)
            if member:
                thumbnail_url = member.display_avatar.url

        embed.title = title
        embed.description = "\n".join(desc_lines) if desc_lines else "\u200b"
        if thumbnail_url:
            try:
                embed.set_thumbnail(url=thumbnail_url)
            except Exception:
                pass

        return embed



def is_straight(original_cards: List[Card]) -> Tuple[bool, Optional[Card]]:
    highest = None
    if len(original_cards) < 5:
        return False, None
    cards = sorted({c.value: c for c in original_cards}.values(), key=lambda c: c.value.value)
    vals = [c.value for c in cards]

    if set([CardValue.TEN, CardValue.JACK, CardValue.QUEEN, CardValue.KING, CardValue.ACE]).issubset(set(vals)):
        highest = next((c for c in cards if c.value == CardValue.ACE), None)
        return True, highest

    count = 1
    for i in range(len(cards) - 2, -1, -1):
        if cards[i].value == CardValue(cards[i + 1].value.value - 1):
            count += 1
            if count == 5:
                highest = cards[i + 4]
                return True, highest
        else:
            count = 1
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
            flush_sorted = sorted(suit_cards, key=lambda x: x.poker_value, reverse=True)
            flush = flush_sorted
            break
    if flush:
        is_straight_flush, highest = is_straight(flush)
        if is_straight_flush:
            straightflush = sorted(flush, key=lambda x: x.poker_value, reverse=True)[:5]
            htype = HandType.RoyalFlush if highest and highest.value == CardValue.ACE else HandType.StraightFlush
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
        straight_cards = sorted(distinct, key=lambda x: x.poker_value, reverse=True)[:5]
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
