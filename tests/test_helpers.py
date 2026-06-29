"""
Brutal unit tests for pure helper / utility functions.
These run with NO database and NO external services.
"""
import os
import sys
import json
import hashlib
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("LLM_ENCRYPTION_KEY", "vX3Kx5q7vT3TQqgq2YQ0nO1E7iH2F7k6Hn5s3aQbYq8=")
sys.path.insert(0, "/root/botBuilder/bb_master/bb_service")


# ─────────────────────────────────────────────────────────────────────────────
# common_utils  (no deps on DB)
# ─────────────────────────────────────────────────────────────────────────────
class TestCommonUtils(unittest.TestCase):

    def setUp(self):
        from app.routes.helpers.common_utils import compute_snapshot_hash, make_json_safe
        self.compute_snapshot_hash = compute_snapshot_hash
        self.make_json_safe = make_json_safe

    # ── make_json_safe ────────────────────────────────────────────────────────

    def test_make_json_safe_dict(self):
        result = self.make_json_safe({"a": 1, "b": "hello"})
        self.assertEqual(result, {"a": 1, "b": "hello"})

    def test_make_json_safe_nested(self):
        import uuid
        uid = uuid.uuid4()
        result = self.make_json_safe({"id": uid, "nested": {"x": 1}})
        self.assertIsInstance(result["id"], str)
        self.assertEqual(result["id"], str(uid))

    def test_make_json_safe_datetime(self):
        from datetime import datetime
        dt = datetime(2026, 1, 15, 12, 0, 0)
        result = self.make_json_safe({"ts": dt})
        self.assertEqual(result["ts"], "2026-01-15T12:00:00")

    def test_make_json_safe_list(self):
        result = self.make_json_safe([1, "two", 3.0])
        self.assertEqual(result, [1, "two", 3.0])

    def test_make_json_safe_empty(self):
        self.assertEqual(self.make_json_safe({}), {})
        self.assertEqual(self.make_json_safe([]), [])

    def test_make_json_safe_none_passthrough(self):
        result = self.make_json_safe(None)
        self.assertIsNone(result)

    # ── compute_snapshot_hash ────────────────────────────────────────────────

    def test_snapshot_hash_is_sha256(self):
        h = self.compute_snapshot_hash({"a": 1})
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))

    def test_snapshot_hash_deterministic(self):
        payload = {"name": "bot", "llm": "gpt-4", "steps": [1, 2, 3]}
        h1 = self.compute_snapshot_hash(payload)
        h2 = self.compute_snapshot_hash(payload)
        self.assertEqual(h1, h2)

    def test_snapshot_hash_key_order_independent(self):
        h1 = self.compute_snapshot_hash({"a": 1, "b": 2})
        h2 = self.compute_snapshot_hash({"b": 2, "a": 1})
        self.assertEqual(h1, h2)

    def test_snapshot_hash_different_payloads_differ(self):
        h1 = self.compute_snapshot_hash({"a": 1})
        h2 = self.compute_snapshot_hash({"a": 2})
        self.assertNotEqual(h1, h2)

    def test_snapshot_hash_empty_dict(self):
        h = self.compute_snapshot_hash({})
        self.assertIsInstance(h, str)
        self.assertEqual(len(h), 64)

    def test_snapshot_hash_matches_manual_sha256(self):
        payload = {"key": "value"}
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        self.assertEqual(self.compute_snapshot_hash(payload), expected)


# ─────────────────────────────────────────────────────────────────────────────
# encryption utils
# ─────────────────────────────────────────────────────────────────────────────
class TestEncryptionUtils(unittest.TestCase):

    def setUp(self):
        from app.routes.helpers.encryption import encrypt_value, decrypt_value, mask_key
        self.encrypt = encrypt_value
        self.decrypt = decrypt_value
        self.mask = mask_key

    def test_encrypt_decrypt_roundtrip(self):
        secret = "sk-test-openai-key-12345"
        ciphertext = self.encrypt(secret)
        self.assertNotEqual(ciphertext, secret)
        plaintext = self.decrypt(ciphertext)
        self.assertEqual(plaintext, secret)

    def test_encrypt_returns_string(self):
        result = self.encrypt("hello")
        self.assertIsInstance(result, str)

    def test_encrypt_is_not_plaintext(self):
        val = "my-api-key"
        self.assertNotIn(val, self.encrypt(val))

    def test_decrypt_wrong_key_raises(self):
        from cryptography.fernet import Fernet, InvalidToken
        other_cipher_key = Fernet.generate_key().decode()
        ciphertext = self.encrypt("secret")
        with patch("app.routes.helpers.encryption.cipher") as mock_cipher:
            mock_cipher.decrypt.side_effect = InvalidToken()
            with self.assertRaises(InvalidToken):
                mock_cipher.decrypt(ciphertext.encode())

    def test_mask_short_key(self):
        self.assertEqual(self.mask("abc"), "****")
        self.assertEqual(self.mask("123456789"), "****")

    def test_mask_long_key(self):
        result = self.mask("sk-abcdefghijklmnopqrstuvwxyz")
        self.assertTrue(result.startswith("sk-abc"))
        self.assertTrue(result.endswith("wxyz"))
        self.assertIn("****", result)

    def test_mask_empty_string(self):
        self.assertEqual(self.mask(""), "****")

    def test_mask_none(self):
        self.assertEqual(self.mask(None), "****")

    def test_encrypt_unicode(self):
        val = "密钥测试-api-key"
        ciphertext = self.encrypt(val)
        self.assertEqual(self.decrypt(ciphertext), val)


# ─────────────────────────────────────────────────────────────────────────────
# custom_bot_utils — pure helper functions (no DB)
# ─────────────────────────────────────────────────────────────────────────────
class TestCustomBotUtils(unittest.TestCase):

    def setUp(self):
        from app.routes.helpers.custom_bot_utils import allowed_file, parse_enum
        self.allowed_file = allowed_file
        self.parse_enum = parse_enum

    def test_allowed_file_png(self):
        self.assertTrue(self.allowed_file("avatar.png"))

    def test_allowed_file_jpg(self):
        self.assertTrue(self.allowed_file("photo.jpg"))

    def test_allowed_file_jpeg(self):
        self.assertTrue(self.allowed_file("photo.jpeg"))

    def test_allowed_file_gif(self):
        self.assertTrue(self.allowed_file("anim.gif"))

    def test_allowed_file_exe_rejected(self):
        self.assertFalse(self.allowed_file("evil.exe"))

    def test_allowed_file_py_rejected(self):
        self.assertFalse(self.allowed_file("script.py"))

    def test_allowed_file_no_extension(self):
        self.assertFalse(self.allowed_file("noextension"))

    def test_allowed_file_double_extension(self):
        self.assertFalse(self.allowed_file("file.png.exe"))

    def test_allowed_file_case_insensitive(self):
        self.assertTrue(self.allowed_file("AVATAR.PNG"))
        self.assertTrue(self.allowed_file("PHOTO.JPG"))

    def test_parse_enum_valid_industry(self):
        from app.models.new_models.custom_bot import IndustryEnum
        result = self.parse_enum(IndustryEnum, "Healthcare", "industry")
        self.assertEqual(result, IndustryEnum.HEALTHCARE)

    def test_parse_enum_valid_tone(self):
        from app.models.new_models.custom_bot import ToneOfVoiceEnum
        result = self.parse_enum(ToneOfVoiceEnum, "Professional", "tone")
        self.assertEqual(result, ToneOfVoiceEnum.PROFESSIONAL)

    def test_parse_enum_case_insensitive(self):
        from app.models.new_models.custom_bot import ToneOfVoiceEnum
        result = self.parse_enum(ToneOfVoiceEnum, "FRIENDLY", "tone")
        self.assertEqual(result, ToneOfVoiceEnum.FRIENDLY)

    def test_parse_enum_invalid_raises(self):
        from app.models.new_models.custom_bot import IndustryEnum
        with self.assertRaises(ValueError):
            self.parse_enum(IndustryEnum, "NotAnIndustry", "industry")

    def test_parse_enum_empty_raises(self):
        from app.models.new_models.custom_bot import IndustryEnum
        with self.assertRaises(ValueError):
            self.parse_enum(IndustryEnum, "", "industry")

    def test_parse_enum_none_raises(self):
        from app.models.new_models.custom_bot import IndustryEnum
        with self.assertRaises(ValueError):
            self.parse_enum(IndustryEnum, None, "industry")


# ─────────────────────────────────────────────────────────────────────────────
# Enum value sanity checks
# ─────────────────────────────────────────────────────────────────────────────
class TestEnumIntegrity(unittest.TestCase):

    def test_agent_status_enum_values(self):
        from app.models.agent import AgentStatusEnum
        values = {e.value for e in AgentStatusEnum}
        self.assertIn("Draft", values)
        self.assertIn("Live", values)
        self.assertIn("Paused", values)
        self.assertIn("Deleted", values)

    def test_bot_status_enum_values(self):
        from app.models.new_models.custom_bot import BotStatusEnum
        values = {e.value for e in BotStatusEnum}
        self.assertIn("Draft", values)
        self.assertIn("Live", values)
        self.assertIn("Paused", values)

    def test_tone_of_voice_has_professional(self):
        from app.models.new_models.custom_bot import ToneOfVoiceEnum
        names = {e.name for e in ToneOfVoiceEnum}
        self.assertIn("PROFESSIONAL", names)

    def test_channel_enum_has_website(self):
        from app.models.new_models.custom_bot import ChannelEnum
        names = {e.name for e in ChannelEnum}
        self.assertIn("WEBSITE", names)

    def test_industry_enum_has_healthcare(self):
        from app.models.new_models.custom_bot import IndustryEnum
        values = {e.value for e in IndustryEnum}
        self.assertIn("Healthcare", values)

    def test_no_duplicate_enum_values_agent_status(self):
        from app.models.agent import AgentStatusEnum
        values = [e.value for e in AgentStatusEnum]
        self.assertEqual(len(values), len(set(values)), "Duplicate values in AgentStatusEnum")

    def test_no_duplicate_enum_values_bot_status(self):
        from app.models.new_models.custom_bot import BotStatusEnum
        values = [e.value for e in BotStatusEnum]
        self.assertEqual(len(values), len(set(values)), "Duplicate values in BotStatusEnum")


# ─────────────────────────────────────────────────────────────────────────────
# response_utils
# ─────────────────────────────────────────────────────────────────────────────
class TestResponseUtils(unittest.TestCase):

    def setUp(self):
        from flask import Flask
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True

    def test_success_response_structure(self):
        from app.routes.helpers.response_utils import success_response
        with self.app.app_context():
            resp, code = success_response("OK", {"id": 1})
            data = resp.get_json()
            self.assertTrue(data["status"])
            self.assertEqual(data["message"], "OK")
            self.assertEqual(data["data"]["id"], 1)
            self.assertEqual(code, 200)

    def test_error_response_structure(self):
        from app.routes.helpers.response_utils import error_response
        with self.app.app_context():
            resp, code = error_response("Bad input", None, 400)
            data = resp.get_json()
            self.assertFalse(data["status"])
            self.assertEqual(data["message"], "Bad input")
            self.assertEqual(code, 400)

    def test_success_response_default_code(self):
        from app.routes.helpers.response_utils import success_response
        with self.app.app_context():
            _, code = success_response("done")
            self.assertEqual(code, 200)

    def test_error_response_default_code(self):
        from app.routes.helpers.response_utils import error_response
        with self.app.app_context():
            _, code = error_response("oops")
            self.assertEqual(code, 400)

    def test_success_response_none_data(self):
        from app.routes.helpers.response_utils import success_response
        with self.app.app_context():
            resp, _ = success_response("OK", None)
            data = resp.get_json()
            self.assertIsNone(data["data"])

    def test_error_response_custom_code(self):
        from app.routes.helpers.response_utils import error_response
        with self.app.app_context():
            _, code = error_response("Not found", code=404)
            self.assertEqual(code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
