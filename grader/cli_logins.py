"""Per-professor subscription sign-ins for the Claude Code and Codex CLIs (dashboard only).

Every professor workspace gets its own CLI configuration directories (CLAUDE_CONFIG_DIR, CODEX_HOME),
so reviews started by a professor run on that professor's own subscription, never on the server
operator's or another professor's. A sign-in is the official CLI's own browser flow: the link and
one-time code it prints are kept in memory and shown only to that professor. Credentials stay inside
the CLI directories; this module never reads them.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from . import subscriptions
from .runner import RunnerError

TOOLS = {"claude": "claude-code", "codex": "chatgpt"}  # sign-in tool -> provider name
LOGIN_SECONDS = 15 * 60
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
URL = re.compile(r"https://[^\s\"'<>]+")
DEVICE_CODE = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4,6}\b")
PASTED_CODE = re.compile(r"[A-Za-z0-9_\-#.~]{8,512}")
LOGIN_HOSTS = ("claude.com", "claude.ai", "anthropic.com", "openai.com", "chatgpt.com")


def environment(root) -> dict:
    """The CLI homes inside a professor's workspace (created owner-only)."""
    homes = {"CLAUDE_CONFIG_DIR": Path(root) / "cli" / "claude", "CODEX_HOME": Path(root) / "cli" / "codex"}
    for path in homes.values():
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return {key: str(path) for key, path in homes.items()}


def login_url(text: str, tool: str) -> str | None:
    """The sign-in link printed by the CLI, only if it points to the vendor's own site."""
    for url in URL.findall(text):
        host = (urlsplit(url).hostname or "").lower()
        if any(host == h or host.endswith("." + h) for h in LOGIN_HOSTS):
            if tool == "codex" or "oauth" in url:
                return url
    return None


class Logins:
    def __init__(self, env: dict):
        self.env = env
        self.lock = threading.RLock()
        self.active: dict[str, dict] = {}

    @staticmethod
    def check_tool(tool):
        if tool not in TOOLS:
            raise ValueError("Choose claude or codex")

    @staticmethod
    def binary(tool):
        path = shutil.which(tool)
        if not path:
            raise ValueError(f"The {tool} CLI is not installed on this server. See docs/subscriptions.md.")
        return path

    def child_env(self):
        return subscriptions.child_environment(self.env)

    def command(self, tool):
        if tool == "claude":
            return [self.binary(tool), "auth", "login", "--claudeai"]
        return [self.binary(tool), "login", "--device-auth"]

    def start(self, tool, wait=15.0):
        self.check_tool(tool)
        with self.lock:
            self.expire()
            entry = self.active.get(tool)
            if not (entry and entry["process"].poll() is None):
                process = subprocess.Popen(self.command(tool), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, env=self.child_env(),
                                           cwd=self.env.get("CODEX_HOME") or None,
                                           start_new_session=os.name != "nt")
                entry = {"process": process, "output": "", "started": time.monotonic()}
                self.active[tool] = entry
                threading.Thread(target=self.read, args=(entry,), daemon=True).start()
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and entry["process"].poll() is None and not self.view(tool)["url"]:
            time.sleep(0.2)
        return self.view(tool)

    @staticmethod
    def read(entry):
        process = entry["process"]
        try:
            while True:
                chunk = process.stdout.read1(4096)
                if not chunk:
                    break
                text = ANSI.sub("", chunk.decode("utf-8", "replace"))
                entry["output"] = (entry["output"] + text)[-16000:]
        except (OSError, ValueError):
            pass  # the pipe was closed by cancel()
        finally:
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass

    def submit_code(self, tool, code, wait=30.0):
        self.check_tool(tool)
        code = (code or "").strip()
        if tool != "claude":
            raise ValueError("Only the Claude sign-in asks for a pasted code")
        if not PASTED_CODE.fullmatch(code):
            raise ValueError("Paste the code exactly as shown after signing in")
        with self.lock:
            entry = self.active.get(tool)
            if not entry or entry["process"].poll() is not None:
                raise ValueError("Start the Claude sign-in again; the previous one has ended")
            try:
                entry["process"].stdin.write(code.encode() + b"\n")
                entry["process"].stdin.flush()
            except (OSError, ValueError):
                raise ValueError("Start the Claude sign-in again; the previous one has ended") from None
        try:
            entry["process"].wait(timeout=wait)
        except subprocess.TimeoutExpired:
            pass
        return self.view(tool)

    def view(self, tool) -> dict:
        entry = self.active.get(tool)
        if not entry:
            return {"state": "idle", "url": None, "code": None, "message": ""}
        output, code = entry["output"], entry["process"].poll()
        state = "waiting" if code is None else "done" if code == 0 else "failed"
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        device = DEVICE_CODE.search(output) if tool == "codex" else None
        return {"state": state, "url": login_url(output, tool) if state == "waiting" else None,
                "code": device.group(0) if device and state == "waiting" else None,
                "message": (lines[-1][:300] if lines else "") if state == "failed" else ""}

    def cancel(self, tool):
        self.check_tool(tool)
        with self.lock:
            entry = self.active.pop(tool, None)
        if entry:
            process = entry["process"]
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
        return {"state": "idle", "url": None, "code": None, "message": ""}

    def expire(self):
        for tool, entry in list(self.active.items()):
            if entry["process"].poll() is None and time.monotonic() - entry["started"] > LOGIN_SECONDS:
                self.cancel(tool)

    def connected(self, tool):
        try:
            subscriptions.SubscriptionCLI(TOOLS[tool], timeout=30, env=self.env)
            return True, "Connected with your own subscription."
        except RunnerError as error:
            return False, str(error)

    def status(self, check=True) -> dict:
        self.expire()
        result = {}
        for tool in TOOLS:
            connected, message = self.connected(tool) if check else (None, "")
            result[tool] = {"connected": connected, "message": message, "login": self.view(tool)}
        return result

    def logout(self, tool):
        self.check_tool(tool)
        self.cancel(tool)
        command = [self.binary(tool), "auth", "logout"] if tool == "claude" else [self.binary(tool), "logout"]
        subprocess.run(command, env=self.child_env(), capture_output=True, timeout=30, check=False)
        return self.status()[tool]

    def close(self):
        for tool in list(self.active):
            self.cancel(tool)
