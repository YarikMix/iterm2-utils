"""Disk fixtures; no real Codex or user configuration is touched."""
import json
from pathlib import Path


def write_session(home: Path, sid: str, cwd: Path, source: object = "cli",
                  originator: str = "codex-tui", prompt: str = "проверка") -> Path:
    path = home / "sessions" / "2026" / (sid + ".jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {"type": "session_meta", "payload": {
        "id": sid, "cwd": str(cwd), "source": source, "originator": originator}}
    message = {"type": "response_item", "payload": {
        "type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt}]}}
    path.write_text(json.dumps(header) + "\n" + json.dumps(message) + "\n")
    return path


class TerminalTools:
    """Subprocess-level iTerm/ps doubles, with inspectable invocation records."""
    def __init__(self, root: Path):
        import sys
        self.root = root / "terminal-tools"
        self.root.mkdir()
        self.log = self.root / "calls.jsonl"
        self.pid = self.root / "child.pid"
        self.it2 = self.root / "it2"
        self.ps = self.root / "ps"
        body = '''
import json, os, pathlib, sys, time
root = pathlib.Path(__file__).parent
with (root / "calls.jsonl").open("a") as stream:
    stream.write(json.dumps([pathlib.Path(__file__).name] + sys.argv[1:]) + "\\n")
if pathlib.Path(__file__).name == "ps":
    print((root / "ps.txt").read_text(), end="")
else:
    (root / "child.pid").write_text(str(os.getpid()))
    if (root / "delay").exists():
        time.sleep(float((root / "delay").read_text()))
    command = "-".join(sys.argv[1:3])
    if command in ("session-list", "tab-list", "window-list"):
        print((root / (command + ".json")).read_text())
    elif command == "tab-new":
        print("Created new tab: T-new")
'''
        for path in (self.it2, self.ps):
            path.write_text("#!" + sys.executable + "\n" + body)
            path.chmod(0o755)
        self.set_inventory([], [], [])
        self.set_ps()

    def set_ps(self, launch=True):
        text = "100 Thu Oct 15 10:00:00 2026 /bin/zsh\n"
        if launch:
            text += "200 Thu Oct 15 09:00:00 2026 /Applications/iTerm.app/Contents/MacOS/iTerm2\n"
        (self.root / "ps.txt").write_text(text)

    def set_inventory(self, sessions, tabs, windows):
        for command, value in (("session", sessions), ("tab", tabs), ("window", windows)):
            (self.root / (command + "-list.json")).write_text(json.dumps(value))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
