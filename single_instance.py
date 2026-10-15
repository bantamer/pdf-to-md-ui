"""One window per user: a second launch hands its files to the first.

Dropping a PDF on the exe, "Open with", and the Explorer context menu all
start the program with file names on the command line. Without this every
one of them opened a window of its own - ten selected PDFs, ten windows. Now
the first process listens on a local socket; later ones pass their files to it
and exit, and the window that is already open comes to the front.
"""

from __future__ import annotations

import ctypes
import getpass
import hashlib
import json
import os
import time

from PySide6.QtCore import QDir, QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def default_key() -> str:
    """Per user: on Windows a named pipe is visible to every session."""
    user = getpass.getuser().encode("utf-8", "replace")
    return "pdf-to-md-ui-" + hashlib.sha1(user).hexdigest()[:12]


class SingleInstance(QObject):
    received = Signal(list)  # paths a later launch handed over (maybe none)

    def __init__(self, key: str | None = None, lock_dir: str | None = None):
        super().__init__()
        self.key = key or default_key()
        folder = lock_dir or QDir.tempPath()
        self._lock = QLockFile(os.path.join(folder, self.key + ".lock"))
        self._server: QLocalServer | None = None

    def start(self, paths: list[str], attempts: int = 20) -> bool:
        """True: carry on as the program. False: handed over - exit now.

        Two launches can race (ten files picked in Explorer start ten at
        once). The lock decides which one becomes the program; the rest wait
        for its socket and hand their files over.
        """
        for _ in range(attempts):
            if self.forward(paths):
                return False
            if self._lock.tryLock(0):
                self._listen()
                return True
            time.sleep(0.15)
        return True  # something is wedged; better a second window than none

    def forward(self, paths: list[str]) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.key)
        if not socket.waitForConnected(500):
            return False
        # Windows only lets the process the user is working with take the
        # foreground; this one is, and it passes that right on.
        if os.name == "nt":
            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        socket.write(json.dumps(paths).encode("utf-8") + b"\n")
        socket.waitForBytesWritten(2000)
        # Wait for the program to say it has the files. Hanging up first lets
        # Windows drop a connection that was not accepted yet - files and all.
        acknowledged = socket.waitForReadyRead(5000) and bytes(
            socket.readAll()
        ).startswith(b"ok")
        socket.disconnectFromServer()
        return acknowledged

    def close(self) -> None:
        """Stop listening and release the lock; the program does this on exit.

        Sockets are aborted rather than left to their deleteLater: destroying
        one with a pipe read still pending is an access violation on Windows.
        """
        if self._server is not None:
            for socket in self._server.findChildren(QLocalSocket):
                socket.abort()
            self._server.close()
            self._server = None
        if self._lock.isLocked():
            self._lock.unlock()

    def _listen(self) -> None:
        QLocalServer.removeServer(self.key)  # a stale socket after a crash
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept)
        self._server.listen(self.key)

    def _accept(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            buffer = bytearray()

            def read(socket=socket, buffer=buffer) -> None:
                buffer.extend(bytes(socket.readAll()))
                if b"\n" in buffer:
                    line = bytes(buffer).split(b"\n", 1)[0]
                    buffer.clear()
                    try:
                        paths = json.loads(line.decode("utf-8"))
                    except ValueError:
                        return
                    if isinstance(paths, list):
                        socket.write(b"ok\n")
                        socket.flush()
                        self.received.emit([str(p) for p in paths])

            socket.readyRead.connect(read)
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                read()
