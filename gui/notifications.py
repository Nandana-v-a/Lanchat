"""Small popup notifications for incoming chat messages."""

from __future__ import annotations

import tkinter as tk
from typing import Callable


class MessageNotifier:
    """Displays short-lived message popups above the taskbar."""

    def __init__(self, master: tk.Tk, on_open: Callable[[str], None]) -> None:
        self.master = master
        self.on_open = on_open
        self._active: tk.Toplevel | None = None

    def show(self, peer_id: str, sender_name: str, body: str) -> None:
        self.dismiss()

        popup = tk.Toplevel(self.master)
        popup.title("LANChat message")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        popup.overrideredirect(True)
        popup.configure(background="#2563eb")

        frame = tk.Frame(popup, background="#ffffff", padx=14, pady=12)
        frame.pack(fill="both", expand=True, padx=(4, 0))

        title = tk.Label(
            frame,
            text="New LANChat message",
            background="#ffffff",
            foreground="#667085",
            font=("Segoe UI", 8, "bold"),
        )
        title.pack(anchor="w")

        sender = tk.Label(
            frame,
            text=sender_name,
            background="#ffffff",
            foreground="#18202a",
            font=("Segoe UI", 11, "bold"),
        )
        sender.pack(anchor="w")

        preview = tk.Label(
            frame,
            text=self._preview(body),
            background="#ffffff",
            foreground="#344054",
            font=("Segoe UI", 9),
            wraplength=280,
            justify="left",
        )
        preview.pack(anchor="w", pady=(6, 0))

        for widget in (popup, frame, title, sender, preview):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda _event, selected_id=peer_id: self._open(selected_id))

        popup.update_idletasks()
        width = max(320, popup.winfo_reqwidth())
        height = popup.winfo_reqheight()
        x = self.master.winfo_screenwidth() - width - 24
        y = self.master.winfo_screenheight() - height - 64
        popup.geometry(f"{width}x{height}+{x}+{y}")

        self._active = popup
        popup.after(5000, self.dismiss)

    def dismiss(self) -> None:
        if self._active and self._active.winfo_exists():
            self._active.destroy()
        self._active = None

    def _open(self, peer_id: str) -> None:
        self.dismiss()
        self.master.deiconify()
        self.master.lift()
        self.master.focus_force()
        self.on_open(peer_id)

    @staticmethod
    def _preview(body: str) -> str:
        cleaned = " ".join(body.split())
        if len(cleaned) <= 140:
            return cleaned
        return f"{cleaned[:137]}..."
