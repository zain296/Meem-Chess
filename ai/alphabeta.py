"""
Alpha-Beta search.

This is the "brain" that picks the AI's move. It works by looking a
few moves ahead (controlled by `depth`) and picking whichever move
leads to the position `ai/evaluation.py` scores best for the AI,
assuming the opponent always plays their best reply too.

Alpha-beta pruning is just a way to skip branches of that search that
can't possibly change the result, so we don't waste time fully
exploring moves we already know are worse than one we've already
found.
"""

import chess
import math

from ai.evaluation import evaluate

# Rough point values, only used here for sorting moves (the real
# scoring of a position happens in evaluation.py)
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000
}


def order_moves(board, moves):
    """
    Sorts moves so that captures are checked before quiet moves, and
    among captures, the ones that win the most material are checked
    first (e.g. "pawn takes queen" before "queen takes pawn").

    This doesn't change which move is eventually picked — alpha-beta
    still considers every move that matters. It just lets the pruning
    in alphabeta() throw away bad branches much faster, since a strong
    move found early lets us skip a lot of the weaker ones entirely.
    This is the main reason the AI feels noticeably faster than before.
    """

    def move_priority(move):

        if board.is_capture(move):

            victim = board.piece_at(move.to_square)
            attacker = board.piece_at(move.from_square)

            # en passant captures a pawn that isn't actually sitting on
            # the destination square, so `victim` can be None there
            victim_value = PIECE_VALUES.get(victim.piece_type, 100) if victim else 100
            attacker_value = PIECE_VALUES.get(attacker.piece_type, 0) if attacker else 0

            # capturing a big piece with a small piece scores highest
            return 10_000 + victim_value - attacker_value

        if move.promotion:
            return 5_000  # promoting a pawn is usually very strong too

        return 0  # an ordinary, non-capturing move

    return sorted(moves, key=move_priority, reverse=True)


def alphabeta(board, depth, alpha, beta, maximizing_player):
    """
    The recursive search itself.

    - depth: how many more moves ahead to look before stopping and
      just scoring the position directly.
    - alpha: the best score the maximizing player (the AI) has found
      a way to guarantee so far.
    - beta: the best score the minimizing player (the opponent) has
      found a way to guarantee so far.
    - maximizing_player: True if it's the AI's turn to move in this
      branch of the search, False if it's the opponent's turn.

    Whenever alpha >= beta, it means the opponent already has a better
    option elsewhere, so there's no point looking any further down
    this branch — that's the "pruning" part, and it's what `break` does
    below.
    """

    if depth == 0 or board.is_game_over():
        return evaluate(board)

    candidate_moves = order_moves(board, board.legal_moves)

    if maximizing_player:

        best_score = -math.inf

        for move in candidate_moves:

            board.push(move)
            score = alphabeta(board, depth - 1, alpha, beta, False)
            board.pop()

            best_score = max(best_score, score)
            alpha = max(alpha, best_score)

            if beta <= alpha:
                break  # the opponent won't ever let us reach this branch

        return best_score

    else:

        best_score = math.inf

        for move in candidate_moves:

            board.push(move)
            score = alphabeta(board, depth - 1, alpha, beta, True)
            board.pop()

            best_score = min(best_score, score)
            beta = min(beta, best_score)

            if beta <= alpha:
                break  # we won't ever let the opponent reach this branch

        return best_score


def get_best_move(board, depth=3):
    """
    Tries every legal move in the current position, scores each one
    using alphabeta(), and returns whichever move scored the best for
    whoever's turn it currently is.
    """

    best_move = None
    best_score = -math.inf

    candidate_moves = order_moves(board, board.legal_moves)

    for move in candidate_moves:

        board.push(move)
        score = alphabeta(board, depth - 1, -math.inf, math.inf, False)
        board.pop()

        if score > best_score:
            best_score = score
            best_move = move

    return best_move