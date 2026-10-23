"""Local professor credentials and expiring in-memory dashboard sessions."""
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from .common import ROOT

ACCOUNTS = ROOT / "state" / "professors.json"
ITERATIONS = 600_000
SESSION_SECONDS = 8 * 60 * 60


def set_password(username, password, path=None, *, first=False):
    path = Path(path or ACCOUNTS)
    username = username.strip().casefold()
    if not re.fullmatch(r"[a-z0-9_.@-]{1,64}", username):
        raise ValueError("Username must contain 1–64 letters, numbers, or . _ @ -")
    if not 12 <= len(password) <= 1024:
        raise ValueError("Use a password of 12–1024 characters")
    salt = secrets.token_hex(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    accounts = json.loads(path.read_text()) if path.exists() else {}
    accounts[username] = {"salt": salt, "iterations": ITERATIONS, "digest": digest}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + secrets.token_hex(8))
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(accounts, stream)
        if first:
            try:
                os.link(temporary, path)  # Atomic first-account claim; never overwrite an account file.
            except FileExistsError:
                raise ValueError("Professor setup is already complete. Sign in instead.") from None
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def configure(username=None):
    username = username or input("Professor username: ").strip()
    password = getpass.getpass("Password (at least 12 characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise ValueError("Passwords do not match; account was not changed")
    set_password(username, password)
    print("Professor account saved. Existing passwords for this username are replaced.")


class Auth:
    def __init__(self, path=None):
        self.path = Path(path or ACCOUNTS)
        accounts = json.loads(self.path.read_text()) if self.path.exists() else None
        if accounts is not None and (not isinstance(accounts, dict) or not accounts):
            raise ValueError("Create a professor account before starting the dashboard")
        self.sessions = {}
        self.attempts = []
        self.lock = threading.RLock()

    def needs_setup(self):
        return not self.path.exists()

    def create_account(self, username, password, confirmation, *, first=False):
        with self.lock:
            if password != confirmation:
                raise ValueError("Passwords do not match")
            if first and not self.needs_setup():
                raise ValueError("Professor setup is already complete. Sign in instead.")
            if not first:
                accounts = json.loads(self.path.read_text())
                if username.strip().casefold() in accounts:
                    raise ValueError("Username already exists. Choose another username.")
            set_password(username, password, self.path, first=first)

    def login(self, username, password):
        # A loopback-wide limit prevents evasion by cycling usernames or cookies.
        with self.lock:
            now = time.monotonic()
            self.attempts = [t for t in self.attempts if now - t < 60]
            if len(self.attempts) >= 5:
                raise ValueError("Too many sign-in attempts. Try again in one minute.")
            self.attempts.append(now)
            accounts = json.loads(self.path.read_text())
            account = accounts.get(username.strip().casefold())
            salt = bytes.fromhex(account["salt"]) if account else bytes(32)
            iterations = account["iterations"] if account else ITERATIONS
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations).hex()
            if not account or not hmac.compare_digest(digest, account["digest"]):
                return None
            token = secrets.token_urlsafe(32)
            self.sessions = {k: v for k, v in self.sessions.items() if v[1] > now}
            self.sessions[token] = (username.strip().casefold(), now + SESSION_SECONDS, account["digest"])
            return token

    def valid(self, token):
        with self.lock:
            session = self.sessions.get(token)
            if not session:
                return False
            accounts = json.loads(self.path.read_text())
            account = accounts.get(session[0])
            if session[1] <= time.monotonic() or not account or account["digest"] != session[2]:
                self.sessions.pop(token, None)
                return False
            return True

    def identity(self, token):
        with self.lock:
            if not self.valid(token):
                return None
            return self.sessions[token][0]

    def logout(self, token):
        with self.lock:
            self.sessions.pop(token, None)


def prepare():
    return Auth()
