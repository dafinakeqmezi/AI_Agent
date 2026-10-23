"""Credentials, password resets, session expiry, and sign-in throttling."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from grader import dashboard_auth as auth


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "professors.json"
        auth.set_password("Professor", "fixture-password-123", self.path)
        self.auth = auth.Auth(self.path)

    def test_passwords_are_hashed_and_file_is_private(self):
        self.assertNotIn("fixture-password", self.path.read_text())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            auth.set_password("other", "short", self.path)
        token = self.auth.login("PROFESSOR", "fixture-password-123")
        self.assertTrue(self.auth.valid(token))
        self.assertFalse(self.auth.valid("invented"))
        self.auth.logout(token)
        self.assertFalse(self.auth.valid(token))

    def test_expiry_and_password_reset_revoke_sessions(self):
        token = self.auth.login("professor", "fixture-password-123")
        with patch.object(auth.time, "monotonic", return_value=self.auth.sessions[token][1] + 1):
            self.assertFalse(self.auth.valid(token))
        token = self.auth.login("professor", "fixture-password-123")
        auth.set_password("professor", "replacement-password-123", self.path)
        self.assertFalse(self.auth.valid(token))
        self.assertIsNone(self.auth.login("professor", "fixture-password-123"))
        self.assertTrue(self.auth.login("professor", "replacement-password-123"))

    def test_failed_attempts_are_limited_across_usernames(self):
        for i in range(5):
            self.assertIsNone(self.auth.login("unknown" + str(i), "wrong"))
        with self.assertRaisesRegex(ValueError, "Too many"):
            self.auth.login("professor", "fixture-password-123")
        with patch.object(auth.time, "monotonic", return_value=auth.time.monotonic() + 61):
            self.assertTrue(self.auth.login("professor", "fixture-password-123"))

    def test_accounts_preserved_on_add(self):
        auth.set_password("second", "second-password-123", self.path)
        self.assertEqual(set(json.loads(self.path.read_text())), {"professor", "second"})
        self.assertTrue(self.auth.login("second", "second-password-123"))

    def test_first_setup_never_overwrites_an_existing_account_file(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            auth.set_password("other", "fixture-password-123", self.path, first=True)
        self.assertEqual(self.path.read_bytes(), before)
        fresh = Path(self.temp.name) / "fresh.json"
        instance = auth.Auth(fresh)
        self.assertTrue(instance.needs_setup())
        with self.assertRaisesRegex(ValueError, "match"):
            instance.create_account("first", "fixture-password-123", "wrong", first=True)
        self.assertFalse(fresh.exists())
        instance.create_account("first", "fixture-password-123", "fixture-password-123", first=True)
        self.assertFalse(instance.needs_setup())
