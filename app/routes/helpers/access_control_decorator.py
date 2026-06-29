from functools import wraps
from flask import jsonify, g
from flask_jwt_extended import get_jwt
from app.models import Tenant, LoginUser, Collaborator


# Optional: Role hierarchy (can move to config later)
ROLE_HIERARCHY = {
    "superAdmin": 100,
    "admin": 90,
    "user": 10,
 
}


def authorize(
    roles_allowed=None,
    permissions_required=None,
    min_role=None,
    user_types_allowed=None,
    allow_super_admin=True
):
    """
    Future-Proof Authorization Decorator

    Supports:
    - Role-based access
    - Role hierarchy (min_role)
    - Permission-based access (future-ready)
    - User type validation
    - Super admin override
    - Tenant & user validation
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):

            claims = get_jwt()

            tenant_id = claims.get("tenant_id")
            user_id = claims.get("user_id")
            role = claims.get("role")
            user_type = claims.get("user_type")

            # ----------------------------------
            # Super Admin Override
            # ----------------------------------
            if allow_super_admin and role == "superAdmin":
                g.tenant = None
                g.current_user = None
                g.role = role
                g.user_type = user_type
                return func(*args, **kwargs)

            if not tenant_id or not user_id:
                return jsonify({"error": "Unauthorized"}), 401

            # ----------------------------------
            # Validate Tenant
            # ----------------------------------
            tenant = Tenant.query.filter_by(
                tenant_id=tenant_id,
                del_flg=False
            ).first()

            if not tenant or tenant.tenant_status != "Active":
                return jsonify({"error": "Invalid or inactive tenant"}), 403

            # ----------------------------------
            # Validate User
            # ----------------------------------
            if user_type == "admin":
                user = LoginUser.query.filter_by(
                    login_id=user_id,
                    tenant_id=tenant_id,
                    del_flg=False
                ).first()
            else:
                user = Collaborator.query.filter_by(
                    collaborator_id=user_id,
                    tenant_id=tenant_id,
                    del_flg=False
                ).first()

                if user and user.status != "Active":
                    return jsonify({"error": "User inactive"}), 403

            if not user:
                return jsonify({"error": "User not found"}), 401

            # ----------------------------------
            # Role Exact Match Validation
            # ----------------------------------
            if roles_allowed and role not in roles_allowed:
                return jsonify({
                    "error": "Insufficient permissions",
                    "message": f"This action requires one of these roles: {roles_allowed}. Your role: '{role}'."
                }), 403

            # ----------------------------------
            # Role Hierarchy Validation
            # ----------------------------------
            if min_role:
                if ROLE_HIERARCHY.get(role, 0) < ROLE_HIERARCHY.get(min_role, 0):
                    return jsonify({"error": "Insufficient role level"}), 403

            # ----------------------------------
            # Permission Validation (Future-Ready)
            # ----------------------------------
            if permissions_required:
                user_permissions = getattr(user, "permissions", [])
                for permission in permissions_required:
                    if permission not in user_permissions:
                        return jsonify({
                            "error": f"Missing permission: {permission}"
                        }), 403

            # ----------------------------------
            # User Type Validation
            # ----------------------------------
            if user_types_allowed and user_type not in user_types_allowed:
                return jsonify({
                    "error": "Access denied for this user type"
                }), 403

            # Inject context
            g.tenant = tenant
            g.current_user = user
            g.role = role
            g.user_type = user_type

            return func(*args, **kwargs)

        return wrapper
    return decorator