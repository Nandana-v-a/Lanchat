"""Login window for choosing a LAN chat username."""

from __future__ import annotations

import socket
import tkinter as tk
from tkinter import messagebox, ttk


class LoginWindow(tk.Tk):
    """Simple username prompt shown before the chat window starts."""

    def __init__(self) -> None:
        super().__init__()
        self.title("LANChat Login")
        self.resizable(False, False)
        self.username: str | None = None

        default_name = socket.gethostname()
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Username").pack(anchor="w")
        self.username_var = tk.StringVar(value=default_name)
        entry = ttk.Entry(frame, textvariable=self.username_var, width=32)
        entry.pack(fill="x", pady=(6, 12))
        entry.focus_set()
        entry.selection_range(0, tk.END)

        ttk.Button(frame, text="Start Chat", command=self._submit).pack(fill="x")
        self.bind("<Return>", lambda _event: self._submit())

    def _submit(self) -> None:
        username = self.username_var.get().strip()
        if not username:
            messagebox.showerror("Username required", "Please enter a username.")
            return
        self.username = username
        self.destroy()


def ask_username() -> str | None:
    window = LoginWindow()
    window.mainloop()
    return window.username
