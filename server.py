"""TCP server responsibilities for receiving chat messages and events."""

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
    is_group: bool = False


@dataclass(frozen=True)
class TypingEvent:
    sender_id: str
    sender_name: str
    sender_ip: str
    is_typing: bool


@dataclass(frozen=True)
class FileTransfer:
    sender_id: str
    sender_name: str
    sender_ip: str
    filename: str
    data: bytes
    is_group: bool = False


ServerEvent = ChatMessage | TypingEvent | FileTransfer
MessageCallback = Callable[[ServerEvent], None]


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
                raw = self._recv_all(client)
                payload = json.loads(raw.decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return

        sender_id = str(payload.get("sender_id", ""))
        sender_name = str(payload.get("sender_name", "Unknown"))
        if not sender_id:
            return

        event_type = payload.get("type")
        if event_type == "message":
            body = str(payload.get("body", "")).strip()
            if body:
                self.on_message(
                    ChatMessage(
                        sender_id,
                        sender_name,
                        sender_ip,
                        body,
                        bool(payload.get("is_group", False)),
                    )
                )
        elif event_type == "typing":
            self.on_message(
                TypingEvent(
                    sender_id,
                    sender_name,
                    sender_ip,
                    bool(payload.get("is_typing", False)),
                )
            )
        elif event_type == "file":
            filename = str(payload.get("filename", "")).strip()
            data_text = str(payload.get("data", ""))
            if not filename or not data_text:
                return
            try:
                import base64

                data = base64.b64decode(data_text.encode("ascii"), validate=True)
            except (ValueError, UnicodeEncodeError):
                return
            self.on_message(
                FileTransfer(
                    sender_id,
                    sender_name,
                    sender_ip,
                    filename,
                    data,
                    bool(payload.get("is_group", False)),
                )
            )

    @staticmethod
    def _recv_all(client: socket.socket) -> bytes:
        chunks: list[bytes] = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)


def send_message(
    host: str,
    port: int,
    sender_id: str,
    sender_name: str,
    body: str,
    is_group: bool = False,
    timeout: float = 5,
) -> None:
    _send_payload(host, port, {
        "type": "message",
        "sender_id": sender_id,
        "sender_name": sender_name,
        "body": body,
        "is_group": is_group,
    }, timeout)


def send_typing(
    host: str,
    port: int,
    sender_id: str,
    sender_name: str,
    is_typing: bool,
    timeout: float = 2,
) -> None:
    _send_payload(host, port, {
        "type": "typing",
        "sender_id": sender_id,
        "sender_name": sender_name,
        "is_typing": is_typing,
    }, timeout)


def send_file(
    host: str,
    port: int,
    sender_id: str,
    sender_name: str,
    filename: str,
    data: bytes,
    is_group: bool = False,
    timeout: float = 15,
) -> None:
    import base64

    _send_payload(host, port, {
        "type": "file",
        "sender_id": sender_id,
        "sender_name": sender_name,
        "filename": filename,
        "data": base64.b64encode(data).decode("ascii"),
        "is_group": is_group,
    }, timeout)


def _send_payload(host: str, port: int, payload: dict[str, object], timeout: float) -> None:
    encoded = json.dumps(payload).encode("utf-8")
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(encoded)
