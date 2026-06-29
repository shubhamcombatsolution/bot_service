
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from app.models.login_user import LoginUser
from app.models.tenant import Tenant
from app.models.custome_bot import CustomBot
from app.models.tenant_collaborator import Collaborator
from app.models.agent import Agent
from app.database.DatabaseOperationPostgreSQL import db_session
import re
import uuid
from google.oauth2 import id_token
from google.auth.transport import requests
import logging
from app.models.knowledge_base import KnowledgeBase
from app.models.llm import LLM
from os.path import basename
import secrets, hashlib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import smtplib, ssl, os
from urllib.parse import quote_plus
from sqlalchemy import desc
from app.models import TenantSubscription
from app.utils import add_free_subscription
from flask import g
from app.routes.helpers.access_control_decorator import authorize

user_blueprint = Blueprint("user", __name__)
logger = logging.getLogger(__name__)

@user_blueprint.route('/', methods=['GET'])
def home():
    return "Flask Application is running."

# @user_blueprint.route("/subdomain", methods=["GET"])
# def handle_subdomain():
#     try:
#         session = next(db_session())
        
#         # Get subdomain from X-Subdomain header
#         subdomain = request.headers.get("X-Subdomain")
#         if not subdomain:
#             logger.error("Subdomain header missing")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Subdomain header is required"
#             }), 400

#         # Validate subdomain format
#         if not re.match(r"^[a-zA-Z0-9_-]+$", subdomain):
#             logger.error(f"Invalid subdomain format: {subdomain}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Invalid subdomain format"
#             }), 400

#         # Get API key from X-API-Key header
#         api_key = request.headers.get("X-API-Key")
#         if not api_key:
#             logger.error("API key missing for subdomain request")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "API key is required"
#             }), 401

#         # Find user by API key
#         user = session.query(LoginUser).filter_by(api_key=api_key, del_flg=False).first()
#         if not user:
#             logger.error("Invalid API key provided")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Invalid API key"
#             }), 401

#         # Find tenant by subdomain (account_name)
#         subdomain_user = session.query(LoginUser).filter_by(account_name=subdomain, del_flg=False).first()
#         if not subdomain_user:
#             logger.error(f"No user found for subdomain: {subdomain}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Subdomain not found"
#             }), 404

#         # Verify that the authenticated user matches the subdomain's tenant_id
#         if user.tenant_id != subdomain_user.tenant_id:
#             logger.error(f"Unauthorized access attempt to subdomain {subdomain} by tenant_id {user.tenant_id}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Unauthorized access to this subdomain"
#             }), 403

#         # Fetch tenant details
#         tenant = session.query(Tenant).filter_by(tenant_id=user.tenant_id).first()
#         if not tenant or tenant.tenant_status != "Active":
#             logger.warning(f"Inactive tenant attempted access: tenant_id={user.tenant_id}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Tenant account is inactive. Contact support."
#             }), 403

#         # Fetch bots for the tenant
#         bots = session.query(CustomBot).filter_by(tenant_id=user.tenant_id, del_flg=False).all()
#         base_url = request.host_url.rstrip('/')
#         avatar_base_path = "custom-bot/uploads/avatars"
#         bot_list = [
#             {
#                 "bot_id": bot.bot_id,
#                 "bot_name": bot.bot_name,
#                 "avatar": (
#                     f"{base_url}/{avatar_base_path}/{basename(bot.avatar)}"
#                     if bot.avatar and not bot.avatar.startswith(('http://', 'https://'))
#                     else bot.avatar or ""
#                 ),
#                 "purpose": bot.purpose or "",
#                 "status": bot.status
#             }
#             for bot in bots
#         ]

#         # Fetch agents for the tenant
#         agents = session.query(Agent).filter_by(tenant_id=user.tenant_id, del_flg=False).all()
#         agent_list = [
#             {
#                 "agent_id": agent.agent_id,
#                 "agent_name": agent.agent_name,
#                 "agent_role": agent.agent_role,
#                 "agent_description": agent.agent_description or ""
#             }
#             for agent in agents
#         ]

#         # Return tenant-specific data
#         return jsonify({
#             "data": {
#                 "user": {
#                     "login_id": user.login_id,
#                     "fullname": user.fullname,
#                     "email": user.email,
#                     "account_name": user.account_name,
#                     "tenant_id": user.tenant_id,
#                     "api_key": user.api_key
#                 },
#                 "bots": bot_list,
#                 "agents": agent_list
#             },
#             "status": "success",
#             "message": f"Welcome to {subdomain}.jnanic.com"
#         }), 200

#     except Exception as e:
#         logger.exception(f"Error handling subdomain request: {str(e)}")
#         return jsonify({
#             "data": {},
#             "status": "error",
#             "message": "Internal server error"
#         }), 500
#     finally:
#         session.close()



@user_blueprint.route("/subdomain", methods=["GET"])
def handle_subdomain():
    try:
        session = next(db_session())
        
        # Extract subdomain from host
        host = request.host
        subdomain = host.split('.')[0] if '.' in host else None
        if not subdomain:
            logger.error("Subdomain not found in request host")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Subdomain is required"
            }), 400

        # Validate subdomain format
        if not re.match(r"^[a-zA-Z0-9_-]+$", subdomain):
            logger.error(f"Invalid subdomain format: {subdomain}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Invalid subdomain format"
            }), 400

        # Get API key from X-API-Key header
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            logger.error("API key missing for subdomain request")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "API key is required"
            }), 401

        # Find user by API key
        user = session.query(LoginUser).filter_by(api_key=api_key, del_flg=False).first()
        if not user:
            logger.error("Invalid API key provided")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Invalid API key"
            }), 401

        # Find tenant by subdomain (account_name)
        subdomain_user = session.query(LoginUser).filter_by(account_name=subdomain, del_flg=False).first()
        if not subdomain_user:
            logger.error(f"No user found for subdomain: {subdomain}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Subdomain not found"
            }), 404

        # Verify that the authenticated user matches the subdomain's tenant_id
        if user.tenant_id != subdomain_user.tenant_id:
            logger.error(f"Unauthorized access attempt to subdomain {subdomain} by tenant_id {user.tenant_id}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Unauthorized access to this subdomain"
            }), 403

        # Fetch tenant details
        tenant = session.query(Tenant).filter_by(tenant_id=user.tenant_id, tenant_status="Active").first()
        if not tenant:
            logger.warning(f"Inactive tenant attempted access: tenant_id={user.tenant_id}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Tenant account is inactive. Contact support."
            }), 403

        # Fetch bots for the tenant
        bots = session.query(CustomBot).filter_by(tenant_id=user.tenant_id, del_flg=False, status=True).all()
        base_url = current_app.config.get('BASE_URL', 'https://api.jnanic.com')
        avatar_base_path = "custom-bot/uploads/avatars"
        bot_list = [
            {
                "bot_id": bot.bot_id,
                "bot_name": bot.bot_name,
                "avatar": (
                    f"{base_url}/{avatar_base_path}/{basename(bot.avatar)}"
                    if bot.avatar and not bot.avatar.startswith(('http://', 'https://'))
                    else bot.avatar or ""
                ),
                "purpose": bot.purpose or "",
                "status": bot.status
            }
            for bot in bots
        ]

        # Fetch agents for the tenant
        agents = session.query(Agent).filter_by(tenant_id=user.tenant_id, del_flg=False).all()
        agent_list = [
            {
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "agent_role": agent.agent_role,
                "agent_description": agent.agent_description or "",
                "agent_key": agent.agent_key or ""
            }
            for agent in agents
        ]

        return jsonify({
            "data": {
                "user": {
                    "login_id": user.login_id,
                    "fullname": user.fullname,
                    "email": user.email,
                    "account_name": user.account_name,
                    "tenant_id": user.tenant_id,
                    "api_key": user.api_key
                },
                "bots": bot_list,
                "agents": agent_list
            },
            "status": "success",
            "message": f"Welcome to {subdomain}.jnanic.com"
        }), 200
    except Exception as e:
        logger.exception(f"Error handling subdomain request: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
    finally:
        session.close()




# # New route to get account_name of the logged-in user
# @user_blueprint.route("/account-name", methods=["GET"])
# @jwt_required()
# def get_account_name():
#     try:
#         claims = get_jwt()
#         tenant_id = claims.get("tenant_id")
#         if not tenant_id:
#             logger.error("Tenant ID not found in token")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Tenant ID not found in token"
#             }), 401

#         session = next(db_session())
#         user = session.query(LoginUser).filter_by(tenant_id=tenant_id, del_flg=False).first()
#         if not user:
#             logger.error(f"No user found for tenant_id: {tenant_id}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "User not found"
#             }), 404

#         return jsonify({
#             "data": {
#                 "account_name": user.account_name
#             },
#             "status": "success",
#             "message": "Account name retrieved successfully"
#         }), 200
#     except Exception as e:
#         logger.exception(f"Error retrieving account name: {str(e)}")
#         return jsonify({
#             "data": {},
#             "status": "error",
#             "message": "Internal server error"
#         }), 500
#     finally:
#         session.close()


# Updated route to get account_name and api_key of the logged-in user
@user_blueprint.route("/account-name", methods=["GET"])
@jwt_required()
def get_account_name():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Tenant ID not found in token"
            }), 401

        session = next(db_session())
        user = session.query(LoginUser).filter_by(tenant_id=tenant_id, del_flg=False).first()
        if not user:
            logger.error(f"No user found for tenant_id: {tenant_id}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "User not found"
            }), 404

        return jsonify({
            "data": {
                "account_name": user.account_name,
                "api_key": user.api_key
            },
            "status": "success",
            "message": "Account details retrieved successfully"
        }), 200
    except Exception as e:
        logger.exception(f"Error retrieving account details: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
    finally:
        session.close()



# @user_blueprint.route("/login", methods=["POST"])
# def tenant_login():
#     try:
#         session = next(db_session())
#         data = request.json
#         email = data.get("email")
#         password = data.get("password")

#         if not email or not password:
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Email and password are required"
#             }), 400

#         user = session.query(LoginUser).filter_by(email=email).first()
        
#         if not user or not check_password_hash(user.password_hash, password):
#             logger.error(f"Invalid login attempt for email {email}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Invalid credentials"
#             }), 401

#         # Check if user is deleted
#         if user.del_flg is True:
#             logger.warning(f"Login attempt for deleted user: email={email}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "User account has been deleted. Contact support."
#             }), 403

#         # Check tenant status
#         tenant = session.query(Tenant).filter_by(tenant_id=user.tenant_id).first()
#         if not tenant or tenant.tenant_status != "Active":
#             logger.warning(f"Login attempt for inactive tenant: tenant_id={user.tenant_id}, email={email}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Tenant account is inactive. Contact support."
#             }), 403

#         # Check tenant deletion flag
#         if tenant.del_flg is True:
#             logger.warning(f"Login attempt for deleted tenant: tenant_id={user.tenant_id}, email={email}")
#             return jsonify({
#                 "data": {},
#                 "status": "error",
#                 "message": "Tenant account has been deleted. Contact support."
#             }), 403

#         # Generate API key if not already present
#         if not user.api_key:
#             user.api_key = user.generate_api_key()
#             session.commit()

#         # Map user.role to "admin" if it is "1"
#         role = "admin" if user.role == "1" else user.role

#         access_token = create_access_token(
#             identity=str(user.login_id),
#             additional_claims={
#                 "tenant_id": user.tenant_id,
#                 "role": role
#             }
#         )
        
#         existing = session.query(TenantSubscription).filter_by(
#             tenant_id=user.tenant_id, subscription_status='active'
#         ).first()

#         if not existing:
#              add_free_subscription(session, user.tenant_id)

#         return jsonify({
#             "data": {
#                 "login_id": user.login_id,
#                 "tenant_id": user.tenant_id,
#                 "access_token": access_token,
#                 "api_key": user.api_key,
#                 "role": role
#             },
#             "status": "success",
#             "message": "Login successful"
#         }), 200

#     except Exception as e:
#         logger.exception(f"Error during login: {str(e)}")
#         return jsonify({
#             "data": {},
#             "status": "error",
#             "message": "Internal server error"
#         }), 500
#     finally:
#         session.close()

@user_blueprint.route("/login", methods=["POST"])
def tenant_login():
    session = next(db_session())
    try:
        data = request.json or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password")

        if not email or not password:
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Email and password are required"
            }), 400

        # ---------------------------------------
        # 1️⃣ Try LoginUser (Tenant Admin)
        # ---------------------------------------
        user = session.query(LoginUser).filter_by(email=email).first()
        user_type = None

        if user and check_password_hash(user.password_hash, password):
            user_type = "admin"

        else:
            # ---------------------------------------
            # 2️⃣ Try Collaborator
            # ---------------------------------------
            collaborator = session.query(Collaborator).filter_by(
                email=email,
                del_flg=False
            ).first()

            if not collaborator or not check_password_hash(collaborator.password_hash, password):
                return jsonify({
                    "data": {},
                    "status": "error",
                    "message": "Invalid credentials"
                }), 401

            if collaborator.status != "Active":
                return jsonify({
                    "data": {},
                    "status": "error",
                    "message": "User account inactive"
                }), 403

            user = collaborator
            user_type = "collaborator"

        # ---------------------------------------
        # Tenant Validation (Common)
        # ---------------------------------------
        tenant = session.query(Tenant).filter_by(
            tenant_id=user.tenant_id,
            del_flg=False
        ).first()

        if not tenant or tenant.tenant_status != "Active":
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Tenant account inactive"
            }), 403

        # ---------------------------------------
        # Role Mapping
        # ---------------------------------------
        role = "admin" if getattr(user, "role", None) == "1" else user.role

        # ---------------------------------------
        # JWT Token
        # ---------------------------------------
        access_token = create_access_token(
            identity=str(user.tenant_id),
            additional_claims={
                "tenant_id": user.tenant_id,
                "user_id": getattr(user, "login_id", None) or user.collaborator_id,
                "role": role,
                "user_type": user_type
            }
        )

        return jsonify({
            "data": {
                "tenant_id": user.tenant_id,
                "user_id": getattr(user, "login_id", None) or user.collaborator_id,
                "access_token": access_token,
                "role": role,
                "user_type": user_type
            },
            "status": "success",
            "message": "Login successful"
        }), 200

    except Exception as e:
        logger.exception(f"Error during login: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
    finally:
        session.close()

@user_blueprint.route("/register", methods=["POST"])
def register_user():
    print("🚀 REGISTER API CALLED")

    try:
        data = request.json
        print("📥 Incoming Data:", data)

        fullname = data.get("fullname")
        email = data.get("email")
        account_name = data.get("account_name")
        password = data.get("password")
        accept_terms = data.get("acceptTerms")

        # -------------------------------
        # VALIDATION LOGS
        # -------------------------------
        print("🔍 Validating input...")

        if not all([fullname, email, account_name, password, accept_terms]):
            print("❌ Missing required fields")
            return jsonify({
                "status": "error",
                "message": "Missing required fields"
            }), 400

        if accept_terms is not True:
            print("❌ Terms not accepted")
            return jsonify({
                "status": "error",
                "message": "Accept terms required"
            }), 400

        if len(password) < 8:
            print("❌ Password too short")
            return jsonify({
                "status": "error",
                "message": "Password too short"
            }), 400

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            print("❌ Invalid email format")
            return jsonify({
                "status": "error",
                "message": "Invalid email"
            }), 400

        if not re.match(r"^[a-zA-Z0-9_-]+$", account_name):
            print("❌ Invalid account name")
            return jsonify({
                "status": "error",
                "message": "Invalid account name"
            }), 400

        print("✅ Validation passed")

        # -------------------------------
        # DB SESSION START
        # -------------------------------
        session = next(db_session())
        print("🗄️ DB session started")

        try:
            # -------------------------------
            # CHECK EXISTING USER
            # -------------------------------
            print("🔍 Checking existing user...")
            existing_user = session.query(LoginUser).filter(
                (LoginUser.email == email) | (LoginUser.account_name == account_name)
            ).first()

            if existing_user:
                print("❌ User already exists:", existing_user.email)
                return jsonify({
                    "status": "error",
                    "message": "User already exists"
                }), 409

            print("✅ No existing user found")

            # -------------------------------
            # CREATE TENANT
            # -------------------------------
            print("🏢 Creating tenant...")
            new_tenant = Tenant(
                tenant_name=fullname,
                tenant_key=str(uuid.uuid4()),
                tenant_emailid=email,
                tenant_contact=data.get("contact"),
                tenant_address=data.get("address"),
                tenant_city=data.get("city"),
                tenant_country=data.get("country"),
                tenant_postcode=data.get("postcode"),
                tenant_GSTNo=data.get("gst_no"),
                tenant_PAN=data.get("pan"),
                tenant_status="Active",
                del_flg=False
            )

            session.add(new_tenant)
            session.flush()  # IMPORTANT
            print("✅ Tenant created with ID:", new_tenant.tenant_id)

            # -------------------------------
            # CREATE USER
            # -------------------------------
            print("👤 Creating user...")

            hashed_password = generate_password_hash(password)

            new_user = LoginUser(
                fullname=fullname,
                email=email,
                account_name=account_name,
                password_hash=hashed_password,
                role="1",
                tenant_id=new_tenant.tenant_id
            )

            # -------------------------------
            # GENERATE API KEY
            # -------------------------------
            try:
                print("🔑 Generating API key...")
                new_user.api_key = new_user.generate_api_key()
                print("✅ API key generated")
            except Exception as e:
                print("❌ API key generation failed:", e)
                raise e

            session.add(new_user)
            session.flush()  # get login_id

            print("✅ User created with login_id:", new_user.login_id)

            # Assign free plan subscription to new tenant
            add_free_subscription(session, new_tenant.tenant_id)
            print("✅ Free plan subscription created for tenant:", new_tenant.tenant_id)

            # -------------------------------
            # FINAL COMMIT
            # -------------------------------
            print("💾 Committing transaction...")
            session.commit()
            print("✅ DB commit successful")

            # -------------------------------
            # JWT TOKEN
            # -------------------------------
            print("🔐 Generating JWT token...")
            role = "admin" if new_user.role == "1" else new_user.role
            access_token = create_access_token(
                identity=str(new_user.tenant_id),
                additional_claims={
                    "tenant_id": new_user.tenant_id,
                    "user_id": new_user.login_id,
                    "role": role,
                    "user_type": "admin"
                }
            )
            print("✅ JWT generated")

            return jsonify({
                "data": {
                    "login_id": new_user.login_id,
                    "tenant_id": new_user.tenant_id,
                    "access_token": access_token,
                    "api_key": new_user.api_key,
                    "account_name": new_user.account_name,
                    "role": role,
                    "user_type": "admin"
                },
                "status": "success",
                "message": "Registration successful"
            }), 201

        except Exception as e:
            print("🔥 DB ERROR:", str(e))
            session.rollback()
            print("↩️ Transaction rolled back")

            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500

        finally:
            session.close()
            print("🔒 DB session closed")

    except Exception as e:
        print("🔥 UNEXPECTED ERROR:", str(e))
        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500

@user_blueprint.route("/details", methods=["GET", "OPTIONS"])
@jwt_required(optional=True)
def get_user_details():
    if request.method == "OPTIONS":
      return jsonify({"status": "ok"}), 200
    session = next(db_session())
    try:
        # user_id = get_jwt_identity()

        claims = get_jwt()
        user_id = claims.get("user_id")   # ✅ correct
        tenant_id = claims.get("tenant_id")
        role = claims.get("role")

        if not user_id or not tenant_id:
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Unauthorized"
            }), 401

        user = session.query(LoginUser).filter_by(login_id=int(user_id)).first()
        
        if not user:
            logger.error(f"User with ID {user_id} not found.")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "User not found"
            }), 404
        sub_msg = (
            session.query(TenantSubscription)
            .filter_by(tenant_id=int(tenant_id))
            .order_by(desc(TenantSubscription.subscription_id))
            .first()
        )
        return jsonify({
            "data": {
                "login_id": user.login_id,
                "fullname": user.fullname,
                "email": user.email,
                "account_name": user.account_name,
                "role": user.role,
                "tenant_id": user.tenant_id,
                "total_msg": sub_msg.total_plan_msg if sub_msg else 0,
                "remaining_msg": sub_msg.remaining_msg if sub_msg else 0,
            },
            "status": "success",
            "message": "User details fetched successfully"
        }), 200

    except Exception as e:
        logger.exception(f"Error fetching user details: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
    finally:
        session.close()

@user_blueprint.route("/google-login", methods=["POST"])
def google_login():
    try:
        session = next(db_session())
        data = request.json
        token = data.get("token")

        if not token:
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Google token is required"
            }), 400

        # Verify Google token
        CLIENT_ID = "700098458791-r2lpos991kscqc3uol46b1osrsc920fg.apps.googleusercontent.com"
        try:
            idinfo = id_token.verify_oauth2_token(token, requests.Request(), CLIENT_ID)
            email = idinfo['email']
        except ValueError as e:
            logger.error(f"Invalid Google token: {str(e)}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Invalid Google token"
            }), 401

        # Check if user exists, if not, create a new user
        user = session.query(LoginUser).filter_by(email=email).first()
        if not user:
            # Create a new tenant
            new_tenant = Tenant(
                tenant_name=email.split('@')[0],
                tenant_key=str(uuid.uuid4()),
                tenant_emailid=email,
                tenant_status="Active",
                del_flg=False
            )
            session.add(new_tenant)
            session.commit()

            # Create a new user
            new_user = LoginUser(
                fullname=email.split('@')[0],
                email=email,
                account_name=email.split('@')[0],
                password_hash='',
                role="admin",
                tenant_id=new_tenant.tenant_id
            )
            new_user.api_key = new_user.generate_api_key()
            session.add(new_user)
            session.commit()
            user = new_user

        else:
            # Existing user — generate api_key if missing
            if not user.api_key:
                logger.info(f"Generating missing api_key for existing user tenant_id={user.tenant_id}")
                user.api_key = user.generate_api_key()
                session.commit()

        # 🔹 Ensure user has a subscription
        existing = session.query(TenantSubscription).filter_by(
            tenant_id=user.tenant_id, subscription_status='active'
        ).first()

        if not existing:
            add_free_subscription(session, user.tenant_id)
            session.commit()

        # Generate access token
        access_token = create_access_token(
            identity=str(user.tenant_id),
            additional_claims={
                "tenant_id": user.tenant_id,
                "user_id": user.login_id,
                "role": user.role,
                "user_type": "admin"
            }
        )

        return jsonify({
            "data": {
                "login_id": user.login_id,
                "tenant_id": user.tenant_id,
                "access_token": access_token,
                "account_name": user.account_name,
                "api_key": user.api_key
            },
            "status": "success",
            "message": "Google login successful"
        }), 200

    except Exception as e:
        logger.exception(f"Error during Google login: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
    finally:
        session.close()


@user_blueprint.route("/user-resource-counts", methods=["GET"])
@jwt_required()
def get_user_resource_counts():
    try:
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        
        if not tenant_id:
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Tenant ID not found in token"
            }), 401

        session = next(db_session())
        
        # Count resources for the specific tenant
        bot_count = session.query(CustomBot).filter_by(
            tenant_id=tenant_id,
            del_flg=False
        ).count()
        
        agent_count = session.query(Agent).filter_by(
            tenant_id=tenant_id,
            del_flg=False
        ).count()
        
        knowledge_base_count = session.query(KnowledgeBase).filter_by(
            tenant_id=tenant_id,
            del_flg=False
        ).count()
        
        llm_count = session.query(LLM).filter_by(
            tenant_id=tenant_id,
            del_flg=False
        ).count()

        return jsonify({
            "data": {
                "bots": bot_count,
                "agents": agent_count,
                "knowledge_bases": knowledge_base_count,
                "llms": llm_count
            },
            "status": "success",
            "message": "Resource counts fetched successfully"
        }), 200

    except Exception as e:
        logger.exception(f"Error fetching resource counts: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
    finally:
        session.close()

@user_blueprint.route("/regenerate-api-key", methods=["POST"])
@jwt_required()
def regenerate_api_key():
    try:
        user_id = get_jwt_identity()
        session = next(db_session())
        user = session.query(LoginUser).filter_by(login_id=int(user_id)).first()
        
        if not user:
            return jsonify({
                "data": {},
                "status": "error",
                "message": "User not found"
            }), 404

        # Generate a new API key
        user.api_key = user.generate_api_key()
        session.commit()

        return jsonify({
            "data": {
                "api_key": user.api_key
            },
            "status": "success",
            "message": "API key regenerated successfully"
        }), 200

    except Exception as e:
        logger.exception(f"Error regenerating API key: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
    finally:
        session.close()

@user_blueprint.route("/create-api-key", methods=["POST"])
@jwt_required()
def create_api_key():
    try:
        user_id = get_jwt_identity()
        session = next(db_session())
        user = session.query(LoginUser).filter_by(login_id=int(user_id)).first()
        
        if not user:
            logger.error(f"User with ID {user_id} not found.")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "User not found"
            }), 404

        # Check if the user already has an API key
        if user.api_key:
            return jsonify({
                "data": {
                    "api_key": user.api_key
                },
                "status": "success",
                "message": "API key already exists for this user"
            }), 200

        # Generate a new API key
        user.api_key = user.generate_api_key()
        session.commit()

        logger.info(f"API key created for user_id={user_id}")
        return jsonify({
            "data": {
                "api_key": user.api_key
            },
            "status": "success",
            "message": "API key created successfully"
        }), 201

    except Exception as e:
        session.rollback()
        logger.exception(f"Error creating API key: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
    finally:
        session.close()


TOKEN_TTL_HOURS = 1

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)      # aware

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_smtp_credentials() -> tuple[str, str]:
    smtp_user = (os.environ.get("SMTP_USER") or "").strip().strip('"').strip("'")
    smtp_pass = (
        os.environ.get("SMTP_PASS")
        or os.environ.get("SMTP_PASSWORD")
        or ""
    ).strip().strip('"').strip("'")
    smtp_pass = re.sub(r"\s+", "", smtp_pass)
    return smtp_user, smtp_pass


def send_reset_email(to_addr: str, reset_url: str) -> None:
    smtp_user, smtp_pass = _get_smtp_credentials()
    if not smtp_user or not smtp_pass:
        raise RuntimeError("SMTP credentials are not configured")

    msg = EmailMessage()
    msg["Subject"] = "Reset your password"
    msg["From"] = os.environ.get("SMTP_FROM") or smtp_user
    msg["To"] = to_addr
    msg.set_content(
        f"""Hi,

    We received a request to reset your password. Click the link below
    (or copy–paste it into your browser) within the next hour:

    {reset_url}

    If you didn’t request this, simply ignore this e‑mail.

    Thanks,
    Your App Team
    """
        )

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587") or 587)
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls(context=context)
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

@user_blueprint.route("/forgot-password", methods=["POST"])
def request_reset():
    # Use ONE session for the whole request
    session = next(db_session())
    try:
        data = request.json or {}
        email = data.get("email", "").lower().strip()

        if not email:
            return jsonify({
                "status": "error",
                "message": "Email is required."
            }), 400

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return jsonify({
                "status": "error",
                "message": "Invalid email format."
            }), 400

        tenant = (
            session.query(Tenant)
                   .filter_by(tenant_emailid=email, del_flg=False, tenant_status="Active")
                   .first()
        )

        if not tenant:
            return jsonify({
                "status": "error",
                "message": "This email is not registered with any active tenant."
            }), 404

        # Always query through *this* session
        user = (
            session.query(LoginUser)
                   .filter_by(email=email, tenant_id=tenant.tenant_id, del_flg=False)
                   .first()
        )

        if not user:
            return jsonify({
                "status": "error",
                "message": "No active user account found for this tenant email."
            }), 404

        delay_start = _utcnow()

        raw_token = secrets.token_urlsafe(32)
        user.reset_token_hash  = _hash_token(raw_token)
        user.reset_expires_at = (
            _utcnow() + timedelta(hours=TOKEN_TTL_HOURS)
        ).replace(tzinfo=None)

        session.flush()   # push pending changes to the DB
        session.commit()  # COMMIT the transaction

        session.refresh(user)      # pull fresh values from DB
        if not user.reset_token_hash or not user.reset_expires_at:
            raise RuntimeError(
                "Password‑reset fields were not persisted (session mismatch?)"
            )
        # -----------------------------------------------------------------

        reset_url = (
            f"{os.environ.get('APP_Url')}/auth/reset-password/change"
            f"?email={quote_plus(email)}&token={raw_token}"
        )
        send_reset_email(user.email, reset_url)

        # mimic constant processing time
        while (_utcnow() - delay_start).total_seconds() < 0.75:
            pass

        return jsonify({"status": "ok"}), 200

    except Exception as exc:
        # any failure (including our explicit RuntimeError) lands here
        session.rollback()
        logger.exception("Error processing forgot‑password: %s", exc)
        return jsonify({
            "status": "error",
            "message": "Could not create reset link; please try again."
        }), 500

    finally:
        session.close()


@user_blueprint.route("/reset-password", methods=["POST"])
def reset_password():
    session = next(db_session())
    try:
        data = request.json or {}
        token = (data.get("token") or "").strip()
        # Keep backward compatibility with clients sending either key
        password = ((data.get("new_password") or data.get("password")) or "").strip()
        email = (data.get("email") or "").strip().lower()

        if not token or not password:
            return jsonify({"message": "Token and new password are required"}), 400

        token_hash = _hash_token(token)

        query = session.query(LoginUser).filter_by(
            reset_token_hash=token_hash,
            del_flg=False
        )
        if email:
            query = query.filter_by(email=email)
        user = query.first()

        # Validate token and expiry
        if (
            user is None
            or user.reset_expires_at is None
            or user.reset_expires_at.replace(tzinfo=timezone.utc) < _utcnow()
        ):
            return jsonify({"message": "Invalid or expired link"}), 400

        # Update password and clear reset fields
        user.password_hash = generate_password_hash(password)
        user.reset_token_hash = None
        user.reset_expires_at = None
        user.updated_at = _utcnow()
        session.commit()

        return jsonify({"status": "updated"}), 200

    except Exception as e:
        session.rollback()
        logger.exception(f"Error resetting password: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500
    finally:
        session.close()
  
@user_blueprint.route("/tenant_collaborator/add-details", methods=["POST"])
@jwt_required()
@authorize(roles_allowed=["admin"])
def add_collaborator_details():

    session = next(db_session())
    try:
        data = request.json or {}

        name = data.get("name")
        email = data.get("email")
        password = data.get("password")

        if not name or not email or not password:
            return jsonify({"error": "Name, email and password required"}), 400

        existing = session.query(Collaborator).filter_by(
            email=email,
            del_flg=False
        ).first()

        if existing:
            return jsonify({"error": "Email already exists"}), 400

        collaborator = Collaborator(
            tenant_id=g.tenant.tenant_id,
            name=name,
            email=email,
            phone=data.get("phone"),
            role=data.get("role", "user"),
            password_hash=generate_password_hash(password)
        )

        session.add(collaborator)
        session.commit()

        return jsonify({
            "message": "Collaborator added successfully",
            "collaborator_id": collaborator.collaborator_id
        }), 201

    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()    


@user_blueprint.route("/tenant_collaborator/update/<int:collaborator_id>", methods=["PATCH"])
@jwt_required()
@authorize(roles_allowed=["admin"])
def update_collaborator(collaborator_id):

    session = next(db_session())
    try:

        collaborator = session.query(Collaborator).filter_by(
            collaborator_id=collaborator_id,
            tenant_id=g.tenant.tenant_id,
            del_flg=False
        ).first()

        if not collaborator:
            return jsonify({"error": "Collaborator not found"}), 404

        data = request.json or {}

        restricted_fields = ["collaborator_id", "tenant_id", "created_at"]

        for key, value in data.items():
            if key == "password":
                collaborator.password_hash = generate_password_hash(value)

            elif hasattr(collaborator, key) and key not in restricted_fields:
                setattr(collaborator, key, value)

        session.commit()

        return jsonify({
            "message": "Collaborator updated successfully"
        }), 200

    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()     
        
@user_blueprint.route("/tenant_collaborator/<int:collaborator_id>", methods=["GET"])
@jwt_required()
@authorize(roles_allowed=["admin"])
def get_collaborator(collaborator_id):

    session = next(db_session())
    try:

        collaborator = session.query(Collaborator).filter_by(
            collaborator_id=collaborator_id,
            tenant_id=g.tenant.tenant_id,
            del_flg=False
        ).first()

        if not collaborator:
            return jsonify({"error": "Collaborator not found"}), 404

        return jsonify({
            "collaborator_id": collaborator.collaborator_id,
            "name": collaborator.name,
            "email": collaborator.email,
            "phone": collaborator.phone,
            "role": collaborator.role,
            "status": collaborator.status,
            "created_at": collaborator.created_at
        }), 200

    finally:
        session.close()


@user_blueprint.route("/tenant_collaborator/details", methods=["GET"])
@jwt_required()
@authorize(roles_allowed=["admin"])
def get_collaborators():

    session = next(db_session())
    try:

        collaborators = session.query(Collaborator).filter_by(
            tenant_id=g.tenant.tenant_id,
            del_flg=False
        ).all()

        result = [
            {
                "collaborator_id": c.collaborator_id,
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "role": c.role,
                "status": c.status
            }
            for c in collaborators
        ]

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()
        
@user_blueprint.route("/tenant_collaborator/delete/<int:collaborator_id>", methods=["DELETE"])
@jwt_required()
@authorize(roles_allowed=["admin"])
def delete_collaborator(collaborator_id):

    session = next(db_session())
    try:

        collaborator = session.query(Collaborator).filter_by(
            collaborator_id=collaborator_id,
            tenant_id=g.tenant.tenant_id,
            del_flg=False
        ).first()

        if not collaborator:
            return jsonify({"error": "Collaborator not found"}), 404

        collaborator.del_flg = True
        session.commit()

        return jsonify({
            "message": "Collaborator deleted successfully"
        }), 200

    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()
        
@user_blueprint.route("/tenant_collaborator/<int:collaborator_id>/status", methods=["PATCH"])
@jwt_required()
@authorize(roles_allowed=["admin"])
def update_collaborator_status(collaborator_id):

    session = next(db_session())
    try:

        collaborator = session.query(Collaborator).filter_by(
            collaborator_id=collaborator_id,
            tenant_id=g.tenant.tenant_id,
            del_flg=False
        ).first()

        if not collaborator:
            return jsonify({"error": "Collaborator not found"}), 404

        data = request.json or {}
        new_status = data.get("status")

        if not new_status:
            return jsonify({"error": "Status is required"}), 400

        new_status = new_status.strip().capitalize()
        allowed_status = ["Active", "Inactive"]

        if new_status not in allowed_status:
            return jsonify({
                "error": f"Invalid status. Allowed values: {allowed_status}"
            }), 400

        if collaborator.status == new_status:
            return jsonify({
                "message": "Status is already set",
                "status": collaborator.status
            }), 200

        collaborator.status = new_status
        session.commit()

        return jsonify({
            "message": "Collaborator status updated successfully",
            "collaborator_id": collaborator.collaborator_id,
            "new_status": collaborator.status
        }), 200

    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()
