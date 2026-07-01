"""
Main Menu screen.

This is the first window the user sees. It just shows a title and a
few buttons to choose how they want to play. When a button is
clicked, we hide this window and open a GameWindow on top of it.
"""

import customtkinter as ctk
from gui.game_window import GameWindow

# Theme settings for the whole app (customtkinter applies these globally)
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MainMenu(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Meem Chess")
        self.geometry("900x750")

        # Start the window maximized. We do this with `after()` instead of
        # calling it directly because the window needs a moment to finish
        # being created first, otherwise some systems ignore the request.
        self.after(50, self.maximize_window)

        # Fonts used on this screen, defined once so they're easy to tweak
        self.font_title = ctk.CTkFont(family="Segoe UI", size=40, weight="bold")
        self.font_subtitle = ctk.CTkFont(family="Segoe UI", size=16)
        self.font_button = ctk.CTkFont(family="Segoe UI", size=18, weight="bold")
        self.font_footer = ctk.CTkFont(family="Segoe UI", size=12)

        self.build_ui()

    def maximize_window(self):
        """Try to maximize the window. Windows uses 'zoomed', Linux uses
        the '-zoomed' attribute instead, so we try both."""
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                pass  # if neither works, just leave it at the normal size

    def build_ui(self):
        """Creates all the widgets on the menu screen."""

        # A card centered on the screen, instead of buttons floating
        # directly on the background. Makes the screen feel designed
        # rather than empty.
        card = ctk.CTkFrame(self, corner_radius=20)
        card.place(relx=0.5, rely=0.5, anchor="center")

        title = ctk.CTkLabel(card, text="♟ MEEM CHESS ", font=self.font_title)
        title.pack(pady=(45, 5), padx=80)

        subtitle = ctk.CTkLabel(
            card,
            text="Play against your own Alpha-Beta engine or Stockfish",
            font=self.font_subtitle,
            text_color="#9fa8b5"
        )
        subtitle.pack(pady=(0, 35))

        # Each button starts a game in a different mode. The mode string
        # ("my_ai", "sf_easy", etc.) is what GameWindow uses later to
        # decide which engine to play against.
        self.add_mode_button(card, "🤖  My AI (Alpha Beta)", "my_ai")
        self.add_mode_button(card, "🟢  Stockfish Easy", "sf_easy")
        self.add_mode_button(card, "🟠  Stockfish Medium", "sf_medium")
        self.add_mode_button(card, "🔴  Stockfish Hard", "sf_hard")

        exit_btn = ctk.CTkButton(
            card,
            text="Exit",
            width=320,
            height=45,
            font=self.font_button,
            fg_color="#8a3434",
            hover_color="#6e2828",
            command=self.destroy
        )
        exit_btn.pack(pady=(25, 20))

        footer = ctk.CTkLabel(
            card,
            text="v0.2  •  built with python-chess + customtkinter",
            font=self.font_footer,
            text_color="#6b7280"
        )
        footer.pack(pady=(0, 25))

    def add_mode_button(self, parent, text, mode):
        """Small helper so we don't repeat the same button code four times."""
        button = ctk.CTkButton(
            parent,
            text=text,
            width=320,
            height=60,
            font=self.font_button,
            command=lambda: self.start_game(mode)
        )
        button.pack(pady=8)
        return button

    def start_game(self, mode):
        """Hide the menu and open the game window in the chosen mode."""
        self.withdraw()
        GameWindow(self, mode)