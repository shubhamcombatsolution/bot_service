from flask import request, g
from flask_jwt_extended import create_access_token
from app.models.login_user import LoginUser
from app.database.DatabaseOperationPostgreSQL import db_session
import logging

logger = logging.getLogger(__name__)

def api_key_auth_middleware():
    """Middleware to authenticate requests using an API key."""
    def middleware():
        session = next(db_session())
        try:
            api_key = request.headers.get("X-API-Key")
            if api_key:
                # Look up user by API key
                user = session.query(LoginUser).filter_by(api_key=api_key).first()
                if not user:
                    logger.warning(f"Invalid API key: {api_key}")
                    return {
                        "data": {},
                        "status": "error",
                        "message": "Invalid API key"
                    }, 401

                # Check tenant status
                from app.models.tenant import Tenant
                tenant = session.query(Tenant).filter_by(tenant_id=user.tenant_id).first()
                if not tenant or tenant.tenant_status != "Active":
                    logger.warning(f"API key used for inactive tenant: tenant_id={user.tenant_id}")
                    return {
                        "data": {},
                        "status": "error",
                        "message": "Tenant account is inactive. Contact support."
                    }, 403

                # Generate a fresh JWT token for the user
                role = "admin" if user.role == "1" else user.role
                access_token = create_access_token(
                    identity=str(user.login_id),
                    additional_claims={
                        "tenant_id": user.tenant_id,
                        "role": role
                    }
                )

                # Add an API-key JWT only when the caller did not already
                # provide an Authorization token. Public chatbot requests send
                # X-API-Key plus a validation JWT from /validate_client; that
                # validation token must reach the route unchanged.
                if not request.headers.get("Authorization"):
                    request.headers.environ["HTTP_AUTHORIZATION"] = f"Bearer {access_token}"
                logger.info(f"API key authenticated for user_id={user.login_id}, tenant_id={user.tenant_id}")
            return None  # Continue with the request
        except Exception as e:
            logger.error(f"Error in API key authentication: {str(e)}")
            return {
                "data": {},
                "status": "error",
                "message": "Internal server error during authentication"
            }, 500
        finally:
            session.close()
    return middleware

# Apply the middleware globally in your app.py
def init_api_key_middleware(app):
    app.before_request(api_key_auth_middleware())
