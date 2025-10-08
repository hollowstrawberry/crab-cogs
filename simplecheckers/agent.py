import time
import random
import logging
import draughts
from typing import Optional, Tuple, Dict, List, Any

log = logging.getLogger("red.crab-cogs.simplecheckers.agent")

INF = 10**9


class MinimaxAgent:
    """
    Minimax agent with alpha-beta, iterative deepening, quiescence search,
    capture-aware ordering, lightweight time management, advancement & capture bonuses.
    Written by an LLM.
    Asking an LLM to implement it has no intellectual merit but makes for a good player experience for minimal effort.
    """

    def __init__(self, my_color: int):
        self.my_color = my_color
        self.opp_color = draughts.WHITE if my_color == draughts.BLACK else draughts.BLACK
        # transposition table: fen_key -> (depth, score)
        # NOTE: kept simple; could be extended to store bounds (upper/lower/exact).
        self.tt: Dict[str, Tuple[int, int]] = {}
        self.nodes = 0

    # ----------------------------
    # Public API (choose_move)
    # ----------------------------
    def choose_move(self, board: draughts.Board, max_depth: int, time_limit: Optional[float] = None):
        board = board.copy()  # don't mutate caller's board here

        start_time = time.time()
        deadline = start_time + time_limit if time_limit is not None else None

        best_score = -INF

        # root moves
        root_moves = list(board.legal_moves())
        if not root_moves:
            return None

        # fast path: only one move
        if len(root_moves) == 1:
            return root_moves[0]

        move_scores = []  # to collect (move, score) for the deepest completed depth

        for depth in range(1, max_depth + 1):
            self.nodes = 0
            depth_results: List[Tuple[Any, int]] = []
            depth_best_score = -INF

            # compute time remaining at the start of this depth (None if no time limit)
            if time_limit is None:
                time_remaining_at_depth_start = None
            else:
                elapsed = time.time() - start_time
                time_remaining_at_depth_start = max(0.0, time_limit - elapsed)

            # allow overrun for this depth if it started with > (1/3) of time_limit remaining
            allow_overrun = (
                time_limit is not None
                and time_remaining_at_depth_start is not None
                and time_remaining_at_depth_start > time_limit / 3.0
            )
            per_depth_deadline = deadline  # will be set to None if we choose to allow overrun
            overrunning = False

            # quick ordering function: give capture moves a strong bias
            def quick_score(m: draughts.Move):
                # prefer captures (cheap detection), then evaluate
                is_cap = m.has_captures
                board.push(m)
                val = self._evaluate_simple(board)
                board.pop()
                return (1 if is_cap else 0, val)  # captures sort higher, then eval

            root_moves.sort(key=quick_score, reverse=(board.turn == self.my_color))

            timed_out = False

            for m in root_moves:
                # check per-depth deadline before starting this root move
                if per_depth_deadline is not None and time.time() > per_depth_deadline:
                    if allow_overrun and not overrunning:
                        # disable the deadline for the rest of this depth so it can finish
                        overrunning = True
                        per_depth_deadline = None
                        log.debug("Allowing per-depth overrun to finish current depth %s", depth)
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
                    # time cutoff inside subtree
                    if allow_overrun and not overrunning:
                        # allow finishing this depth: clear deadline and re-run this move
                        overrunning = True
                        per_depth_deadline = None
                        log.debug(f"Subtree timed out; enabling overrun and re-running move to finish depth {depth}")
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
                        if score is None:
                            # still none -> treat as timed out
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
                log.debug(f"Timed out or no results at depth {depth}")
                break

            log.info(f"Depth {depth} completed. {self.nodes=}, {best_score=}, elapsed={int((time.time() - start_time) * 1000)}ms")

        if not move_scores:
            return None

        # randomize among top moves within margin for entertainment
        MARGIN = 10  # tweak for more/less randomness
        candidates = [m for m, score in move_scores if score >= best_score - MARGIN]
        chosen = random.choice(candidates)
        return chosen

    # ----------------------------
    # Alpha-beta with TT & quiescence
    # ----------------------------
    def _alphabeta(self, board: draughts.Board, depth: int, alpha: int, beta: int,
                   maximizing: bool, deadline: Optional[float]) -> Optional[int]:
        """
        Alpha-beta search using push/pop. Returns score (int) or None on time cutoff.
        """

        # deadline/time cutoff check
        if deadline is not None and time.time() > deadline:
            return None

        self.nodes += 1

        # terminal
        if board.is_over():
            win = board.winner()
            if win is None:
                return 0
            return INF if win == self.my_color else -INF

        # Depth 0 -> call quiescence instead of raw evaluation to avoid horizon effect
        if depth == 0:
            return self._quiescence(board, alpha, beta, maximizing, deadline)

        # transposition table lookup (simple)
        tt_key = f"{board.fen}_{depth}_{'M' if maximizing else 'm'}"
        if tt_key in self.tt:
            return self.tt[tt_key][1]

        moves = list(board.legal_moves())
        if not moves:
            # no legal moves
            return -INF if board.turn != self.my_color else INF

        # Move ordering: try captures first (cheap detection), then by shallow eval
        def move_order_key(m: draughts.Move):
            is_cap = m.has_captures
            board.push(m)
            v = self._evaluate_simple(board)
            board.pop()
            # prefer captures and higher eval when maximizing; reverse sorted by caller
            return (1 if is_cap else 0, v)

        moves.sort(key=move_order_key, reverse=maximizing)

        value = -INF if maximizing else INF

        for m in moves:
            # deadline check
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

        # store in TT (simple replace)
        self.tt[tt_key] = (depth, value)
        return value

    # ----------------------------
    # Quiescence search (captures-only)
    # ----------------------------
    def _quiescence(self, board: draughts.Board, alpha: int, beta: int, maximizing: bool,
                    deadline: Optional[float]) -> Optional[int]:
        """
        Quiescence search: extend along capture moves until "quiet".
        Returns int score or None on timeout. Evaluation is always from self.my_color's perspective.
        """

        # deadline check
        if deadline is not None and time.time() > deadline:
            return None

        self.nodes += 1

        stand_pat = self._evaluate_simple(board)

        # If stand_pat is already outside bounds, we can cutoff
        if maximizing:
            if stand_pat >= beta:
                return stand_pat
            if stand_pat > alpha:
                alpha = stand_pat
        else:
            if stand_pat <= alpha:
                return stand_pat
            if stand_pat < beta:
                beta = stand_pat

        # generate capture moves only
        capture_moves = [m for m in board.legal_moves() if m.has_captures]
        if not capture_moves:
            return stand_pat

        # order captures by shallow eval (prefer good captures)
        def cap_key(m):
            board.push(m)
            v = self._evaluate_simple(board)
            board.pop()
            return v

        # For maximizing we want highest first; for minimizing lowest first -> reverse flag
        capture_moves.sort(key=cap_key, reverse=maximizing)

        value = -INF if maximizing else INF

        for m in capture_moves:
            if deadline is not None and time.time() > deadline:
                return None

            board.push(m)
            score = self._quiescence(board, alpha, beta, not maximizing, deadline)
            board.pop()

            if score is None:
                return None

            if maximizing:
                if score > value:
                    value = score
                if value > alpha:
                    alpha = value
            else:
                if score < value:
                    value = score
                if value < beta:
                    beta = value

            if alpha >= beta:
                break

        return value

    # --------
    # Helpers
    # --------
    def _count_pieces(self, board: draughts.Board) -> Tuple[int, int]:
        """
        Count men+kings for (my_color, opp_color) using str(board) (robust ASCII).
        Returns (my_count, opp_count).
        """
        s = str(board)
        my_count = 0
        opp_count = 0
        for ch in s:
            if ch == 'b':
                if self.my_color == draughts.BLACK:
                    my_count += 1
                else:
                    opp_count += 1
            elif ch == 'B':
                if self.my_color == draughts.BLACK:
                    my_count += 1
                else:
                    opp_count += 1
            elif ch == 'w':
                if self.my_color == draughts.WHITE:
                    my_count += 1
                else:
                    opp_count += 1
            elif ch == 'W':
                if self.my_color == draughts.WHITE:
                    my_count += 1
                else:
                    opp_count += 1
        return my_count, opp_count

    # ----------------------------
    # Improved evaluation
    # ----------------------------
    def _evaluate_simple(self, board: draughts.Board) -> int:
        """
        Evaluation from self.my_color's perspective:
         - man = 100, king = 175
         - mobility: small bonus for number of legal moves (signed by whose turn it is)
         - advancement: reward men nearer to promotion (best-effort using ASCII board parsing)
         - capture potential: bonus if current side has capture moves available (penalize if opponent does)
        """
        man_value = 100
        king_value = 175

        s = str(board)
        # count characters for black/white men and kings
        my_man = 0
        my_kings = 0
        opp_man = 0
        opp_kings = 0

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

        # advancement: parse ASCII rows (lines containing '|') if possible
        advancement_bonus = 0
        try:
            lines = [ln for ln in str(board).splitlines() if '|' in ln]
            # lines top->bottom; for each piece char, estimate its row index
            for row_idx, ln in enumerate(lines):
                # find piece characters in the line
                for ch in ln:
                    if ch == 'b':
                        # for black men, advancement increases with row_idx (closer to bottom)
                        adv = row_idx  # 0..(nrows-1)
                        if self.my_color == draughts.BLACK:
                            advancement_bonus += adv * 2
                        else:
                            advancement_bonus -= adv * 2
                    elif ch == 'w':
                        adv = row_idx
                        if self.my_color == draughts.WHITE:
                            advancement_bonus += (len(lines) - 1 - adv) * 2
                        else:
                            advancement_bonus -= (len(lines) - 1 - adv) * 2
                    # kings not considered for advancement
        except Exception:
            # fallback: no advancement info
            advancement_bonus = 0

        # capture potential: check how many immediate capture moves each side has (cheap-ish)
        try:
            my_capture_moves = 0
            opp_capture_moves = 0
            for m in board.legal_moves():
                if m.has_captures:
                    if board.turn == self.my_color:
                        my_capture_moves += 1
                    else:
                        # it's opponent-to-move; but we only know capture potential for side to move.
                        # We'll account for both by temporarily simulating moves for each side below.
                        pass

            # To count opponent capture opportunities, we'll simulate briefly:
            # (iterate legal moves for opponent by flipping turn with a null pseudo-move is tricky,
            # so instead we iterate all legal moves from the current position and test captures
            # after the move for the opponent — a rough proxy.)
            # Better: count capture moves for current side only (mainly what matters).
        except Exception:
            my_capture_moves = 0
            opp_capture_moves = 0

        capture_bonus = 0
        # give a bonus if it's our turn and we have capture moves; penalize if opponent has captures available
        if board.turn == self.my_color:
            capture_bonus += 30 * my_capture_moves
        else:
            # if it's opponent turn and they have captures, that's bad for us
            # check opponent immediate captures quickly by simulating opponent moves
            opp_caps = 0
            for m in board.legal_moves():
                if m.has_captures:
                    opp_caps += 1
            capture_bonus -= 25 * opp_caps

        total = int(material + mobility_bonus + advancement_bonus + capture_bonus)
        return total
