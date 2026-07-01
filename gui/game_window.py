"""
Game Window.

This file controls the actual chess board screen: drawing the board,
handling clicks, keeping track of captured pieces and move history,
detecting when the game ends, and asking the AI for a move when it's
its turn.

The board state itself (whose turn it is, legal moves, checkmate
rules, etc.) is all handled by the `chess` library (python-chess).
We just draw it and react to clicks.
"""

import customtkinter as ctk
import chess
import threading
import time
import os

from PIL import Image, ImageTk
from ai.alphabeta import get_best_move
from engines.stockfish_engine import StockfishEngine


# Filenames for piece images, e.g. "wp" = white pawn, "bk" = black king
PIECE_NAMES = ["wp", "wn", "wb", "wr", "wq", "wk",
               "bp", "bn", "bb", "br", "bq", "bk"]

# Board colors, kept as constants so they're easy to find and change
LIGHT_SQUARE_COLOR = "#EEEED2"
DARK_SQUARE_COLOR = "#769656"
HIGHLIGHT_COLOR = "#F6F669"     # legal move dots / capture rings
SELECTED_COLOR = "#BACA2B"      # the square you clicked on
CHECK_COLOR = "#d9534f"         # red outline around a king in check

# Unicode symbols just for showing captured pieces in the side panel
PIECE_SYMBOLS = {
    chess.PAWN: "♟", chess.KNIGHT: "♞", chess.BISHOP: "♝",
    chess.ROOK: "♜", chess.QUEEN: "♛", chess.KING: "♚"
}


class GameWindow(ctk.CTkToplevel):

    def __init__(self, parent, mode):
        super().__init__(parent)

        self.parent = parent
        self.mode = mode  # "my_ai", "sf_easy", "sf_medium", or "sf_hard"

        # The actual chess game state lives here. Everything about legal
        # moves, check, checkmate etc. comes from this object.
        self.board = chess.Board()

        self.square_size = 80  # each square on the canvas is 80x80 pixels

        # --- selection state, used while the player is picking a move ---
        self.selected_square = None
        self.legal_targets = []   # squares the selected piece can move to

        # --- piece images ---
        self.piece_images = {}        # full-size images, drawn on the board
        self.small_piece_images = {}  # smaller versions, kept loaded in
                                       # case you want a captured-pieces
                                       # icon tray later instead of text

        # --- misc game state ---
        self.flipped = False           # is the board drawn upside down?
        self.waiting_for_ai = False    # blocks clicks while the AI "thinks"
        self.game_over_shown = False   # stops the game-over popup from
                                        # appearing more than once

        # pieces captured so far, stored as piece types (PAWN, KNIGHT...)
        self.captured_white_pieces = []  # white pieces captured by black
        self.captured_black_pieces = []  # black pieces captured by white

        # --- AI thinking state (used by the background thread, see
        # make_ai_move() near the bottom for the full explanation) ---
        self.ai_is_thinking = False
        self.ai_started_at = None
        self.ai_chosen_move = None

        # --- Stockfish engine (only used in sf_easy / sf_medium / sf_hard) ---
        self.stockfish = None

        if self.mode.startswith("sf_"):
            self.stockfish = StockfishEngine(self.mode)

            if not self.stockfish.is_available():
                # Stockfish wasn't found on this computer -> fall back to
                # our own AI so the game still works, and let the player
                # know why once the window has appeared.
                self.mode = "my_ai"
                self.stockfish = None
                self.after(300, self.show_engine_missing_popup)

        self.load_piece_images()
        self.setup_fonts()

        self.title("Chess Game")
        self.geometry("1400x850")
        self.minsize(1100, 700)

        # If the user closes the window with the X button, go back to menu
        # instead of just closing (so the main menu reappears)
        self.protocol("WM_DELETE_WINDOW", self.back_to_menu)

        self.after(50, self.maximize_window)

        self.build_ui()

    # ==================================================================
    # SETUP
    # ==================================================================

    def maximize_window(self):
        """Maximize the window. Windows uses 'zoomed', Linux uses the
        '-zoomed' attribute, so we just try both and ignore failures."""
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                pass

    def setup_fonts(self):
        """All fonts in one place so the look of the app is easy to change."""
        self.font_title = ctk.CTkFont(family="Segoe UI", size=26, weight="bold")
        self.font_subtitle = ctk.CTkFont(family="Segoe UI", size=15)
        self.font_label = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        self.font_status = ctk.CTkFont(family="Segoe UI", size=14)
        self.font_moves = ctk.CTkFont(family="Consolas", size=13)
        self.font_button = ctk.CTkFont(family="Segoe UI", size=14, weight="bold")

    def load_piece_images(self):
        """Loads every piece PNG from assets/pieces and resizes it.
        We keep two sizes: a bigger one for the board, and a smaller one
        in case it's needed elsewhere (e.g. a captured-pieces tray)."""

        for piece in PIECE_NAMES:

            path = os.path.join("assets", "pieces", f"{piece}.png")

            if not os.path.exists(path):
                print(f"Missing piece image: {path}")
                continue

            try:
                image = Image.open(path).convert("RGBA")

                big_version = image.resize((70, 70), Image.LANCZOS)
                self.piece_images[piece] = ImageTk.PhotoImage(big_version)

                small_version = image.resize((26, 26), Image.LANCZOS)
                self.small_piece_images[piece] = ImageTk.PhotoImage(small_version)

            except Exception as error:
                print(f"Error loading {piece}: {error}")

    # ==================================================================
    # BUILDING THE SCREEN LAYOUT
    # ==================================================================

    def build_ui(self):
        """Creates every widget on screen: the board on the left, and a
        panel with game info, move history and buttons on the right."""

        # Two columns: board (fixed width) and side panel (stretches to
        # fill whatever space is left)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.build_board_panel()
        self.build_side_panel()

        self.update_board()

    def build_board_panel(self):
        """The left side: the canvas the board is drawn on, plus a small
        line of text above/below it showing captured pieces."""

        board_outer = ctk.CTkFrame(self, corner_radius=14)
        board_outer.grid(row=0, column=0, padx=20, pady=20, sticky="ns")

        board_frame = ctk.CTkFrame(board_outer, corner_radius=10)
        board_frame.pack(padx=20, pady=20)

        self.board_canvas = ctk.CTkCanvas(
            board_frame,
            width=self.square_size * 8,
            height=self.square_size * 8,
            highlightthickness=0,
            bg="#2b2b2b"
        )
        self.board_canvas.pack()

        # Whenever the player clicks the board, on_square_click runs
        self.board_canvas.bind("<Button-1>", self.on_square_click)

        # Text labels showing which pieces have been captured so far
        self.captured_top_label = ctk.CTkLabel(board_frame, text="", font=self.font_subtitle)
        self.captured_top_label.pack(pady=(10, 0), anchor="w")

        self.captured_bottom_label = ctk.CTkLabel(board_frame, text="", font=self.font_subtitle)
        self.captured_bottom_label.pack(pady=(2, 0), anchor="w")

    def build_side_panel(self):
        """The right side: turn/status info, move history, and buttons.

        We use a CTkScrollableFrame (instead of a plain frame) so that if
        the window is ever small, the content scrolls instead of some
        buttons being pushed off the bottom of the screen and becoming
        invisible. (This was the original 'Main Menu button missing' bug
        — a plain frame doesn't scroll, so when all the widgets stacked
        up taller than the window, the last button or two just ended up
        below the visible area.)"""

        side_outer = ctk.CTkFrame(self, corner_radius=14)
        side_outer.grid(row=0, column=1, padx=(0, 20), pady=20, sticky="nsew")
        side_outer.grid_rowconfigure(0, weight=1)
        side_outer.grid_columnconfigure(0, weight=1)

        side_frame = ctk.CTkScrollableFrame(side_outer, corner_radius=10, label_text="")
        side_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        ctk.CTkLabel(side_frame, text="♟ Chess AI", font=self.font_title).pack(pady=(15, 0))

        mode_names = {
            "my_ai": "My AI (Alpha-Beta)",
            "sf_easy": "Stockfish - Easy",
            "sf_medium": "Stockfish - Medium",
            "sf_hard": "Stockfish - Hard",
        }
        ctk.CTkLabel(
            side_frame,
            text=mode_names.get(self.mode, self.mode),
            font=self.font_subtitle,
            text_color="#9fa8b5"
        ).pack(pady=(2, 15))

        self.build_status_card(side_frame)

        self.ai_info_label = ctk.CTkLabel(side_frame, text="AI Ready", font=self.font_status)
        self.ai_info_label.pack(pady=8)

        self.build_move_history(side_frame)
        self.build_action_buttons(side_frame)

    def build_status_card(self, parent):
        """Small box showing whose turn it is and whether they're in check."""
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(fill="x", padx=10, pady=5)

        self.turn_label = ctk.CTkLabel(card, text="Turn: White", font=self.font_label)
        self.turn_label.pack(pady=(10, 2), padx=10, anchor="w")

        self.status_label = ctk.CTkLabel(
            card, text="Status: Normal", font=self.font_status, text_color="#9fa8b5"
        )
        self.status_label.pack(pady=(0, 10), padx=10, anchor="w")

    def build_move_history(self, parent):
        """A scrollable text box listing every move played, like:
        1. e4 e5
        2. Nf3 Nc6
        """
        ctk.CTkLabel(parent, text="Move History", font=self.font_label).pack(pady=(15, 5))

        self.moves_box = ctk.CTkTextbox(parent, width=260, height=240, font=self.font_moves)
        self.moves_box.pack(pady=5, padx=10, fill="x")
        self.moves_box.configure(state="disabled")  # read-only, player can't type in it

    def build_action_buttons(self, parent):
        """Undo / Flip / New Game / Resign / Main Menu buttons."""

        row1 = ctk.CTkFrame(parent, fg_color="transparent")
        row1.pack(pady=(15, 5), fill="x", padx=10)

        ctk.CTkButton(
            row1, text="Undo", font=self.font_button, command=self.undo_move
        ).pack(side="left", expand=True, fill="x", padx=4)

        ctk.CTkButton(
            row1, text="Flip Board", font=self.font_button, command=self.flip_board
        ).pack(side="left", expand=True, fill="x", padx=4)

        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(pady=5, fill="x", padx=10)

        ctk.CTkButton(
            row2, text="New Game", font=self.font_button, command=self.new_game
        ).pack(side="left", expand=True, fill="x", padx=4)

        ctk.CTkButton(
            row2, text="Resign", font=self.font_button,
            fg_color="#8a3434", hover_color="#6e2828", command=self.resign
        ).pack(side="left", expand=True, fill="x", padx=4)

        ctk.CTkButton(
            parent, text="Main Menu", font=self.font_button,
            fg_color="#3a3f47", hover_color="#2c3036", command=self.back_to_menu
        ).pack(pady=(15, 20), fill="x", padx=10)

    # ==================================================================
    # BUTTON ACTIONS
    # ==================================================================

    def flip_board(self):
        """Rotates the board 180 degrees so the other side is at the bottom."""
        self.flipped = not self.flipped
        self.update_board()

    def undo_move(self):
        """Takes back the last move. If playing against our own AI, we
        take back two moves (the AI's reply and the player's move before
        it) so it becomes the player's turn again."""

        if self.waiting_for_ai:
            return  # don't let the player undo while the AI is mid-thought

        if len(self.board.move_stack) == 0:
            return

        self.board.pop()

        if self.mode == "my_ai" and len(self.board.move_stack) > 0:
            self.board.pop()

        self.rebuild_captured_pieces_from_history()
        self.rebuild_move_history_text()
        self.update_turn_status()
        self.update_board()

    def new_game(self):
        """Resets everything back to the starting position."""

        self.board.reset()

        self.selected_square = None
        self.legal_targets = []
        self.captured_white_pieces = []
        self.captured_black_pieces = []
        self.game_over_shown = False
        self.waiting_for_ai = False
        self.ai_is_thinking = False

        self.rebuild_move_history_text()
        self.update_turn_status()
        self.ai_info_label.configure(text="AI Ready")
        self.update_board()

    def resign(self):
        """Lets the player give up instead of playing on."""
        if not self.game_over_shown:
            self.show_game_over_popup("You resigned. Game over.")

    def back_to_menu(self):
        """Closes this window and shows the main menu again."""
        self.cleanup_engine()
        self.destroy()
        self.parent.deiconify()

    def cleanup_engine(self):
        """Shuts down the Stockfish process (if one was started) so it
        doesn't keep running in the background after this window closes."""
        if self.stockfish:
            self.stockfish.close()

    def is_ai_mode(self):
        """True if it's an AI's job to automatically reply after the
        player moves. Covers both our own AI and Stockfish modes."""
        return self.mode == "my_ai" or self.mode.startswith("sf_")

    def show_engine_missing_popup(self):
        """Lets the player know Stockfish couldn't be found on this
        computer, and that we've switched them to our own AI instead
        for this game."""

        popup = ctk.CTkToplevel(self)
        popup.title("Stockfish Not Found")
        popup.geometry("440x280")
        popup.resizable(False, False)
        popup.grab_set()
        popup.transient(self)

        message = (
            "Stockfish wasn't found on this computer, so this game will "
            "use 'My AI' instead.\n\n"
            "To play against Stockfish, download it from "
            "stockfishchess.org and place the program inside the "
            "'engines' folder (named 'stockfish.exe' on Windows, or "
            "'stockfish' on Mac/Linux)."
        )

        ctk.CTkLabel(
            popup, text=message, font=self.font_status,
            wraplength=380, justify="left"
        ).pack(pady=(25, 15), padx=20)

        ctk.CTkButton(
            popup, text="Got it", font=self.font_button, command=popup.destroy
        ).pack(pady=10)

    # ==================================================================
    # DRAWING THE BOARD
    # ==================================================================
    #
    # The chess library numbers squares 0-63 starting from a1 at the
    # bottom-left. Our canvas draws starting from the top-left, so we
    # need to convert between "chess square" and "screen column/row"
    # every time we draw something. board_to_screen() does that
    # conversion in one place (and also handles the flipped-board case)
    # so the rest of the drawing code doesn't have to think about it.

    def board_to_screen(self, square):
        """Converts a chess square (0-63) into a (column, row) position
        on the canvas, taking into account whether the board is flipped."""

        column = chess.square_file(square)
        row = 7 - chess.square_rank(square)

        if self.flipped:
            column = 7 - column
            row = 7 - row

        return column, row

    def update_board(self):
        """Redraws the entire board: squares, highlights, then pieces on
        top. Called every time something changes (a move, a selection,
        flipping the board, etc.)."""

        self.board_canvas.delete("all")
        self.draw_squares()
        self.draw_highlights()
        self.draw_pieces()
        self.update_captured_pieces_text()

    def draw_squares(self):
        """Draws the checkered background plus the file/rank labels
        (a-h, 1-8) along the edges."""

        for row in range(8):
            for column in range(8):

                x1 = column * self.square_size
                y1 = row * self.square_size
                x2 = x1 + self.square_size
                y2 = y1 + self.square_size

                is_light_square = (row + column) % 2 == 0
                color = LIGHT_SQUARE_COLOR if is_light_square else DARK_SQUARE_COLOR

                self.board_canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline=color)

        files = "abcdefgh"
        ranks = "87654321"

        if self.flipped:
            files = files[::-1]
            ranks = ranks[::-1]

        for column in range(8):
            self.board_canvas.create_text(
                column * self.square_size + self.square_size - 8,
                8 * self.square_size - 8,
                text=files[column], font=("Segoe UI", 9, "bold"), fill="#444"
            )

        for row in range(8):
            self.board_canvas.create_text(
                8, row * self.square_size + 8,
                text=ranks[row], font=("Segoe UI", 9, "bold"), fill="#444", anchor="nw"
            )

    def draw_highlights(self):
        """Draws the selected square, dots/rings showing where the
        selected piece can legally move, and a red outline around a king
        that's currently in check."""

        if self.selected_square is not None:
            column, row = self.board_to_screen(self.selected_square)
            x1, y1 = column * self.square_size, row * self.square_size
            self.board_canvas.create_rectangle(
                x1, y1, x1 + self.square_size, y1 + self.square_size,
                fill=SELECTED_COLOR, outline=SELECTED_COLOR
            )

        for square in self.legal_targets:
            column, row = self.board_to_screen(square)
            x1, y1 = column * self.square_size, row * self.square_size
            x2, y2 = x1 + self.square_size, y1 + self.square_size

            if self.board.piece_at(square):
                # there's an enemy piece here -> draw a ring (capture move)
                self.board_canvas.create_oval(x1 + 4, y1 + 4, x2 - 4, y2 - 4,
                                               outline=HIGHLIGHT_COLOR, width=4)
            else:
                # empty square -> draw a small dot (normal move)
                self.board_canvas.create_oval(x1 + 28, y1 + 28, x2 - 28, y2 - 28,
                                               fill=HIGHLIGHT_COLOR, outline="")

        if self.board.is_check():
            king_square = self.board.king(self.board.turn)
            if king_square is not None:
                column, row = self.board_to_screen(king_square)
                x1, y1 = column * self.square_size, row * self.square_size
                self.board_canvas.create_rectangle(
                    x1, y1, x1 + self.square_size, y1 + self.square_size,
                    outline=CHECK_COLOR, width=4
                )

    def draw_pieces(self):
        """Draws every piece in its current position."""

        for square in chess.SQUARES:

            piece = self.board.piece_at(square)
            if not piece:
                continue

            column, row = self.board_to_screen(square)

            # build the image key, e.g. "P" -> "wp", "n" -> "bn"
            symbol = piece.symbol()
            key = ("w" + symbol.lower()) if symbol.isupper() else ("b" + symbol)

            if key not in self.piece_images:
                continue

            x = column * self.square_size + self.square_size // 2
            y = row * self.square_size + self.square_size // 2
            self.board_canvas.create_image(x, y, image=self.piece_images[key])

    def update_captured_pieces_text(self):
        """Shows the captured pieces as a row of chess symbols, e.g. ♟♟♞"""

        top_text = " ".join(PIECE_SYMBOLS[p] for p in self.captured_black_pieces)
        bottom_text = " ".join(PIECE_SYMBOLS[p] for p in self.captured_white_pieces)

        self.captured_top_label.configure(text=f"Captured: {top_text}")
        self.captured_bottom_label.configure(text=f"Captured: {bottom_text}")

    # ==================================================================
    # HANDLING CLICKS
    # ==================================================================

    def on_square_click(self, event):
        """Runs every time the player clicks on the board canvas."""

        # Ignore clicks while the AI is thinking, or once the game has ended
        if self.waiting_for_ai or self.game_over_shown:
            return

        column = event.x // self.square_size
        row = event.y // self.square_size

        if not (0 <= column <= 7 and 0 <= row <= 7):
            return  # clicked outside the board somehow

        # undo the flip when figuring out which square was actually clicked
        if self.flipped:
            column = 7 - column
            row = 7 - row

        clicked_square = chess.square(column, 7 - row)

        if self.selected_square is None:
            self.try_select_piece(clicked_square)
        else:
            self.try_move_to(clicked_square)

    def try_select_piece(self, square):
        """First click: select a piece if it belongs to the player whose
        turn it is, and show its legal moves."""

        piece = self.board.piece_at(square)

        if piece and piece.color == self.board.turn:
            self.selected_square = square
            self.legal_targets = [
                move.to_square for move in self.board.legal_moves
                if move.from_square == square
            ]
            self.update_board()

    def try_move_to(self, square):
        """Second click: try to move the selected piece to this square.
        If the square instead holds another one of the player's own
        pieces, select that piece instead (so the player can change their
        mind without having to click the original piece again first)."""

        move = chess.Move(self.selected_square, square)

        # Pawn promotion: if a pawn reaches the last rank, python-chess
        # needs us to specify what it promotes to. We always choose a
        # queen here since that's almost always the right choice.
        moving_piece = self.board.piece_at(self.selected_square)
        reaching_last_rank = chess.square_rank(square) in (0, 7)

        if moving_piece and moving_piece.piece_type == chess.PAWN and reaching_last_rank:
            move = chess.Move(self.selected_square, square, promotion=chess.QUEEN)

        if move in self.board.legal_moves:
            self.selected_square = None
            self.legal_targets = []
            self.play_move(move)
            return

        clicked_piece = self.board.piece_at(square)
        if clicked_piece and clicked_piece.color == self.board.turn:
            # reselect a different one of the player's own pieces
            self.try_select_piece(square)
            return

        # invalid click -> just clear the selection
        self.selected_square = None
        self.legal_targets = []
        self.update_board()

    # ==================================================================
    # PLAYING MOVES
    # ==================================================================

    def play_move(self, move):
        """Plays a move made by the human player, updates the screen,
        and then lets the AI reply if needed."""

        if self.board.is_capture(move):
            self.record_capture(move)

        # SAN ("e4", "Nf3", "Qxh7#") has to be generated BEFORE the move
        # is pushed onto the board, since it needs to compare against the
        # position the move was played from.
        move_text = self.board.san(move)
        self.board.push(move)

        self.append_move_to_history(move_text)
        self.update_turn_status()
        self.update_board()

        if self.check_game_over():
            return

        if self.is_ai_mode():
            self.waiting_for_ai = True
            # small delay just so the player's move visibly lands before
            # the "AI thinking" label appears
            self.after(150, self.make_ai_move)

    def record_capture(self, move):
        """Adds the captured piece to the right captured-pieces list."""

        if self.board.is_en_passant(move):
            # en passant captures a pawn that isn't actually on the
            # destination square, so we have to handle it separately
            captured_type = chess.PAWN
            captured_color = not self.board.piece_at(move.from_square).color
        else:
            captured_piece = self.board.piece_at(move.to_square)
            if not captured_piece:
                return
            captured_type = captured_piece.piece_type
            captured_color = captured_piece.color

        if captured_color == chess.WHITE:
            self.captured_white_pieces.append(captured_type)
        else:
            self.captured_black_pieces.append(captured_type)

    def rebuild_captured_pieces_from_history(self):
        """After an undo, the easiest way to get an accurate captured
        list again is to replay the whole game from the start and record
        captures as we go, rather than trying to 'subtract' a capture."""

        self.captured_white_pieces = []
        self.captured_black_pieces = []

        replay_board = chess.Board()

        for move in self.board.move_stack:
            if replay_board.is_capture(move):
                if replay_board.is_en_passant(move):
                    captured_type = chess.PAWN
                    captured_color = not replay_board.piece_at(move.from_square).color
                else:
                    captured_piece = replay_board.piece_at(move.to_square)
                    captured_type = captured_piece.piece_type
                    captured_color = captured_piece.color

                if captured_color == chess.WHITE:
                    self.captured_white_pieces.append(captured_type)
                else:
                    self.captured_black_pieces.append(captured_type)

            replay_board.push(move)

    # ==================================================================
    # MOVE HISTORY TEXT BOX
    # ==================================================================

    def append_move_to_history(self, move_text):
        """Adds one move to the move-history box, formatted in pairs:
        '1. e4 e5  2. Nf3 ...' """

        self.moves_box.configure(state="normal")  # temporarily allow editing

        move_number = (len(self.board.move_stack) + 1) // 2

        if self.board.turn == chess.BLACK:
            # white just moved -> start a new numbered line
            self.moves_box.insert("end", f"{move_number}. {move_text}  ")
        else:
            # black just moved -> finish the line
            self.moves_box.insert("end", f"{move_text}\n")

        self.moves_box.see("end")
        self.moves_box.configure(state="disabled")  # lock it again

    def rebuild_move_history_text(self):
        """Clears and regenerates the move history box from scratch.
        Used after undo, since it's simpler than trying to remove just
        the last entry from the text box."""

        self.moves_box.configure(state="normal")
        self.moves_box.delete("1.0", "end")

        replay_board = chess.Board()

        for index, move in enumerate(self.board.move_stack):
            move_text = replay_board.san(move)

            if index % 2 == 0:
                move_number = (index // 2) + 1
                self.moves_box.insert("end", f"{move_number}. {move_text}  ")
            else:
                self.moves_box.insert("end", f"{move_text}\n")

            replay_board.push(move)

        self.moves_box.see("end")
        self.moves_box.configure(state="disabled")

    def update_turn_status(self):
        """Updates the 'Turn: White/Black' and check indicator labels."""

        current_side = "White" if self.board.turn else "Black"
        self.turn_label.configure(text=f"Turn: {current_side}")

        if self.board.is_check():
            self.status_label.configure(text="Status: Check!", text_color=CHECK_COLOR)
        else:
            self.status_label.configure(text="Status: Normal", text_color="#9fa8b5")

    # ==================================================================
    # GAME OVER
    # ==================================================================

    def check_game_over(self):
        """Checks if the game has ended and shows the popup if so.
        Returns True if the game is over (so callers know to stop)."""

        if self.board.is_game_over():
            self.show_game_over_popup(self.describe_result())
            return True

        return False

    def describe_result(self):
        """Turns the game-ending condition into a readable message."""

        board = self.board

        if board.is_checkmate():
            # the side whose turn it is just got checkmated, so the OTHER
            # side is the winner
            winner = "Black" if board.turn == chess.WHITE else "White"
            return f"Checkmate!\n{winner} wins."

        if board.is_stalemate():
            return "Draw by stalemate."

        if board.is_insufficient_material():
            return "Draw - insufficient material."

        if board.is_seventyfive_moves():
            return "Draw - 75 move rule."

        if board.is_fivefold_repetition():
            return "Draw - fivefold repetition."

        if board.can_claim_draw():
            return "Draw."

        return "Game over."

    def show_game_over_popup(self, message):
        """Pops up a small window announcing the result, with buttons to
        either start a new game or go back to the main menu."""

        self.game_over_shown = True
        self.waiting_for_ai = False

        popup = ctk.CTkToplevel(self)
        popup.title("Game Over")
        popup.geometry("380x240")
        popup.resizable(False, False)
        popup.grab_set()       # blocks clicks on the main window until closed
        popup.transient(self)  # keeps it on top of the game window

        ctk.CTkLabel(
            popup, text=message, font=self.font_title, justify="center"
        ).pack(pady=(35, 20), padx=20)

        button_row = ctk.CTkFrame(popup, fg_color="transparent")
        button_row.pack(pady=10)

        def restart_game():
            popup.destroy()
            self.new_game()

        def go_to_menu():
            popup.destroy()
            self.back_to_menu()

        ctk.CTkButton(
            button_row, text="New Game", font=self.font_button, command=restart_game
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            button_row, text="Main Menu", font=self.font_button,
            fg_color="#3a3f47", hover_color="#2c3036", command=go_to_menu
        ).pack(side="left", padx=10)

    # ==================================================================
    # AI MOVE
    # ==================================================================
    #
    # WHY A BACKGROUND THREAD?
    # get_best_move() can take a second or more to think. Tkinter (the
    # GUI library customtkinter is built on) runs everything on a single
    # thread — if we called get_best_move() directly here, the whole
    # window would freeze while it thinks, and the "AI thinking..." timer
    # couldn't update either, since updating the label also needs that
    # same thread.
    #
    # The fix is to run get_best_move() on a separate background thread,
    # so the GUI thread stays free to keep redrawing the timer label every
    # 100ms. The background thread isn't allowed to touch the GUI itself
    # (that's not safe in tkinter), so it just stores its answer in
    # `self.ai_chosen_move`, and the GUI thread picks that answer up once
    # it's ready and applies the move.

    def make_ai_move(self):
        """Kicks off the AI's move calculation in the background."""

        if not self.is_ai_mode():
            self.waiting_for_ai = False
            return

        if self.board.is_game_over():
            self.waiting_for_ai = False
            return

        self.ai_is_thinking = True
        self.ai_started_at = time.time()
        self.ai_chosen_move = None

        background_thread = threading.Thread(target=self.calculate_ai_move, daemon=True)
        background_thread.start()

        self.poll_ai_progress()

    def calculate_ai_move(self):
        """Runs on the BACKGROUND thread. Must not touch any GUI widgets
        directly — it only writes a plain value to self.ai_chosen_move,
        which the main thread reads later."""

        if self.mode == "my_ai":
            self.ai_chosen_move = get_best_move(self.board, depth=3)
        elif self.stockfish:
            self.ai_chosen_move = self.stockfish.get_best_move(self.board)

        self.ai_is_thinking = False

    def poll_ai_progress(self):
        """Runs on the MAIN (GUI) thread, called repeatedly every 100ms
        while the AI thinks. Updates the live timer, and once the
        background thread is done, applies the chosen move."""

        elapsed_seconds = time.time() - self.ai_started_at

        if self.ai_is_thinking:
            self.ai_info_label.configure(text=f"AI thinking... {elapsed_seconds:.1f}s")
            self.after(100, self.poll_ai_progress)  # check again in 100ms
            return

        self.ai_info_label.configure(text=f"AI moved in {elapsed_seconds:.2f}s")
        self.waiting_for_ai = False

        move = self.ai_chosen_move
        if move:
            self.apply_ai_move(move)

    def apply_ai_move(self, move):
        """Plays the move the AI decided on and updates the screen."""

        if self.board.is_capture(move):
            self.record_capture(move)

        move_text = self.board.san(move)
        self.board.push(move)

        self.append_move_to_history(move_text)
        self.update_turn_status()
        self.update_board()

        self.check_game_over()