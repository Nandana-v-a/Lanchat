"""Online users list UI components."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from discovery import Peer


class UsersPanel(ttk.Frame):
    """Listbox wrapper for online LAN users."""

    def __init__(self, master: tk.Misc, on_select: Callable[[Peer | None], None]) -> None:
        super().__init__(master, padding=8)
        self.on_select = on_select
        self._peers: list[Peer] = []

        ttk.Label(self, text="Chats").pack(anchor="w")
        self.listbox = tk.Listbox(self, height=18, exportselection=False)
        self.listbox.pack(fill="both", expand=True, pady=(6, 0))
        self.listbox.bind("<<ListboxSelect>>", self._handle_select)

    def set_peers(self, peers: list[Peer]) -> None:
        selected_index_before = self.listbox.curselection()
        group_selected = bool(selected_index_before and selected_index_before[0] == 0)
        selected_peer = self.selected_peer()
        selected_id = selected_peer.peer_id if selected_peer else None
        self._peers = sorted(peers, key=lambda peer: peer.username.lower())

        self.listbox.delete(0, tk.END)
        self.listbox.insert(tk.END, "[GR] Group Chat  (all online)")
        selected_index = 0 if group_selected else None
        for index, peer in enumerate(self._peers):
            self.listbox.insert(
                tk.END,
                f"[{self._initials(peer.username)}] {peer.username}  ({peer.ip}:{peer.tcp_port})",
            )
            if peer.peer_id == selected_id:
                selected_index = index + 1

        if selected_index is not None:
            self.listbox.selection_set(selected_index)

    def selected_peer(self) -> Peer | None:
        selection = self.listbox.curselection()
        if not selection:
            return None
        index = selection[0]
        if index == 0:
            return None
        return self._peers[index - 1]

    def _handle_select(self, _event: tk.Event) -> None:
        selection = self.listbox.curselection()
        if selection:
            self.on_select(self.selected_peer())

    @staticmethod
    def _initials(username: str) -> str:
        parts = [part for part in username.strip().split() if part]
        if not parts:
            return "??"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return f"{parts[0][0]}{parts[-1][0]}".upper()
