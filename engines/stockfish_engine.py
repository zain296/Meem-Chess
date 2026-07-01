

import os
import chess
import chess.engine



STOCKFISH_PATH = r"C:\Users\Zain\Downloads\Drive\Programing\ai\Projects\Chess APP\assets\stockfish.exe"  


DIFFICULTY_SETTINGS = {
    "sf_easy":   {"elo": 250,  "skill_level": 0,  "think_time": 0.05, "depth": 1},
    "sf_medium": {"elo": 800,  "skill_level": 3,  "think_time": 0.2,  "depth": 3},
    "sf_hard":   {"elo": 1500, "skill_level": 10, "think_time": 0.8,  "depth": 8},
}


class StockfishEngine:

    def __init__(self, mode):
        """Starts the Stockfish process and configures its difficulty.
        If Stockfish can't be found or fails to start, self.engine
        stays None and is_available() will return False — the caller
        is expected to check that and handle it gracefully."""

        self.mode = mode
        self.settings = DIFFICULTY_SETTINGS.get(mode, DIFFICULTY_SETTINGS["sf_medium"])
        self.engine = None

        if not STOCKFISH_PATH:
            print("Stockfish path not set. Edit STOCKFISH_PATH in stockfish_engine.py.")
            return

        if not os.path.isfile(STOCKFISH_PATH):
            print(f"Stockfish not found at: {STOCKFISH_PATH}")
            print("Please update STOCKFISH_PATH in stockfish_engine.py.")
            return

        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
            self.configure_difficulty()
        except Exception as error:
            print(f"Could not start Stockfish: {error}")
            self.engine = None

    def configure_difficulty(self):
        """Tells the running Stockfish process how strong to play.
        Applies Skill Level first (always works), then tries to also
        enable ELO limiting for a more human-like feel."""

        # Skill Level (0–20) is always supported — apply it first
        try:
            self.engine.configure({"Skill Level": self.settings["skill_level"]})
        except Exception as error:
            print(f"Could not set Skill Level: {error}")

        # Also try ELO limiting — makes easy/medium feel much weaker
        try:
            self.engine.configure({
                "UCI_LimitStrength": True,
                "UCI_Elo": self.settings["elo"],
            })
        except Exception:
            pass  # older builds don't support this, that's fine

    def is_available(self):
        """True if Stockfish started successfully and is ready to play."""
        return self.engine is not None

    def get_best_move(self, board):
        """Asks Stockfish for its move in the given position.
        Returns None if the engine isn't available."""

        if not self.engine:
            return None

        # On easy/medium, occasionally play a random legal move to simulate
        # blunders — makes the engine feel genuinely human and beatable.
        blunder_chance = {"sf_easy": 0.4, "sf_medium": 0.15, "sf_hard": 0.0}
        chance = blunder_chance.get(self.mode, 0.0)
        if chance > 0:
            import random
            if random.random() < chance:
                return random.choice(list(board.legal_moves))

        limit = chess.engine.Limit(time=self.settings["think_time"], depth=self.settings["depth"])

        result = self.engine.play(board, limit)
        return result.move

    def close(self):
        """Shuts down the Stockfish process. Always call this when
        you're done with the engine, otherwise the process can keep
        running in the background after the window closes."""

        if self.engine:
            try:
                self.engine.quit()
            except Exception:
                pass
            self.engine = None