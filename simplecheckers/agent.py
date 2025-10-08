import re
import time
import random
import logging
import draughts
from typing import Optional, Tuple, Dict, List, Any

log = logging.getLogger("red.crab-cogs.simplecheckers.agent")

INF = 10**9


class EvalState:
    """Incremental evaluation state for pydraughts boards."""

    def __init__(self, board, my_color):
        self.my_color = my_color
        self.opp_color = draughts.WHITE if my_color == draughts.BLACK else draughts.BLACK

        self.man_value = 100
        self.king_value = 175

        # piece counts
        self.my_man = 0
        self.my_kings = 0
        self.opp_man = 0
        self.opp_kings = 0

        # stack to support undo
        self.history = []

        # initialize from FEN
        self.init_counts_from_fen(board)

    def init_counts_from_fen(self, board):
        """Parse pydraughts FEN (e.g., B:W16,19,31,K4:B17,25,K26)"""
        self.my_man = self.my_kings = self.opp_man = self.opp_kings = 0
        fen = board.fen

        w_match = re.search(r'W([K\d,]*)', fen)
        b_match = re.search(r'B([K\d,]*)', fen)

        w_squares = w_match.group(1) if w_match else ''
        b_squares = b_match.group(1) if b_match else ''

        def count_pieces(squares_str, color):
            man = king = 0
            for part in squares_str.split(','):
                part = part.strip()
                if not part:
                    continue
                if part.startswith('K'):
                    king += 1
                else:
                    man += 1
            if color == self.my_color:
                self.my_man += man
                self.my_kings += king
            else:
                self.opp_man += man
                self.opp_kings += king

        count_pieces(w_squares, draughts.WHITE)
        count_pieces(b_squares, draughts.BLACK)

    def material_score(self):
        """Return current material score from agent's perspective."""
        my_score = self.my_man * self.man_value + self.my_kings * self.king_value
        opp_score = self.opp_man * self.man_value + self.opp_kings * self.king_value
        return my_score - opp_score

    def apply_move(self, board, move):
        """Update counts incrementally on push(move)."""
        delta = {"my_man": 0, "my_kings": 0, "opp_man": 0, "opp_kings": 0}

        # handle captures: check squares BEFORE move is pushed
        fen_before = board.fen
        for sq in getattr(move, "captures", []):
            # regex search for K<number> first
            if re.search(rf'\bK{sq}\b', fen_before):
                # king captured
                if board.turn == self.my_color:
                    delta["opp_kings"] -= 1
                else:
                    delta["my_kings"] -= 1
            elif re.search(rf'\b{sq}\b', fen_before):
                # man captured
                if board.turn == self.my_color:
                    delta["opp_man"] -= 1
                else:
                    delta["my_man"] -= 1

        # handle promotion: check if final square is now a king AFTER push
        board.push(move)
        fen_after = board.fen
        board.pop()

        final_sq = move.steps_move[-1]
        if board.turn == self.my_color:
            if re.search(rf'\bK{final_sq}\b', fen_after):
                delta["my_man"] -= 1
                delta["my_kings"] += 1
        else:
            if re.search(rf'\bK{final_sq}\b', fen_after):
                delta["opp_man"] -= 1
                delta["opp_kings"] += 1

        # apply delta
        self.my_man += delta["my_man"]
        self.my_kings += delta["my_kings"]
        self.opp_man += delta["opp_man"]
        self.opp_kings += delta["opp_kings"]

        # save for undo
        self.history.append(delta)

    def undo_move(self):
        """Revert counts on pop()."""
        delta = self.history.pop()
        self.my_man -= delta["my_man"]
        self.my_kings -= delta["my_kings"]
        self.opp_man -= delta["opp_man"]
        self.opp_kings -= delta["opp_kings"]


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
        self.tt: Dict[str, Tuple[int, int]] = {}  # simple transposition table
        self.nodes = 0

    # ----------------------------
    # Public API
    # ----------------------------
    def choose_move(self, board: draughts.Board, max_depth: int, time_limit: Optional[float] = None):
        board = board.copy()
        eval_state = EvalState(board, self.my_color)

        start_time = time.time()
        deadline = start_time + time_limit if time_limit is not None else None

        root_moves = list(board.legal_moves())
        if not root_moves:
            return None
        if len(root_moves) == 1:
            return root_moves[0]

        best_score = -INF
        move_scores: List[Tuple[Any, int]] = []

        for depth in range(1, max_depth + 1):
            self.nodes = 0
            depth_results: List[Tuple[Any, int]] = []
            depth_best_score = -INF

            elapsed = time.time() - start_time
            time_remaining = time_limit - elapsed if time_limit else None
            allow_overrun = time_limit is not None and time_remaining is not None and time_remaining > (time_limit * 2.0/3.0)
            per_depth_deadline = deadline
            overrunning = False

            # quick root move ordering: capture moves first, then shallow eval
            def quick_score(m: draughts.Move):
                is_cap = getattr(m, "captures", None) or getattr(m, "has_captures", False)
                eval_state.apply_move(board, m)
                val = self._evaluate_simple(board, eval_state)
                eval_state.undo_move()
                return (1 if is_cap else 0, val)

            root_moves.sort(key=quick_score, reverse=(board.turn == self.my_color))

            timed_out = False
            for m in root_moves:
                if per_depth_deadline is not None and time.time() > per_depth_deadline:
                    if allow_overrun and not overrunning:
                        overrunning = True
                        per_depth_deadline = None
                        log.debug(f"Allowing overrun to finish current depth {depth}")
                    else:
                        timed_out = True
                        break

                eval_state.apply_move(board, m)
                board.push(m)
                score = self._alphabeta(board, eval_state, depth - 1, -INF, INF,
                                        maximizing=(board.turn != self.my_color),
                                        deadline=per_depth_deadline)
                board.pop()
                eval_state.undo_move()

                if score is None:
                    if allow_overrun and not overrunning:
                        overrunning = True
                        per_depth_deadline = None
                        eval_state.apply_move(board, m)
                        board.push(m)
                        score = self._alphabeta(board, eval_state, depth - 1, -INF, INF,
                                                maximizing=(board.turn != self.my_color),
                                                deadline=None)
                        board.pop()
                        eval_state.undo_move()
                        if score is None:
                            timed_out = True
                            break
                    else:
                        timed_out = True
                        break

                depth_results.append((m, score))
                if score > depth_best_score:
                    depth_best_score = score

            if not timed_out and depth_results:
                move_scores = depth_results
                best_score = depth_best_score
            else:
                log.debug(f"Timed out or no results at depth {depth}")
                break

            log.info(f"Depth {depth} completed. {self.nodes=}, {best_score=}, elapsed={int(elapsed*1000)}ms")

        if not move_scores:
            return None

        MARGIN = 10
        candidates = [m for m, score in move_scores if score >= best_score - MARGIN]
        return random.choice(candidates)

    # ----------------------------
    # Alpha-beta search
    # ----------------------------
    def _alphabeta(self, board: draughts.Board, eval_state: 'EvalState',
                   depth: int, alpha: int, beta: int, maximizing: bool,
                   deadline: Optional[float]) -> Optional[int]:

        if deadline is not None and time.time() > deadline:
            return None

        self.nodes += 1

        if board.is_over():
            win = board.winner()
            if win is None:
                return 0
            return INF if win == self.my_color else -INF

        if depth == 0:
            return self._quiescence(board, eval_state, alpha, beta, maximizing, deadline)

        tt_key = f"{board.fen}_{depth}_{'M' if maximizing else 'm'}"
        if tt_key in self.tt:
            return self.tt[tt_key][1]

        moves = list(board.legal_moves())
        if not moves:
            return -INF if board.turn != self.my_color else INF

        def move_order_key(m):
            is_cap = getattr(m, "captures", None) or getattr(m, "has_captures", False)
            eval_state.apply_move(board, m)
            board.push(m)
            v = self._evaluate_simple(board, eval_state)
            board.pop()
            eval_state.undo_move()
            return (1 if is_cap else 0, v)

        moves.sort(key=move_order_key, reverse=maximizing)

        value = -INF if maximizing else INF
        for m in moves:
            if deadline is not None and time.time() > deadline:
                return None

            eval_state.apply_move(board, m)
            board.push(m)
            child_score = self._alphabeta(board, eval_state, depth - 1, alpha, beta,
                                          not maximizing, deadline)
            board.pop()
            eval_state.undo_move()

            if child_score is None:
                return None

            if maximizing:
                value = max(value, child_score)
                alpha = max(alpha, value)
            else:
                value = min(value, child_score)
                beta = min(beta, value)

            if alpha >= beta:
                break

        self.tt[tt_key] = (depth, value)
        return value

    # ----------------------------
    # Quiescence search
    # ----------------------------
    def _quiescence(self, board: draughts.Board, eval_state: 'EvalState',
                     alpha: int, beta: int, maximizing: bool,
                     deadline: Optional[float]) -> Optional[int]:

        if deadline is not None and time.time() > deadline:
            return None

        self.nodes += 1
        stand_pat = self._evaluate_simple(board, eval_state)

        if maximizing:
            if stand_pat >= beta:
                return stand_pat
            alpha = max(alpha, stand_pat)
        else:
            if stand_pat <= alpha:
                return stand_pat
            beta = min(beta, stand_pat)

        capture_moves = [m for m in board.legal_moves() if getattr(m, "captures", None) or getattr(m, "has_captures", False)]
        if not capture_moves:
            return stand_pat

        def cap_key(m):
            eval_state.apply_move(board, m)
            board.push(m)
            v = self._evaluate_simple(board, eval_state)
            board.pop()
            eval_state.undo_move()
            return v

        capture_moves.sort(key=cap_key, reverse=maximizing)

        value = -INF if maximizing else INF
        for m in capture_moves:
            if deadline is not None and time.time() > deadline:
                return None
            eval_state.apply_move(board, m)
            board.push(m)
            score = self._quiescence(board, eval_state, alpha, beta, not maximizing, deadline)
            board.pop()
            eval_state.undo_move()

            if score is None:
                return None

            if maximizing:
                value = max(value, score)
                alpha = max(alpha, value)
            else:
                value = min(value, score)
                beta = min(beta, value)

            if alpha >= beta:
                break

        return value

    # ----------------------------
    # Incremental evaluation helper
    # ----------------------------
    def _evaluate_simple(self, board: draughts.Board, eval_state: 'EvalState') -> int:
        """
        Fast incremental evaluation:
         - material from EvalState
         - mobility: number of legal moves
        """
        mobility = len(board.legal_moves()) * (1 if board.turn == self.my_color else -1) * 10
        return eval_state.material_score() + mobility
