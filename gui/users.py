"""Online users list UI components."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from discovery import Peer


class UsersPanel(ttk.Frame):
    """Listbox wrapper for online LAN users."""

    def __init__(self, master: tk.Misc, on_select: Callable[[Peer], None]) -> None:
        super().__init__(master, padding=8)
        self.on_select = on_select
        self._peers: list[Peer] = []

        ttk.Label(self, text="Online Users").pack(anchor="w")
        self.listbox = tk.Listbox(self, height=18, exportselection=False)
        self.listbox.pack(fill="both", expand=True, pady=(6, 0))
        self.listbox.bind("<<ListboxSelect>>", self._handle_select)

    def set_peers(self, peers: list[Peer]) -> None:
        selected_peer = self.selected_peer()
        selected_id = selected_peer.peer_id if selected_peer else None
        self._peers = sorted(peers, key=lambda peer: peer.username.lower())

        self.listbox.delete(0, tk.END)
        selected_index = None
        for index, peer in enumerate(self._peers):
            self.listbox.insert(tk.END, f"{peer.username}  ({peer.ip}:{peer.tcp_port})")
            if peer.peer_id == selected_id:
                selected_index = index

        if selected_index is not None:
            self.listbox.selection_set(selected_index)

    def selected_peer(self) -> Peer | None:
        selection = self.listbox.curselection()
        if not selection:
            return None
        return self._peers[selection[0]]

    def _handle_select(self, _event: tk.Event) -> None:
        peer = self.selected_peer()
        if peer:
            self.on_select(peer)
