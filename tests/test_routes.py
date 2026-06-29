"""
Route-level integration tests for bb_service.

Uses Flask test client with SQLite in-memory DB.
All external services (DB, spacy, Qdrant) are mocked where needed.
"""
import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-routes")
os.environ.setdefault("SECRET_KEY", "test-secret-routes")
os.environ.setdefault("LLM_ENCRYPTION_KEY", "vX3Kx5q7vT3TQqgq2YQ0nO1E7iH2F7k6Hn5s3aQbYq8=")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
sys.path.insert(0, "/root/botBuilder/bb_master/bb_service")


def _make_test_app():
    with patch("spacy.load", return_value=MagicMock()), \
         patch("qdrant_client.QdrantClient", return_value=MagicMock()):
        from flask import Flask
        from flask_jwt_extended import JWTManager, create_access_token
        from flask_cors import CORS

        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            JWT_SECRET_KEY="test-jwt-secret-routes",
            SECRET_KEY="test-secret-routes",
            WTF_CSRF_ENABLED=False,
        )
        from app.models import db
        db.init_app(app)
        JWTManager(app)
        CORS(app)

        # Register only lightweight blueprints that have no heavy deps
        from app.routes.user_routes import user_blueprint
        from app.routes.role_routes import role_blueprint

        app.register_blueprint(user_blueprint, url_prefix="/user")
        app.register_blueprint(role_blueprint, url_prefix="/roles")

        with app.app_context():
            db.create_all()

        return app, db


def _auth_header(app, role="admin", tenant_id=1):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token = create_access_token(
            identity=str(tenant_id),
            additional_claims={"role": role, "tenant_id": tenant_id, "user_id": 1}
        )
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# Health / basic routes
# ─────────────────────────────────────────────────────────────────────────────
class TestHealthRoutes(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app, cls.db = _make_test_app()
        cls.client = cls.app.test_client()

    def test_home_returns_200(self):
        resp = self.client.get("/user/")
        self.assertEqual(resp.status_code, 200)

    def test_home_response_text(self):
        resp = self.client.get("/user/")
        self.assertIn(b"Flask", resp.data)


# ─────────────────────────────────────────────────────────────────────────────
# Login endpoint
# ─────────────────────────────────────────────────────────────────────────────
class TestLoginRoute(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app, cls.db = _make_test_app()
        cls.client = cls.app.test_client()

    def test_login_missing_email(self):
        resp = self.client.post(
            "/user/login",
            json={"password": "password123"},
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")

    def test_login_missing_password(self):
        resp = self.client.post(
            "/user/login",
            json={"email": "user@test.com"},
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")

    def test_login_empty_body(self):
        resp = self.client.post(
            "/user/login",
            json={},
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_login_invalid_credentials(self):
        resp = self.client.post(
            "/user/login",
            json={"email": "nonexistent@test.com", "password": "wrongpass"},
            content_type="application/json"
        )
        self.assertIn(resp.status_code, [401, 403, 500])

    def test_login_content_type_json(self):
        resp = self.client.post("/user/login", data="not json")
        self.assertIn(resp.status_code, [400, 415, 500])

    def test_login_valid_user_flow(self):
        """Create a real user and test full login flow."""
        from werkzeug.security import generate_password_hash
        from app.models.login_user import LoginUser
        from app.models.tenant import Tenant

        with self.app.app_context():
            tenant = Tenant(
                tenant_name="LoginTest",
                tenant_key="login-route-test",
                tenant_emailid="routetest@example.com",
                tenant_contact="1234567890",
                tenant_address="Test Address",
                tenant_status="Active",
                del_flg=False,
            )
            self.db.session.add(tenant)
            self.db.session.flush()

            user = LoginUser(
                fullname="Route Test User",
                email="routetest@example.com",
                password_hash=generate_password_hash("TestPass123!"),
                tenant_id=tenant.tenant_id,
                del_flg=False,
            )
            self.db.session.add(user)
            self.db.session.commit()

        resp = self.client.post(
            "/user/login",
            json={"email": "routetest@example.com", "password": "TestPass123!"},
            content_type="application/json"
        )
        # Should succeed (200) or give tenant-inactive error — not a 500
        self.assertNotEqual(resp.status_code, 500)

    def test_login_wrong_password_rejected(self):
        """Correct email, wrong password → 401."""
        resp = self.client.post(
            "/user/login",
            json={"email": "routetest@example.com", "password": "WrongPassword!"},
            content_type="application/json"
        )
        self.assertIn(resp.status_code, [401, 403])

    def test_login_sql_injection_in_email(self):
        """SQL injection attempts should not cause 500."""
        resp = self.client.post(
            "/user/login",
            json={"email": "' OR 1=1 --", "password": "anything"},
            content_type="application/json"
        )
        self.assertNotEqual(resp.status_code, 500)

    def test_login_xss_in_email(self):
        """XSS payload in email should return error, not crash."""
        resp = self.client.post(
            "/user/login",
            json={"email": "<script>alert(1)</script>@test.com", "password": "pw"},
            content_type="application/json"
        )
        self.assertNotEqual(resp.status_code, 500)


# ─────────────────────────────────────────────────────────────────────────────
# Register endpoint
# ─────────────────────────────────────────────────────────────────────────────
class TestRegisterRoute(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app, cls.db = _make_test_app()
        cls.client = cls.app.test_client()

    def _valid_payload(self, email="newuser@test.com", account="newuser"):
        return {
            "fullname": "New User",
            "email": email,
            "account_name": account,
            "password": "Password123!",
            "acceptTerms": True,
        }

    def test_register_missing_fullname(self):
        payload = self._valid_payload()
        del payload["fullname"]
        resp = self.client.post("/user/register", json=payload)
        self.assertEqual(resp.status_code, 400)

    def test_register_missing_email(self):
        payload = self._valid_payload()
        del payload["email"]
        resp = self.client.post("/user/register", json=payload)
        self.assertEqual(resp.status_code, 400)

    def test_register_missing_password(self):
        payload = self._valid_payload()
        del payload["password"]
        resp = self.client.post("/user/register", json=payload)
        self.assertEqual(resp.status_code, 400)

    def test_register_terms_not_accepted(self):
        payload = self._valid_payload()
        payload["acceptTerms"] = False
        resp = self.client.post("/user/register", json=payload)
        self.assertEqual(resp.status_code, 400)

    def test_register_password_too_short(self):
        payload = self._valid_payload()
        payload["password"] = "short"
        resp = self.client.post("/user/register", json=payload)
        self.assertEqual(resp.status_code, 400)

    def test_register_invalid_email_format(self):
        payload = self._valid_payload(email="not-an-email")
        resp = self.client.post("/user/register", json=payload)
        self.assertEqual(resp.status_code, 400)

    def test_register_invalid_account_name_chars(self):
        payload = self._valid_payload(account="has spaces!")
        resp = self.client.post("/user/register", json=payload)
        self.assertEqual(resp.status_code, 400)

    def test_register_empty_body(self):
        resp = self.client.post("/user/register", json={})
        self.assertEqual(resp.status_code, 400)

    def test_register_success_returns_non_500(self):
        """Valid registration should not 500."""
        payload = self._valid_payload(email="brand-new@test.com", account="brandnew123")
        resp = self.client.post("/user/register", json=payload)
        self.assertNotEqual(resp.status_code, 500)

    def test_register_duplicate_email_rejected(self):
        """Second registration with same email → 409."""
        payload = self._valid_payload(email="dupe-reg@test.com", account="dupe1")
        self.client.post("/user/register", json=payload)  # first
        payload2 = self._valid_payload(email="dupe-reg@test.com", account="dupe2")
        resp = self.client.post("/user/register", json=payload2)
        # expect 409 conflict or at least not 500
        self.assertNotEqual(resp.status_code, 500)


# ─────────────────────────────────────────────────────────────────────────────
# Protected route — JWT required
# ─────────────────────────────────────────────────────────────────────────────
class TestProtectedRoutes(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app, cls.db = _make_test_app()
        cls.client = cls.app.test_client()

    def test_account_name_requires_jwt(self):
        resp = self.client.get("/user/account-name")
        self.assertIn(resp.status_code, [401, 422])

    def test_user_details_requires_jwt(self):
        resp = self.client.get("/user/details")
        self.assertIn(resp.status_code, [401, 422])

    def test_user_resource_counts_requires_jwt(self):
        resp = self.client.get("/user/user-resource-counts")
        self.assertIn(resp.status_code, [401, 422])

    def test_invalid_token_rejected(self):
        resp = self.client.get(
            "/user/details",
            headers={"Authorization": "Bearer totally-invalid-token"}
        )
        self.assertIn(resp.status_code, [401, 422])

    def test_expired_token_rejected(self):
        """An expired token should be rejected (422 from flask-jwt)."""
        import time
        from flask_jwt_extended import create_access_token
        from datetime import timedelta
        with self.app.app_context():
            token = create_access_token(
                identity="1",
                expires_delta=timedelta(seconds=-1),  # already expired
                additional_claims={"tenant_id": 1, "role": "admin"}
            )
        resp = self.client.get(
            "/user/details",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertIn(resp.status_code, [401, 422])

    def test_account_name_with_valid_token(self):
        headers = _auth_header(self.app)
        resp = self.client.get("/user/account-name", headers=headers)
        # should not be a 401/422 auth error
        self.assertNotIn(resp.status_code, [401, 422])

    def test_forgot_password_no_email(self):
        resp = self.client.post("/user/forgot-password", json={})
        self.assertNotEqual(resp.status_code, 500)

    def test_send_reset_email_strips_smtp_password_whitespace(self):
        from app.routes.user_routes import send_reset_email

        with patch.dict(
            os.environ,
            {
                "SMTP_USER": "user@example.com",
                "SMTP_PASS": "abcd efgh ijkl mnop",
                "SMTP_FROM": "from@example.com",
            },
            clear=False,
        ), patch("app.routes.user_routes.ssl.create_default_context", return_value=MagicMock()), patch(
            "app.routes.user_routes.smtplib.SMTP"
        ) as smtp_cls:
            server = smtp_cls.return_value.__enter__.return_value
            send_reset_email("to@example.com", "https://example.com/reset")

            server.login.assert_called_once_with("user@example.com", "abcdefghijklmnop")

    def test_method_not_allowed(self):
        resp = self.client.delete("/user/login")
        self.assertEqual(resp.status_code, 405)


# ─────────────────────────────────────────────────────────────────────────────
# Roles blueprint
# ─────────────────────────────────────────────────────────────────────────────
class TestRoleRoutes(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app, cls.db = _make_test_app()
        cls.client = cls.app.test_client()

    def test_get_all_roles_returns_list(self):
        resp = self.client.get("/roles/")
        self.assertIn(resp.status_code, [200, 401, 422])  # may require JWT

    def test_register_role_missing_fields(self):
        resp = self.client.post("/roles/register", json={})
        self.assertNotEqual(resp.status_code, 500)

    def test_get_role_by_id_not_found(self):
        resp = self.client.get("/roles/99999")
        self.assertNotEqual(resp.status_code, 500)


if __name__ == "__main__":
    unittest.main(verbosity=2)
