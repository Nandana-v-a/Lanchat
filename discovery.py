"""UDP broadcast discovery for finding peers on the local network."""

from __future__ import annotations

import socket
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable


DISCOVERY_PORT = 5000
DISCOVERY_INTERVAL_SECONDS = 5
PEER_STALE_SECONDS = 20
PROTOCOL = "LANCHAT_V1"


@dataclass(frozen=True)
class Peer:
    peer_id: str
    username: str
    ip: str
    tcp_port: int
    last_seen: float


PeerCallback = Callable[[Peer], None]


class DiscoveryService:
    """Broadcasts this client and listens for other LAN chat clients."""

    def __init__(
        self,
        username: str,
        tcp_port: int,
        on_peer: PeerCallback | None = None,
        discovery_port: int = DISCOVERY_PORT,
    ) -> None:
        self.username = username
        self.tcp_port = tcp_port
        self.discovery_port = discovery_port
        self.peer_id = str(uuid.uuid4())
        self.on_peer = on_peer
        self._stop_event = threading.Event()
        self._peers: dict[str, Peer] = {}
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self._threads = [
            threading.Thread(target=self._listen, name="discovery-listen", daemon=True),
            threading.Thread(target=self._announce_loop, name="discovery-announce", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def get_peers(self) -> list[Peer]:
        now = time.time()
        with self._lock:
            return [
                peer
                for peer in self._peers.values()
                if now - peer.last_seen <= PEER_STALE_SECONDS
            ]

    def announce_now(self) -> None:
        self._broadcast_hello()

    def _announce_loop(self) -> None:
        while not self._stop_event.is_set():
            self._broadcast_hello()
            self._stop_event.wait(DISCOVERY_INTERVAL_SECONDS)

    def _broadcast_hello(self) -> None:
        message = f"{PROTOCOL}|HELLO|{self.peer_id}|{self.username}|{self.tcp_port}"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(
                message.encode("utf-8"),
                ("255.255.255.255", self.discovery_port),
            )

    def _listen(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", self.discovery_port))
            sock.settimeout(1)

            while not self._stop_event.is_set():
                try:
                    data, address = sock.recvfrom(2048)
                except socket.timeout:
                    continue

                peer = self._parse_hello(data, address[0])
                if peer is None or peer.peer_id == self.peer_id:
                    continue

                with self._lock:
                    self._peers[peer.peer_id] = peer
                if self.on_peer:
                    self.on_peer(peer)

    def _parse_hello(self, data: bytes, ip: str) -> Peer | None:
        try:
            protocol, event, peer_id, username, tcp_port = data.decode("utf-8").split("|", 4)
            if protocol != PROTOCOL or event != "HELLO":
                return None
            return Peer(peer_id, username, ip, int(tcp_port), time.time())
        except (UnicodeDecodeError, ValueError):
            return None
