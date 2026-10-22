"""Bounded subprocess access to iTerm2's built-in it2 utility."""
import json
import os
import re
import signal
import subprocess
import time
from typing import Optional

from .models import Pane
from .registry import normalize_terminal

IT2_DEFAULT = "/Applications/iTerm.app/Contents/Resources/utilities/it2"
ITERM_PROCESS = "/Applications/iTerm.app/Contents/MacOS/iTerm2"


class UnknownTabOutcome(Exception):
    """The create request may have reached iTerm; inspection is required."""


class ITerm:
    def __init__(self, executable: str = IT2_DEFAULT, ps: str = "ps", timeout: float = 3.0):
        self.executable = os.environ.get("CODEX_RESTORE_IT2", executable) if executable == IT2_DEFAULT else executable
        self.ps = os.environ.get("CODEX_RESTORE_PS", ps) if ps == "ps" else ps
        self.process = os.environ.get("CODEX_RESTORE_ITERM_PROCESS", ITERM_PROCESS)
        self.timeout = timeout
        self.deadline: Optional[float] = None

    def _run(self, arguments: list[str], c_locale: bool = False) -> str:
        budget = self.timeout
        if self.deadline is not None:
            budget = min(budget, self.deadline - time.monotonic())
        if budget <= 0:
            raise TimeoutError("iTerm2 deadline exceeded")
        environment = dict(os.environ)
        if c_locale:
            environment["LC_ALL"] = "C"
        process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=environment, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=budget)
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, arguments, stdout, stderr)
            return stdout
        except BaseException:
            # Kill the process group too: a wrapper can have a sleeping child.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise

    def _processes(self) -> dict[int, tuple[str, str]]:
        result = {}
        for line in self._run([self.ps, "-Ao", "pid=,lstart=,comm="], c_locale=True).splitlines():
            fields = line.split(None, 6)
            if len(fields) != 7 or not fields[0].isdigit():
                raise ValueError("invalid process inventory")
            pid = int(fields[0])
            if pid in result:
                raise ValueError("duplicate process identity")
            result[pid] = (" ".join(fields[1:6]), fields[6])
        return result

    def launch_id(self) -> str:
        override = os.environ.get("CODEX_RESTORE_ITERM_LAUNCH")
        if override:
            return override
        matches = [(pid, started) for pid, (started, command) in self._processes().items()
                   if command == self.process]
        if len(matches) != 1:
            raise ValueError("cannot identify the iTerm2 launch")
        return "%s:%s" % matches[0]

    def identity(self, pid: int) -> Optional[str]:
        value = self._processes().get(pid)
        return value[0] if value else None

    def _list(self, kind: str) -> list[dict]:
        value = json.loads(self._run([self.executable, kind, "list", "--json"]))
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError("invalid iTerm2 inventory")
        return value

    @staticmethod
    def _id(value: object) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("missing iTerm2 identity")
        return value

    def panes(self) -> list[Pane]:
        sessions, tabs, windows = self._list("session"), self._list("tab"), self._list("window")
        window_numbers = {}
        for number, window in enumerate(windows, 1):
            wid = self._id(window.get("id"))
            if wid in window_numbers:
                raise ValueError("duplicate window")
            window_numbers[wid] = number
        positions = {}
        tab_positions = set()
        for tab in tabs:
            tid, wid = self._id(tab.get("id")), self._id(tab.get("window_id"))
            index = tab.get("index")
            if (tid in positions or wid not in window_numbers or type(index) is not int
                    or index < 0 or (wid, index) in tab_positions):
                raise ValueError("incomplete tab inventory")
            positions[tid] = (wid, index + 1)
            tab_positions.add((wid, index))
        for wid in window_numbers:
            indexes = sorted(index for window, index in tab_positions if window == wid)
            if not indexes or indexes != list(range(len(indexes))):
                raise ValueError("incomplete window inventory")
        result = []
        seen = set()
        used_tabs = set()
        for session in sessions:
            terminal = normalize_terminal(self._id(session.get("id")))
            tid, wid = self._id(session.get("tab_id")), self._id(session.get("window_id"))
            if terminal in seen or tid not in positions or positions[tid][0] != wid:
                raise ValueError("incomplete session inventory")
            seen.add(terminal)
            used_tabs.add(tid)
            result.append(Pane(terminal, tid, wid, window_numbers[wid], positions[tid][1]))
        if used_tabs != set(positions):
            raise ValueError("missing tab sessions")
        return result

    def new_tab(self, window_id: str) -> str:
        window_id = self._id(window_id)
        try:
            return self._created_tab(window_id)
        except Exception as exc:
            raise UnknownTabOutcome("tab creation outcome is unknown") from exc

    def _created_tab(self, window_id):
        output = self._run([self.executable, "tab", "new", "--window", window_id])
        match = re.search(r"^Created new tab: (\S+)\s*$", output, re.MULTILINE)
        if not match:
            raise ValueError("iTerm2 did not identify the new tab")
        key = match.group(1)
        for attempt in range(5):
            if attempt:
                time.sleep(0.2)
            matches = [item for item in self._list("session")
                       if (key == item.get("tab_id") or key.lower() == str(item.get("id", "")).lower())
                       and item.get("window_id") == window_id]
            if len(matches) == 1:
                return normalize_terminal(self._id(matches[0].get("id")))
        raise ValueError("cannot find the new iTerm2 session")

    def run(self, terminal: str, command: str) -> None:
        self._run([self.executable, "session", "run", command, "-s", normalize_terminal(terminal).upper()])

    def focus(self, terminal: str) -> None:
        self._run([self.executable, "session", "focus", normalize_terminal(terminal).upper()])
