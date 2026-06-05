"""TCP server responsibilities for receiving chat messages."""

from __future__ import annotations

import json
import socket
import threading
from dataclasses import dataclass
from typing import Callable


DEFAULT_TCP_PORT = 6000
PORT_SCAN_LIMIT = 25


@dataclass(frozen=True)
class ChatMessage:
    sender_id: str
    sender_name: str
    sender_ip: str
    body: str


MessageCallback = Callable[[ChatMessage], None]


class MessageServer:
    """Background TCP server that receives direct chat messages."""

    def __init__(
        self,
        on_message: MessageCallback,
        host: str = "0.0.0.0",
        preferred_port: int = DEFAULT_TCP_PORT,
    ) -> None:
        self.on_message = on_message
        self.host = host
        self.preferred_port = preferred_port
        self.port = preferred_port
        self._stop_event = threading.Event()
        self._server_socket: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        self._server_socket = self._bind_available_socket()
        self.port = self._server_socket.getsockname()[1]
        self._server_socket.listen()
        self._thread = threading.Thread(target=self._serve, name="message-server", daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_socket:
            self._server_socket.close()

    def _bind_available_socket(self) -> socket.socket:
        for port in range(self.preferred_port, self.preferred_port + PORT_SCAN_LIMIT):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((self.host, port))
                return sock
            except OSError:
                sock.close()
        raise OSError(f"No free TCP port found from {self.preferred_port}")

    def _serve(self) -> None:
        assert self._server_socket is not None
        self._server_socket.settimeout(1)
        while not self._stop_event.is_set():
            try:
                client, address = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            threading.Thread(
                target=self._handle_client,
                args=(client, address[0]),
                name="message-client",
                daemon=True,
            ).start()

    def _handle_client(self, client: socket.socket, sender_ip: str) -> None:
        with client:
            try:
                raw = client.recv(65536)
                payload = json.loads(raw.decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return

        if payload.get("type") != "message":
            return

        sender_id = str(payload.get("sender_id", ""))
        sender_name = str(payload.get("sender_name", "Unknown"))
        body = str(payload.get("body", "")).strip()
        if not sender_id or not body:
            return

        self.on_message(ChatMessage(sender_id, sender_name, sender_ip, body))


def send_message(
    host: str,
    port: int,
    sender_id: str,
    sender_name: str,
    body: str,
    timeout: float = 5,
) -> None:
    payload = {
        "type": "message",
        "sender_id": sender_id,
        "sender_name": sender_name,
        "body": body,
    }
    encoded = json.dumps(payload).encode("utf-8")
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(encoded)
