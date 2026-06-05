"""Main chat window UI."""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox, ttk

from database import ChatDatabase
from discovery import DiscoveryService, Peer
from gui.users import UsersPanel
from server import ChatMessage, MessageServer, send_message


class ChatWindow(tk.Tk):
    """Main Version 1.0 LAN chat interface."""

    def __init__(self, username: str) -> None:
        super().__init__()
        self.username = username
        self.title(f"LANChat - {username}")
        self.geometry("860x560")
        self.minsize(720, 460)

        self.db = ChatDatabase()
        self.event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.peers: dict[str, Peer] = {}
        self.active_peer: Peer | None = None

        self.server = MessageServer(self._queue_message)
        tcp_port = self.server.start()
        self.discovery = DiscoveryService(username, tcp_port, self._queue_peer)
        self.discovery.start()

        self._build_layout()
        self._refresh_peers()
        self._poll_events()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_layout(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.users_panel = UsersPanel(self, self._select_peer)
        self.users_panel.grid(row=0, column=0, sticky="nsw")

        chat_frame = ttk.Frame(self, padding=(8, 8, 8, 8))
        chat_frame.grid(row=0, column=1, sticky="nsew")
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(1, weight=1)

        self.header_var = tk.StringVar(value="Select an online user")
        ttk.Label(chat_frame, textvariable=self.header_var, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self.history = tk.Text(chat_frame, wrap="word", state="disabled", height=18)
        self.history.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        self.history.tag_configure("in", foreground="#1f4e79")
        self.history.tag_configure("out", foreground="#0b6b35")
        self.history.tag_configure("meta", foreground="#777777")

        composer = ttk.Frame(chat_frame)
        composer.grid(row=2, column=0, sticky="ew")
        composer.columnconfigure(0, weight=1)

        self.message_var = tk.StringVar()
        entry = ttk.Entry(composer, textvariable=self.message_var)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        entry.bind("<Return>", lambda _event: self._send_current_message())
        ttk.Button(composer, text="Send", command=self._send_current_message).grid(
            row=0, column=1
        )

    def _queue_peer(self, peer: Peer) -> None:
        self.event_queue.put(("peer", peer))

    def _queue_message(self, message: ChatMessage) -> None:
        self.event_queue.put(("message", message))

    def _poll_events(self) -> None:
        while True:
            try:
                event_type, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if event_type == "peer":
                self._handle_peer(payload)
            elif event_type == "message":
                self._handle_message(payload)

        self._refresh_peers()
        self.after(500, self._poll_events)

    def _handle_peer(self, peer: object) -> None:
        assert isinstance(peer, Peer)
        self.peers[peer.peer_id] = peer
        if self.active_peer and self.active_peer.peer_id == peer.peer_id:
            self.active_peer = peer
            self._update_header()

    def _handle_message(self, message: object) -> None:
        assert isinstance(message, ChatMessage)
        peer = self.peers.get(
            message.sender_id,
            Peer(message.sender_id, message.sender_name, message.sender_ip, 6000, 0),
        )
        self.peers[peer.peer_id] = peer
        self.db.add_message(peer.peer_id, peer.username, peer.ip, "in", message.body)

        if self.active_peer and self.active_peer.peer_id == peer.peer_id:
            self._append_message(peer.username, message.body, "in")
        else:
            self.bell()

    def _refresh_peers(self) -> None:
        for peer in self.discovery.get_peers():
            self.peers[peer.peer_id] = peer
        self.users_panel.set_peers(list(self.peers.values()))

    def _select_peer(self, peer: Peer) -> None:
        self.active_peer = peer
        self._update_header()
        self._load_history(peer)

    def _update_header(self) -> None:
        if self.active_peer:
            self.header_var.set(
                f"{self.active_peer.username} - {self.active_peer.ip}:{self.active_peer.tcp_port}"
            )

    def _load_history(self, peer: Peer) -> None:
        self.history.configure(state="normal")
        self.history.delete("1.0", tk.END)
        for row in self.db.get_messages(peer.peer_id):
            author = self.username if row["direction"] == "out" else row["peer_name"]
            self._insert_message(author, row["body"], row["direction"], row["created_at"])
        self.history.configure(state="disabled")
        self.history.see(tk.END)

    def _send_current_message(self) -> None:
        if not self.active_peer:
            messagebox.showinfo("Select user", "Select an online user before sending.")
            return

        body = self.message_var.get().strip()
        if not body:
            return

        try:
            send_message(
                self.active_peer.ip,
                self.active_peer.tcp_port,
                self.discovery.peer_id,
                self.username,
                body,
            )
        except OSError as error:
            messagebox.showerror("Send failed", f"Could not send message: {error}")
            return

        self.db.add_message(
            self.active_peer.peer_id,
            self.active_peer.username,
            self.active_peer.ip,
            "out",
            body,
        )
        self.message_var.set("")
        self._append_message(self.username, body, "out")

    def _append_message(self, author: str, body: str, direction: str) -> None:
        self.history.configure(state="normal")
        self._insert_message(author, body, direction)
        self.history.configure(state="disabled")
        self.history.see(tk.END)

    def _insert_message(
        self,
        author: str,
        body: str,
        direction: str,
        created_at: str | None = None,
    ) -> None:
        prefix = f"{created_at} " if created_at else ""
        self.history.insert(tk.END, f"{prefix}{author}: ", ("meta",))
        self.history.insert(tk.END, f"{body}\n", (direction,))

    def _close(self) -> None:
        self.discovery.stop()
        self.server.stop()
        self.destroy()
