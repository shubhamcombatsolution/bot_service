"""
Model integrity tests — uses SQLite in-memory so no real DB needed.
Tests that models can be created, persisted, and queried correctly.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("LLM_ENCRYPTION_KEY", "vX3Kx5q7vT3TQqgq2YQ0nO1E7iH2F7k6Hn5s3aQbYq8=")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
sys.path.insert(0, "/root/botBuilder/bb_master/bb_service")


def _make_app():
    with patch("spacy.load", return_value=MagicMock()), \
         patch("qdrant_client.QdrantClient", return_value=MagicMock()):
        from flask import Flask
        from flask_jwt_extended import JWTManager
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            JWT_SECRET_KEY="test-jwt-secret",
            SECRET_KEY="test-secret",
        )
        from app.models import db
        db.init_app(app)
        JWTManager(app)
        with app.app_context():
            db.create_all()
        return app, db


class TestTenantModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app, cls.db = _make_app()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.session = self.db.session

    def tearDown(self):
        self.db.session.rollback()
        self.ctx.pop()

    def _make_tenant(self, **kwargs):
        from app.models.tenant import Tenant
        defaults = dict(
            tenant_name="Test Corp",
            tenant_key="test-corp",
            tenant_emailid="admin@test.com",
            tenant_contact="9999999999",
            tenant_address="123 Test St",
        )
        defaults.update(kwargs)
        return Tenant(**defaults)

    def test_create_tenant(self):
        t = self._make_tenant()
        self.session.add(t)
        self.session.commit()
        self.assertIsNotNone(t.tenant_id)

    def test_tenant_unique_email(self):
        from sqlalchemy.exc import IntegrityError
        t1 = self._make_tenant(tenant_emailid="dupe@test.com", tenant_key="key1")
        t2 = self._make_tenant(tenant_emailid="dupe@test.com", tenant_key="key2")
        self.session.add(t1)
        self.session.commit()
        self.session.add(t2)
        with self.assertRaises(Exception):
            self.session.commit()

    def test_tenant_defaults(self):
        t = self._make_tenant(tenant_key="defaults-test", tenant_emailid="defaults@t.com")
        self.session.add(t)
        self.session.commit()
        fetched = self.session.get(type(t), t.tenant_id)
        self.assertIsNotNone(fetched)

    def test_tenant_name_stored_correctly(self):
        t = self._make_tenant(tenant_name="MyBusiness", tenant_key="mybiz", tenant_emailid="biz@biz.com")
        self.session.add(t)
        self.session.commit()
        from app.models.tenant import Tenant
        result = self.session.query(Tenant).filter_by(tenant_key="mybiz").first()
        self.assertEqual(result.tenant_name, "MyBusiness")


class TestLoginUserModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app, cls.db = _make_app()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.db.session.rollback()
        self.ctx.pop()

    def _make_tenant(self):
        from app.models.tenant import Tenant
        t = Tenant(
            tenant_name="LoginTest",
            tenant_key="login-test-key",
            tenant_emailid="logintest@example.com",
            tenant_contact="8888888888",
            tenant_address="456 Login Ave",
        )
        self.db.session.add(t)
        self.db.session.flush()
        return t

    def test_create_login_user(self):
        from app.models.login_user import LoginUser
        from werkzeug.security import generate_password_hash
        tenant = self._make_tenant()
        user = LoginUser(
            fullname="Test User",
            email="user@test.com",
            password_hash=generate_password_hash("password123"),
            tenant_id=tenant.tenant_id,
        )
        self.db.session.add(user)
        self.db.session.commit()
        self.assertIsNotNone(user.login_id)

    def test_password_is_hashed(self):
        from app.models.login_user import LoginUser
        from werkzeug.security import generate_password_hash, check_password_hash
        tenant = self._make_tenant()
        raw_pw = "MySecurePassword!"
        hashed = generate_password_hash(raw_pw)
        user = LoginUser(
            fullname="Hash User",
            email="hash@test.com",
            password_hash=hashed,
            tenant_id=tenant.tenant_id,
        )
        self.db.session.add(user)
        self.db.session.commit()
        self.assertNotEqual(user.password_hash, raw_pw)
        self.assertTrue(check_password_hash(user.password_hash, raw_pw))

    def test_del_flg_defaults_false(self):
        from app.models.login_user import LoginUser
        from werkzeug.security import generate_password_hash
        tenant = self._make_tenant()
        user = LoginUser(
            fullname="Del Test",
            email="del@test.com",
            password_hash=generate_password_hash("pw"),
            tenant_id=tenant.tenant_id,
        )
        self.db.session.add(user)
        self.db.session.commit()
        self.assertFalse(user.del_flg)


class TestKnowledgeBaseModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app, cls.db = _make_app()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.db.session.rollback()
        self.ctx.pop()

    def test_kb_has_name_field(self):
        from app.models.knowledge_base import KnowledgeBase
        cols = [c.key for c in KnowledgeBase.__table__.columns]
        self.assertIn("kb_name", cols)

    def test_kb_has_tenant_id(self):
        from app.models.knowledge_base import KnowledgeBase
        cols = [c.key for c in KnowledgeBase.__table__.columns]
        self.assertIn("tenant_id", cols)

    def test_kb_has_del_flg(self):
        from app.models.knowledge_base import KnowledgeBase
        cols = [c.key for c in KnowledgeBase.__table__.columns]
        self.assertIn("del_flg", cols)


class TestCustomBotNewModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app, cls.db = _make_app()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.db.session.rollback()
        self.ctx.pop()

    def test_model_has_required_columns(self):
        from app.models.new_models.custom_bot import CustomBotNew
        cols = {c.key for c in CustomBotNew.__table__.columns}
        for required in ["tenant_id", "bot_name", "del_flg", "bot_status"]:
            self.assertIn(required, cols, f"Missing column: {required}")

    def test_bot_status_enum_live_value(self):
        from app.models.new_models.custom_bot import BotStatusEnum
        self.assertEqual(BotStatusEnum.LIVE.value, "Live")

    def test_bot_status_enum_draft_value(self):
        from app.models.new_models.custom_bot import BotStatusEnum
        self.assertEqual(BotStatusEnum.DRAFT.value, "Draft")


class TestAgentModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app, cls.db = _make_app()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.db.session.rollback()
        self.ctx.pop()

    def test_agent_has_required_columns(self):
        from app.models.agent import Agent
        cols = {c.key for c in Agent.__table__.columns}
        for required in ["agent_id", "tenant_id", "agent_name", "del_flg", "agent_status"]:
            self.assertIn(required, cols, f"Missing column: {required}")

    def test_agent_status_enum_values_complete(self):
        from app.models.agent import AgentStatusEnum
        expected = {"Draft", "Created", "Live", "Paused", "Deleted"}
        actual = {e.value for e in AgentStatusEnum}
        self.assertEqual(expected, actual)

    def test_agent_del_flg_defaults_false(self):
        from app.models.agent import Agent
        col = Agent.__table__.columns["del_flg"]
        self.assertEqual(col.default.arg, False)


class TestBotTemplateModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app, cls.db = _make_app()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.db.session.rollback()
        self.ctx.pop()

    def test_bot_template_table_exists(self):
        from app.models.bot_template import BotTemplate
        self.assertIsNotNone(BotTemplate.__table__)

    def test_bot_template_has_template_name(self):
        from app.models.bot_template import BotTemplate
        cols = {c.key for c in BotTemplate.__table__.columns}
        self.assertIn("template_name", cols)

    def test_bot_template_has_source_bot_id(self):
        from app.models.bot_template import BotTemplate
        cols = {c.key for c in BotTemplate.__table__.columns}
        self.assertIn("source_bot_id", cols)


if __name__ == "__main__":
    unittest.main(verbosity=2)
