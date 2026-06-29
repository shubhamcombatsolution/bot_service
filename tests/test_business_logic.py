"""
Business logic tests — pure functions from route files.
No DB, no external services needed.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("LLM_ENCRYPTION_KEY", "vX3Kx5q7vT3TQqgq2YQ0nO1E7iH2F7k6Hn5s3aQbYq8=")
sys.path.insert(0, "/root/botBuilder/bb_master/bb_service")


# ─────────────────────────────────────────────────────────────────────────────
# calculation_engine — pure utility functions
# ─────────────────────────────────────────────────────────────────────────────
def _load_calc():
    """Load calc engine module (patches heavy imports)."""
    with patch.dict("sys.modules", {
        "fuzzywuzzy": MagicMock(),
        "fuzzywuzzy.fuzz": MagicMock(),
        "fuzzywuzzy.process": MagicMock(),
        "flask_jwt_extended": MagicMock(),
        "app.models": MagicMock(),
        "app.models.charges_models": MagicMock(),
        "app.models.charges_models.bank_charges": MagicMock(),
        "app.models.charges_models.other_charges": MagicMock(),
        "app.models.charges_models.clearance_charges": MagicMock(),
        "app.database": MagicMock(),
        "app.database.DatabaseOperationPostgreSQL": MagicMock(),
        "sqlalchemy": MagicMock(),
    }):
        import importlib
        import app.routes.calculation_engine_routes as m
        return m


class TestFmtFunction(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = _load_calc()

    def test_fmt_integer(self):
        self.assertEqual(self.m.fmt(5), "5.00")

    def test_fmt_float(self):
        self.assertEqual(self.m.fmt(3.14159), "3.14")

    def test_fmt_zero(self):
        self.assertEqual(self.m.fmt(0), "0.00")

    def test_fmt_none_returns_none(self):
        self.assertIsNone(self.m.fmt(None))

    def test_fmt_large_number(self):
        self.assertEqual(self.m.fmt(1000000.5), "1000000.50")

    def test_fmt_negative(self):
        self.assertEqual(self.m.fmt(-9.999), "-10.00")

    def test_fmt_string_number(self):
        self.assertEqual(self.m.fmt("7.5"), "7.50")


class TestExtractWeight(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = _load_calc()

    def test_extract_integer_string(self):
        self.assertEqual(self.m.extract_weight("10 kg"), 10.0)

    def test_extract_float_string(self):
        self.assertEqual(self.m.extract_weight("5.5kg"), 5.5)

    def test_extract_bare_int(self):
        self.assertEqual(self.m.extract_weight(20), 20.0)

    def test_extract_bare_float(self):
        self.assertEqual(self.m.extract_weight(3.14), 3.14)

    def test_extract_none(self):
        self.assertIsNone(self.m.extract_weight(None))

    def test_extract_no_number(self):
        self.assertIsNone(self.m.extract_weight("heavy"))

    def test_extract_with_prefix(self):
        result = self.m.extract_weight("Weight: 42.5 lbs")
        self.assertEqual(result, 42.5)

    def test_extract_zero(self):
        self.assertEqual(self.m.extract_weight(0), 0.0)


class TestNormalizeCountry(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = _load_calc()

    def test_lowercase_output(self):
        self.assertEqual(self.m.normalize_country("India"), "india")

    def test_strips_whitespace(self):
        self.assertEqual(self.m.normalize_country("  India  "), "india")

    def test_removes_digits(self):
        result = self.m.normalize_country("India123")
        self.assertNotIn("1", result)

    def test_removes_special_chars(self):
        result = self.m.normalize_country("U.S.A.")
        self.assertNotIn(".", result)

    def test_empty_string(self):
        self.assertEqual(self.m.normalize_country(""), "")

    def test_none_returns_empty(self):
        self.assertEqual(self.m.normalize_country(None), "")

    def test_multi_word(self):
        result = self.m.normalize_country("United States")
        self.assertIn("united", result)
        self.assertIn("states", result)


class TestDeriveDeliveryType(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = _load_calc()

    def test_empty_suppliers_returns_none(self):
        self.assertIsNone(self.m.derive_delivery_type([]))

    def test_global_when_freight_partner_set(self):
        supplier = MagicMock()
        supplier.freight_delivery_partner = "DHL"
        result = self.m.derive_delivery_type([supplier])
        self.assertEqual(result, "global")

    def test_local_when_no_freight_partner(self):
        supplier = MagicMock()
        supplier.freight_delivery_partner = None
        result = self.m.derive_delivery_type([supplier])
        self.assertEqual(result, "local")

    def test_uses_first_supplier_only(self):
        s1 = MagicMock()
        s1.freight_delivery_partner = None
        s2 = MagicMock()
        s2.freight_delivery_partner = "FedEx"
        result = self.m.derive_delivery_type([s1, s2])
        self.assertEqual(result, "local")  # only s1 is checked


# ─────────────────────────────────────────────────────────────────────────────
# superadmin_bot_template_routes — is_super_admin()
# ─────────────────────────────────────────────────────────────────────────────
class TestIsSuperAdmin(unittest.TestCase):

    def _call_with_role(self, role):
        from flask import Flask
        from flask_jwt_extended import JWTManager, create_access_token, get_jwt

        app = Flask(__name__)
        app.config["JWT_SECRET_KEY"] = "test-super-secret"
        JWTManager(app)

        with app.test_request_context():
            with patch("flask_jwt_extended.get_jwt", return_value={"role": role}):
                import app.routes.superadmin_bot_template_routes as m
                return m.is_super_admin()

    def test_superadmin_role(self):
        from flask import Flask
        from flask_jwt_extended import JWTManager
        import app.routes.superadmin_bot_template_routes as m

        app = Flask(__name__)
        app.config["JWT_SECRET_KEY"] = "test"
        JWTManager(app)
        with app.test_request_context():
            with patch("app.routes.superadmin_bot_template_routes.get_jwt",
                       return_value={"role": "superadmin"}):
                self.assertTrue(m.is_super_admin())

    def test_super_admin_with_underscore(self):
        import app.routes.superadmin_bot_template_routes as m
        from flask import Flask
        from flask_jwt_extended import JWTManager

        app = Flask(__name__)
        app.config["JWT_SECRET_KEY"] = "test"
        JWTManager(app)
        with app.test_request_context():
            with patch("app.routes.superadmin_bot_template_routes.get_jwt",
                       return_value={"role": "super_admin"}):
                self.assertTrue(m.is_super_admin())

    def test_regular_user_is_not_super_admin(self):
        import app.routes.superadmin_bot_template_routes as m
        from flask import Flask
        from flask_jwt_extended import JWTManager

        app = Flask(__name__)
        app.config["JWT_SECRET_KEY"] = "test"
        JWTManager(app)
        with app.test_request_context():
            with patch("app.routes.superadmin_bot_template_routes.get_jwt",
                       return_value={"role": "user"}):
                self.assertFalse(m.is_super_admin())

    def test_empty_role_is_not_super_admin(self):
        import app.routes.superadmin_bot_template_routes as m
        from flask import Flask
        from flask_jwt_extended import JWTManager

        app = Flask(__name__)
        app.config["JWT_SECRET_KEY"] = "test"
        JWTManager(app)
        with app.test_request_context():
            with patch("app.routes.superadmin_bot_template_routes.get_jwt",
                       return_value={"role": ""}):
                self.assertFalse(m.is_super_admin())

    def test_case_insensitive_superadmin(self):
        import app.routes.superadmin_bot_template_routes as m
        from flask import Flask
        from flask_jwt_extended import JWTManager

        app = Flask(__name__)
        app.config["JWT_SECRET_KEY"] = "test"
        JWTManager(app)
        with app.test_request_context():
            with patch("app.routes.superadmin_bot_template_routes.get_jwt",
                       return_value={"role": "SuperAdmin"}):
                self.assertTrue(m.is_super_admin())


# ─────────────────────────────────────────────────────────────────────────────
# user_routes — password and email validation logic
# ─────────────────────────────────────────────────────────────────────────────
class TestUserValidationLogic(unittest.TestCase):
    """
    Test the validation logic embedded in register_user without hitting DB.
    We call the route through the test client and check boundary conditions.
    """

    @classmethod
    def setUpClass(cls):
        with patch("spacy.load", return_value=MagicMock()), \
             patch("qdrant_client.QdrantClient", return_value=MagicMock()):
            from flask import Flask
            from flask_jwt_extended import JWTManager
            app = Flask(__name__)
            app.config.update(
                TESTING=True,
                SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
                SQLALCHEMY_TRACK_MODIFICATIONS=False,
                JWT_SECRET_KEY="test-val-logic",
                SECRET_KEY="test-val-logic",
            )
            from app.models import db
            db.init_app(app)
            JWTManager(app)
            from app.routes.user_routes import user_blueprint
            app.register_blueprint(user_blueprint, url_prefix="/user")
            with app.app_context():
                db.create_all()
            cls.app = app
            cls.client = app.test_client()

    def test_password_exactly_8_chars_accepted(self):
        resp = self.client.post("/user/register", json={
            "fullname": "A", "email": "e8@test.com",
            "account_name": "acc8", "password": "12345678", "acceptTerms": True
        })
        self.assertNotEqual(resp.status_code, 400)

    def test_password_7_chars_rejected(self):
        resp = self.client.post("/user/register", json={
            "fullname": "A", "email": "e7@test.com",
            "account_name": "acc7", "password": "1234567", "acceptTerms": True
        })
        self.assertEqual(resp.status_code, 400)

    def test_account_name_with_hyphen_accepted(self):
        resp = self.client.post("/user/register", json={
            "fullname": "A", "email": "hyph@test.com",
            "account_name": "my-account", "password": "Password1!", "acceptTerms": True
        })
        self.assertNotEqual(resp.status_code, 400)

    def test_account_name_with_underscore_accepted(self):
        resp = self.client.post("/user/register", json={
            "fullname": "A", "email": "us@test.com",
            "account_name": "my_account", "password": "Password1!", "acceptTerms": True
        })
        self.assertNotEqual(resp.status_code, 400)

    def test_account_name_with_space_rejected(self):
        resp = self.client.post("/user/register", json={
            "fullname": "A", "email": "sp@test.com",
            "account_name": "my account", "password": "Password1!", "acceptTerms": True
        })
        self.assertEqual(resp.status_code, 400)

    def test_accept_terms_string_true_rejected(self):
        """acceptTerms must be a boolean True, not string "true"."""
        resp = self.client.post("/user/register", json={
            "fullname": "A", "email": "strterm@test.com",
            "account_name": "strtermac", "password": "Password1!", "acceptTerms": "true"
        })
        # "true" string != True — should be rejected
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
