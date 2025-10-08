import time
import logging
from typing import Optional, Tuple, Dict

import draughts

log = logging.getLogger("red.crab-cogs.simplecheckers.agent")

INF = 10**9


class MinimaxAgent:
    """
    Minimax agent with alpha-beta and iterative deepening that uses push/pop.
    Construct with MinimaxAgent(my_color=draughts.BLACK or draughts.WHITE).
    """

    def __init__(self, my_color: int):
        self.my_color = my_color
        self.opp_color = draughts.WHITE if my_color == draughts.BLACK else draughts.BLACK
        # transposition table: fen_key -> (depth, score)
        self.tt: Dict[str, Tuple[int, int]] = {}
        self.nodes = 0

    def choose_move(self, board: draughts.Board, max_depth: int, time_limit: Optional[float] = None):
        """
        Iterative deepening root search.
        - board: draughts.Board
        - max_depth: maximum search depth to attempt
        - time_limit: seconds (optional). If provided, function will return best-so-far when time runs out.
        Returns chosen move or None.
        """
        board = board.copy() # just in case

        start_time = time.time()
        deadline = start_time + time_limit if time_limit is not None else None

        best_move = None
        best_score = -INF

        # root move ordering: shallow evaluation of resulting position
        root_moves = list(board.legal_moves())
        if not root_moves:
            return None

        # iterative deepening
        for depth in range(1, max_depth + 1):
            self.nodes = 0
            depth_best_move = None
            depth_best_score = -INF

            # order moves by quick shallow eval (descending if it's our turn)
            def quick_score(m):
                board.push(m)
                val = self._evaluate_simple(board)
                board.pop()
                return val

            root_moves.sort(key=quick_score, reverse=(board.turn == self.my_color))

            timed_out = False

            for m in root_moves:
                # time check at each root move
                if deadline is not None and time.time() > deadline:
                    timed_out = True
                    break

                board.push(m)
                score = self._alphabeta(board, depth - 1, -INF, INF, maximizing=(board.turn != self.my_color),
                                         deadline=deadline)
                board.pop()

                if score is None:
                    # time cutoff in subtree
                    timed_out = True
                    break

                if score > depth_best_score:
                    depth_best_score = score
                    depth_best_move = m

            # if we completed this depth without timing out, adopt depth result
            if not timed_out and depth_best_move is not None:
                best_move = depth_best_move
                best_score = depth_best_score
            else:
                log.info("Timed out")
                # timed out during this depth: return best_move from previous completed depth
                break

            log.info(f"Depth {depth} completed. {self.nodes=}, {best_score=}, elapsed={int((time.time() - start_time) * 1000)}ms")

        return best_move

    def _alphabeta(self, board: draughts.Board, depth: int, alpha: int, beta: int,
                   maximizing: bool, deadline: Optional[float]) -> Optional[int]:
        """
        Alpha-beta search using push/pop (at calling sites). Returns score (int) or None on time cutoff.
        - maximizing: True if we are maximizing for self.my_color at this node (i.e., the side to move equals agent)
        """
        # time cutoff
        if deadline is not None and time.time() > deadline:
            return None

        self.nodes += 1

        # terminal
        if board.is_over():
            win = board.winner()
            if win is None:
                return 0
            return INF if win == self.my_color else -INF

        if depth == 0:
            return self._evaluate_simple(board)

        # transposition table lookup
        # use board.fen for keying -- include side-to-move implicitly in fen if it's part of fen
        tt_key = f"{board.fen}_{depth}_{'M' if maximizing else 'm'}"
        if tt_key in self.tt:
            return self.tt[tt_key][1]

        moves = list(board.legal_moves())
        if not moves:
            # no legal moves at non-terminal (should be handled by is_over, but be safe)
            return -INF if board.turn != self.my_color else INF

        # move ordering: shallow eval of resulting pos
        def quick_after(move):
            board.push(move)
            v = self._evaluate_simple(board)
            board.pop()
            return v

        moves.sort(key=quick_after, reverse=maximizing)

        value = -INF if maximizing else INF

        for m in moves:
            if deadline is not None and time.time() > deadline:
                return None

            board.push(m)
            child_score = self._alphabeta(board, depth - 1, alpha, beta, not maximizing, deadline)
            board.pop()

            if child_score is None:
                return None  # time cutoff bubbled up

            if maximizing:
                if child_score > value:
                    value = child_score
                if value > alpha:
                    alpha = value
            else:
                if child_score < value:
                    value = child_score
                if value < beta:
                    beta = value

            if alpha >= beta:
                break

        # store in tt
        self.tt[tt_key] = (depth, value)
        return value

    def _evaluate_simple(self, board: draughts.Board) -> int:
        """
        Simple evaluation from self.my_color's perspective:
         - man = 100, king = 175
         - mobility: small bonus for number of legal moves (signed by whose turn it is)
         - uses str(board) to count piece characters (works with pydraughts ascii output)
        """
        man_value = 100
        king_value = 175

        s = str(board)  # robust text representation; counts b/B/w/W
        # count characters for black/white men and kings
        my_man = 0
        my_kings = 0
        opp_man = 0
        opp_kings = 0

        # determine which characters correspond to which colors
        # common prints: 'b' = black man, 'B' = black king, 'w' = white man, 'W' = white king
        for ch in s:
            if ch == 'b':
                if self.my_color == draughts.BLACK:
                    my_man += 1
                else:
                    opp_man += 1
            elif ch == 'B':
                if self.my_color == draughts.BLACK:
                    my_kings += 1
                else:
                    opp_kings += 1
            elif ch == 'w':
                if self.my_color == draughts.WHITE:
                    my_man += 1
                else:
                    opp_man += 1
            elif ch == 'W':
                if self.my_color == draughts.WHITE:
                    my_kings += 1
                else:
                    opp_kings += 1

        my_score = my_man * man_value + my_kings * king_value
        opp_score = opp_man * man_value + opp_kings * king_value
        material = my_score - opp_score

        # mobility
        try:
            moves_count = len(list(board.legal_moves()))
        except Exception:
            moves_count = 0
        mobility_bonus = 10 * moves_count * (1 if board.turn == self.my_color else -1)

        # small advancement-ish bonus (very small; we don't assume square API)
        # Use a tiny heuristic: prefer having more men than opponent (already in material),
        # and slightly reward if we have fewer kings than opponent (handled by material).
        advancement_bonus = 0

        total = material + mobility_bonus + advancement_bonus
        return int(total)
