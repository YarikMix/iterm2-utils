"""Bounded, shell-free process execution; never log payloads."""
import subprocess


class Runner:
    def run(self, argv: list[str], *, timeout: float, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(argv, input=stdin, capture_output=True, text=True,
                              timeout=timeout, check=False)
