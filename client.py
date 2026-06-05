"""Client entry point for the LAN chat application."""

from __future__ import annotations

from gui.chat import ChatWindow
from gui.login import ask_username


def main() -> None:
    username = ask_username()
    if not username:
        return

    app = ChatWindow(username)
    app.mainloop()


if __name__ == "__main__":
    main()
