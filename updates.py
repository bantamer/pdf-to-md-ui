"""Is there a newer release on GitHub?

One request to the GitHub API: the latest published release, drafts and
pre-releases left out. It runs on a thread of its own - a slow or missing
connection must never hold the window up - and any failure just means "no
answer": the program works the same offline.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

from version import __version__

LATEST_URL = "https://api.github.com/repos/k1llrouz/pdf-to-md-ui/releases/latest"
TIMEOUT = 10  # seconds


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.0' -> (1, 2, 0). Anything after the numbers is ignored."""
    match = re.match(r"v?(\d+(?:\.\d+)*)", text.strip())
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(latest: str, current: str = __version__) -> bool:
    new, old = parse_version(latest), parse_version(current)
    if not new or not old:
        return False
    width = max(len(new), len(old))
    return new + (0,) * (width - len(new)) > old + (0,) * (width - len(old))


def fetch_latest() -> dict | None:
    """{"version": "1.2.0", "url": <release page>} or None if unreachable."""
    request = urllib.request.Request(
        LATEST_URL,
        headers={
            "Accept": "application/vnd.github+json",
            # GitHub turns away requests without one.
            "User-Agent": f"pdf-to-md-ui/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            release = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    tag, url = release.get("tag_name"), release.get("html_url")
    if not isinstance(tag, str) or not isinstance(url, str):
        return None
    return {"version": tag.lstrip("v"), "url": url}


class UpdateCheck(QObject):
    """Asks in the background; `finished` carries fetch_latest()'s answer."""

    finished = Signal(object)

    def start(self) -> None:
        # The signal crosses back to the window's thread on its own: Qt queues
        # it for the receiver. The thread is a daemon, so a hung request never
        # keeps the program from exiting.
        threading.Thread(target=lambda: self.finished.emit(fetch_latest()), daemon=True).start()
