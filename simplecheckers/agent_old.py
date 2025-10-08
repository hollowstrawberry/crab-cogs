import time
import random
import logging
import draughts
from typing import Optional, Tuple, Dict

log = logging.getLogger("red.crab-cogs.simplecheckers.agent")

INF = 10**9


class MinimaxAgentOld:
    """
    Minimax agent with alpha-beta and iterative deepening. Made with an LLM.
    """

    def __init__(self, my_color: int):
        self.my_color = my_color
        self.opp_color = draughts.WHITE if my_color == draughts.BLACK else draughts.BLACK
        # transposition table: fen_key -> (depth, score)
        self.tt: Dict[str, Tuple[int, int]] = {}
        self.nodes = 0


    def choose_move(self, board: draughts.Board, max_depth: int, time_limit: Optional[float] = None):
        board = board.copy()  # just in case

        start_time = time.time()
        deadline = start_time + time_limit if time_limit is not None else None

        best_score = -INF

        # root moves
        root_moves = list(board.legal_moves())
        if not root_moves:
            return None

        move_scores = []  # to collect (move, score) for the deepest completed depth

        for depth in range(1, max_depth + 1):
            self.nodes = 0
            depth_results = []
            depth_best_score = -INF

            # compute time remaining at the start of this depth (None if no time limit)
            if time_limit is None:
                time_remaining_at_depth_start = None
            else:
                elapsed = time.time() - start_time
                time_remaining_at_depth_start = max(0.0, time_limit - elapsed)

            # allow overrun for this depth if it started with > half the time_limit remaining
            allow_overrun = time_limit is not None and time_remaining_at_depth_start is not None and time_remaining_at_depth_start > time_limit / 3.0
            per_depth_deadline = deadline  # will be set to None if we choose to allow overrun
            overrunning = False

            # quick ordering function
            def quick_score(m):
                board.push(m)
                val = self._evaluate_simple(board)
                board.pop()
                return val

            root_moves.sort(key=quick_score, reverse=(board.turn == self.my_color))

            timed_out = False

            for m in root_moves:
                # check per-depth deadline before starting this root move
                if per_depth_deadline is not None and time.time() > per_depth_deadline:
                    if allow_overrun and not overrunning:
                        # disable the deadline for the rest of this depth so it can finish
                        overrunning = True
                        per_depth_deadline = None
                    else:
                        timed_out = True
                        break

                board.push(m)
                score = self._alphabeta(
                    board,
                    depth - 1,
                    -INF,
                    INF,
                    maximizing=(board.turn != self.my_color),
                    deadline=per_depth_deadline
                )
                board.pop()

                if score is None:
                    # If we get None, that means a time cutoff happened inside the subtree.
                    # If we allowed overrun and haven't already disabled the deadline, disable it now
                    # and continue (so the rest of the depth can finish).
                    if allow_overrun and not overrunning:
                        overrunning = True
                        per_depth_deadline = None
                        # Re-run this move with no deadline so we get a concrete score and allow the depth to finish.
                        board.push(m)
                        score = self._alphabeta(
                            board,
                            depth - 1,
                            -INF,
                            INF,
                            maximizing=(board.turn != self.my_color),
                            deadline=None
                        )
                        board.pop()
                        # if still None (very unlikely), treat as timed out and break
                        if score is None:
                            timed_out = True
                            break
                    else:
                        timed_out = True
                        break

                depth_results.append((m, score))
                if score > depth_best_score:
                    depth_best_score = score

            # if we completed the entire depth without timing out, adopt its results
            if not timed_out and depth_results:
                move_scores = depth_results
                best_score = depth_best_score
            else:
                break

            log.info(f"[OLD] Depth {depth} completed. {self.nodes=}, {best_score=}, elapsed={int((time.time() - start_time) * 1000)}ms")

        if not move_scores:
            return None

        MARGIN = 20  # tweak for more/less randomness
        candidates = [m for m, score in move_scores if score >= best_score - MARGIN]
        chosen = random.choice(candidates)
        return chosen


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
