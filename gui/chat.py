"""Main chat window UI."""

from __future__ import annotations

import queue
import tkinter as tk
import time
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from database import ChatDatabase
from discovery import DiscoveryService, Peer
from gui.notifications import MessageNotifier
from gui.users import UsersPanel
from server import (
    ChatMessage,
    FileTransfer,
    MessageServer,
    TypingEvent,
    send_file,
    send_message,
    send_typing,
)


GROUP_CHAT_ID = "__group__"
GROUP_CHAT_NAME = "Group Chat"
RECEIVED_FILES_DIR = Path("received_files")
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


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
        self.is_group_chat = False
        self.dark_mode = tk.BooleanVar(value=False)
        self.typing_var = tk.StringVar(value="")
        self._typing_peers: dict[str, float] = {}
        self._last_typing_sent = 0.0
        self.notifier = MessageNotifier(self, self._open_peer_from_notification)

        self.server = MessageServer(self._queue_message)
        tcp_port = self.server.start()
        self.discovery = DiscoveryService(username, tcp_port, self._queue_peer)
        self.discovery.start()

        self._build_layout()
        self._apply_theme()
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

        header = ttk.Frame(chat_frame)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        self.header_var = tk.StringVar(value="Select a chat")
        ttk.Label(header, textvariable=self.header_var, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Checkbutton(
            header,
            text="Dark mode",
            variable=self.dark_mode,
            command=self._apply_theme,
        ).grid(row=0, column=1, sticky="e")

        self.history = tk.Text(chat_frame, wrap="word", state="disabled", height=18)
        self.history.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        self.history.tag_configure("in", foreground="#1f4e79")
        self.history.tag_configure("out", foreground="#0b6b35")
        self.history.tag_configure("meta", foreground="#777777")

        ttk.Label(chat_frame, textvariable=self.typing_var).grid(row=2, column=0, sticky="w")

        composer = ttk.Frame(chat_frame)
        composer.grid(row=3, column=0, sticky="ew")
        composer.columnconfigure(0, weight=1)

        self.message_var = tk.StringVar()
        entry = ttk.Entry(composer, textvariable=self.message_var)
        self.message_entry = entry
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        entry.bind("<Return>", lambda _event: self._send_current_message())
        entry.bind("<KeyRelease>", self._handle_typing)
        ttk.Button(composer, text="Attach", command=self._send_current_file).grid(
            row=0, column=1, padx=(0, 8)
        )
        ttk.Button(composer, text="Send", command=self._send_current_message).grid(
            row=0, column=2
        )

    def _queue_peer(self, peer: Peer) -> None:
        self.event_queue.put(("peer", peer))

    def _queue_message(self, event: ChatMessage | TypingEvent | FileTransfer) -> None:
        if isinstance(event, ChatMessage):
            self.event_queue.put(("message", event))
        elif isinstance(event, TypingEvent):
            self.event_queue.put(("typing", event))
        elif isinstance(event, FileTransfer):
            self.event_queue.put(("file", event))

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
            elif event_type == "typing":
                self._handle_typing_event(payload)
            elif event_type == "file":
                self._handle_file_transfer(payload)

        self._refresh_peers()
        self._refresh_typing_indicator()
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
        conversation_id = GROUP_CHAT_ID if message.is_group else peer.peer_id
        conversation_name = peer.username
        conversation_ip = "broadcast" if message.is_group else peer.ip
        self.db.add_message(
            conversation_id,
            conversation_name,
            conversation_ip,
            "in",
            message.body,
        )

        if self._is_viewing_conversation(peer.peer_id, message.is_group):
            self._append_message(peer.username, message.body, "in")
        else:
            self.bell()
        notification_id = GROUP_CHAT_ID if message.is_group else peer.peer_id
        self.notifier.show(notification_id, peer.username, message.body)

    def _handle_typing_event(self, event: object) -> None:
        assert isinstance(event, TypingEvent)
        if event.is_typing:
            self._typing_peers[event.sender_id] = time.time()
        else:
            self._typing_peers.pop(event.sender_id, None)

    def _handle_file_transfer(self, transfer: object) -> None:
        assert isinstance(transfer, FileTransfer)
        peer = self.peers.get(
            transfer.sender_id,
            Peer(transfer.sender_id, transfer.sender_name, transfer.sender_ip, 6000, 0),
        )
        self.peers[peer.peer_id] = peer
        try:
            saved_path = self._save_received_file(transfer.filename, transfer.data)
        except OSError as error:
            messagebox.showerror("File error", f"Could not save received file: {error}")
            return
        body = f"Received file: {saved_path}"

        conversation_id = GROUP_CHAT_ID if transfer.is_group else peer.peer_id
        conversation_name = peer.username
        conversation_ip = "broadcast" if transfer.is_group else peer.ip
        self.db.add_message(
            conversation_id,
            conversation_name,
            conversation_ip,
            "in",
            body,
        )

        if self._is_viewing_conversation(peer.peer_id, transfer.is_group):
            self._append_message(peer.username, body, "in")
        else:
            self.bell()
        notification_id = GROUP_CHAT_ID if transfer.is_group else peer.peer_id
        self.notifier.show(notification_id, peer.username, body)

    def _refresh_peers(self) -> None:
        for peer in self.discovery.get_peers():
            self.peers[peer.peer_id] = peer
        self.users_panel.set_peers(list(self.peers.values()))
        if self.is_group_chat:
            self._update_header()

    def _select_peer(self, peer: Peer | None) -> None:
        self.is_group_chat = peer is None
        self.active_peer = peer
        self.notifier.dismiss()
        self._update_header()
        self._load_history()

    def _open_peer_from_notification(self, peer_id: str) -> None:
        if peer_id == GROUP_CHAT_ID:
            self._select_peer(None)
            return
        peer = self.peers.get(peer_id)
        if peer:
            self._select_peer(peer)

    def _update_header(self) -> None:
        if self.is_group_chat:
            self.header_var.set(f"{GROUP_CHAT_NAME} - {len(self.peers)} online")
        elif self.active_peer:
            self.header_var.set(
                f"{self.active_peer.username} - {self.active_peer.ip}:{self.active_peer.tcp_port}"
            )
        else:
            self.header_var.set("Select a chat")

    def _load_history(self) -> None:
        self.history.configure(state="normal")
        self.history.delete("1.0", tk.END)
        if not self.is_group_chat and not self.active_peer:
            self.history.configure(state="disabled")
            return
        peer_id = GROUP_CHAT_ID if self.is_group_chat else self.active_peer.peer_id
        for row in self.db.get_messages(peer_id):
            author = self.username if row["direction"] == "out" else row["peer_name"]
            self._insert_message(author, row["body"], row["direction"], row["created_at"])
        self.history.configure(state="disabled")
        self.history.see(tk.END)

    def _send_current_message(self) -> None:
        targets = self._message_targets()
        if not targets:
            messagebox.showinfo("Select chat", "Select a user or group chat before sending.")
            return

        body = self.message_var.get().strip()
        if not body:
            return

        failed: list[str] = []
        is_group = self.is_group_chat
        for peer in targets:
            try:
                send_message(
                    peer.ip,
                    peer.tcp_port,
                    self.discovery.peer_id,
                    self.username,
                    body,
                    is_group=is_group,
                )
            except OSError:
                failed.append(peer.username)

        if failed and len(failed) == len(targets):
            messagebox.showerror("Send failed", "Could not send the message to any recipient.")
            return
        if failed:
            messagebox.showwarning("Partially sent", f"Could not reach: {', '.join(failed)}")

        conversation_id = GROUP_CHAT_ID if is_group else targets[0].peer_id
        conversation_name = GROUP_CHAT_NAME if is_group else targets[0].username
        conversation_ip = "broadcast" if is_group else targets[0].ip
        self.db.add_message(conversation_id, conversation_name, conversation_ip, "out", body)
        self.message_var.set("")
        self._send_typing_state(False)
        self._append_message(self.username, body, "out")

    def _send_current_file(self) -> None:
        targets = self._message_targets()
        if not targets:
            messagebox.showinfo("Select chat", "Select a user or group chat before sending a file.")
            return

        selected = filedialog.askopenfilename(title="Send file")
        if not selected:
            return

        path = Path(selected)
        try:
            data = path.read_bytes()
        except OSError as error:
            messagebox.showerror("File error", f"Could not read file: {error}")
            return

        if len(data) > MAX_FILE_SIZE_BYTES:
            messagebox.showerror("File too large", "Send files up to 10 MB.")
            return

        failed: list[str] = []
        is_group = self.is_group_chat
        for peer in targets:
            try:
                send_file(
                    peer.ip,
                    peer.tcp_port,
                    self.discovery.peer_id,
                    self.username,
                    path.name,
                    data,
                    is_group=is_group,
                )
            except OSError:
                failed.append(peer.username)

        if failed and len(failed) == len(targets):
            messagebox.showerror("Send failed", "Could not send the file to any recipient.")
            return
        if failed:
            messagebox.showwarning("Partially sent", f"Could not reach: {', '.join(failed)}")

        body = f"Sent file: {path.name}"
        conversation_id = GROUP_CHAT_ID if is_group else targets[0].peer_id
        conversation_name = GROUP_CHAT_NAME if is_group else targets[0].username
        conversation_ip = "broadcast" if is_group else targets[0].ip
        self.db.add_message(conversation_id, conversation_name, conversation_ip, "out", body)
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

    def _message_targets(self) -> list[Peer]:
        if self.is_group_chat:
            return self.discovery.get_peers()
        if self.active_peer:
            return [self.active_peer]
        return []

    def _handle_typing(self, _event: tk.Event) -> None:
        if self.message_var.get().strip():
            self._send_typing_state(True)
        else:
            self._send_typing_state(False)

    def _send_typing_state(self, is_typing: bool) -> None:
        now = time.time()
        if is_typing and now - self._last_typing_sent < 2:
            return
        self._last_typing_sent = now
        for peer in self._message_targets():
            try:
                send_typing(
                    peer.ip,
                    peer.tcp_port,
                    self.discovery.peer_id,
                    self.username,
                    is_typing,
                )
            except OSError:
                continue

    def _refresh_typing_indicator(self) -> None:
        now = time.time()
        active_names = [
            self.peers[peer_id].username
            for peer_id, last_seen in list(self._typing_peers.items())
            if now - last_seen <= 4 and peer_id in self.peers
        ]
        for peer_id, last_seen in list(self._typing_peers.items()):
            if now - last_seen > 4:
                self._typing_peers.pop(peer_id, None)

        if self.is_group_chat:
            visible_names = active_names
        elif self.active_peer and self.active_peer.peer_id in self._typing_peers:
            visible_names = [self.active_peer.username]
        else:
            visible_names = []

        if not visible_names:
            self.typing_var.set("")
        elif len(visible_names) == 1:
            self.typing_var.set(f"{visible_names[0]} is typing...")
        else:
            self.typing_var.set(f"{', '.join(visible_names[:3])} are typing...")

    def _is_viewing_conversation(self, peer_id: str, is_group: bool) -> bool:
        if is_group:
            return self.is_group_chat
        return bool(self.active_peer and self.active_peer.peer_id == peer_id)

    def _save_received_file(self, filename: str, data: bytes) -> Path:
        RECEIVED_FILES_DIR.mkdir(exist_ok=True)
        safe_name = Path(filename).name or "received_file"
        destination = RECEIVED_FILES_DIR / safe_name
        if not destination.exists():
            destination.write_bytes(data)
            return destination

        stem = destination.stem
        suffix = destination.suffix
        for index in range(1, 1000):
            candidate = RECEIVED_FILES_DIR / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                candidate.write_bytes(data)
                return candidate
        raise OSError("Could not choose a received file name.")

    def _apply_theme(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        dark = self.dark_mode.get()
        if dark:
            background = "#1f2329"
            surface = "#2b3038"
            text = "#f0f3f6"
            muted = "#aab4c0"
            selected = "#3d6fb6"
            in_text = "#8ab4f8"
            out_text = "#8fd19e"
        else:
            background = "#f3f5f7"
            surface = "#ffffff"
            text = "#202124"
            muted = "#777777"
            selected = "#d6e8ff"
            in_text = "#1f4e79"
            out_text = "#0b6b35"

        self.configure(background=background)
        style.configure(".", background=background, foreground=text)
        style.configure("TFrame", background=background)
        style.configure("TLabel", background=background, foreground=text)
        style.configure("TButton", padding=(10, 4))
        style.configure("TCheckbutton", background=background, foreground=text)

        self.users_panel.configure(style="TFrame")
        self.users_panel.listbox.configure(
            background=surface,
            foreground=text,
            selectbackground=selected,
            selectforeground=text,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=selected,
        )
        self.history.configure(
            background=surface,
            foreground=text,
            insertbackground=text,
            highlightthickness=1,
            highlightbackground=selected,
        )
        self.history.tag_configure("in", foreground=in_text)
        self.history.tag_configure("out", foreground=out_text)
        self.history.tag_configure("meta", foreground=muted)

    def _close(self) -> None:
        self._send_typing_state(False)
        self.discovery.stop()
        self.server.stop()
        self.destroy()
