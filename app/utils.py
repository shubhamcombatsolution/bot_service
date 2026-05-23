from datetime import datetime, timezone, timedelta
import logging
from typing import Tuple, Dict, Any, Optional
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.models import Tenant, TenantSubscription, BotPlan, Agent
# If your models use different names, replace Agent and custome_bot accordingly.
from app.models.custome_bot import CustomBot  # Use actual model class name
from dateutil.relativedelta import relativedelta
logger = logging.getLogger(__name__)

# Configurable grace period (in days)
GRACE_PERIOD_DAYS = 0  # set to >0 if you want a grace period after expiry


def _now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert a naive datetime to timezone-aware UTC.
    If dt is already timezone-aware, convert to UTC.
    If dt is None, return None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_valid_subscription(session: Session, tenant_id: int) -> Tuple[bool, Dict[str, Any]]:
    """
    Check if the tenant has a valid, active subscription.
    """
    try:
        subscription = session.query(TenantSubscription).filter_by(
            tenant_id=tenant_id,
            subscription_status='active',
            del_flg=False
        ).first()

        if not subscription:
            return False, {"error_code": "NO_ACTIVE_SUBSCRIPTION", "message": "No active subscription found."}

        if subscription.subscription_end:
            expiry_with_grace = _ensure_aware(subscription.subscription_end) + timedelta(days=GRACE_PERIOD_DAYS)
            if expiry_with_grace < _now():
                return False, {"error_code": "SUBSCRIPTION_EXPIRED", "message": "Subscription has expired."}

        plan = session.query(BotPlan).filter_by(
            plan_id=subscription.plan_id,
            plan_status=True,
            del_flg=False
        ).first()

        if not plan:
            return False, {"error_code": "PLAN_NOT_FOUND", "message": "Associated plan not found."}

        return True, {"message": "Valid subscription found.", "subscription": subscription, "plan": plan}

    except SQLAlchemyError as e:
        logger.exception(f"DB error in is_valid_subscription({tenant_id}): {e}")
        return False, {"error_code": "DATABASE_ERROR", "message": "Database error while checking subscription."}


def validate_full_subscription_status(session: Session, tenant_id: int) -> Tuple[bool, Dict[str, Any]]:
    """
    Validate active subscription and enforce limits for bots, agents, and messages.
    Returns (success: bool, result: dict)
    """
    try:
        is_valid, result = is_valid_subscription(session, tenant_id)
        if not is_valid:
            return False, result

        subscription: TenantSubscription = result["subscription"]
        plan: BotPlan = result["plan"]

        # Current usage
        bot_count = session.query(CustomBot).filter_by(tenant_id=tenant_id).count()
        agent_count = session.query(Agent).filter_by(tenant_id=tenant_id).count()

        # Allowed limits (default to plan, fallback to 0)
        remaining_bots = int(subscription.remaining_bots or plan.no_bot or 0)
        remaining_agents = int(subscription.remaining_agent or plan.no_agent or 0)
        remaining_msgs = int(subscription.remaining_msg or 0)
        total_msgs = int(subscription.total_plan_msg or plan.plan_messages or 0)
        overage_limit = int(plan.overage_limit or 0)

        # Validation
        if bot_count > remaining_bots:
            return False, {
                "error_code": "BOT_LIMIT_EXCEEDED",
                "message": f"Bots ({bot_count}) exceed allowed ({remaining_bots}).",
                "usage": {"bots_used": bot_count, "bots_allowed": remaining_bots}
            }

        if agent_count > remaining_agents:
            return False, {
                "error_code": "AGENT_LIMIT_EXCEEDED",
                "message": f"Agents ({agent_count}) exceed allowed ({remaining_agents}).",
                "usage": {"agents_used": agent_count, "agents_allowed": remaining_agents}
            }

        if remaining_msgs <= 0:
            deficit = abs(remaining_msgs)
            if overage_limit <= 0 or deficit > overage_limit:
                return False, {
                    "error_code": "MESSAGE_LIMIT_EXCEEDED",
                    "message": "Messages exhausted and overage exceeded.",
                    "usage": {
                        "messages_used": total_msgs,
                        "messages_allowed": total_msgs,
                        "overage_limit": overage_limit
                    }
                }

        return True, {
            "message": "Subscription within limits.",
            "usage": {
                "bots_used": bot_count,
                "bots_allowed": remaining_bots,
                "agents_used": agent_count,
                "agents_allowed": remaining_agents,
                "messages_remaining": remaining_msgs,
                "messages_total": total_msgs,
                "overage_limit": overage_limit
            }
        }

    except SQLAlchemyError as e:
        logger.exception(f"DB error in validate_full_subscription_status({tenant_id}): {e}")
        return False, {
            "error_code": "DATABASE_ERROR",
            "message": "Database error validating subscription."
        }


# def check_create_bot(session: Session, tenant_id: int) -> Tuple[bool, Dict[str, Any]]:
#     """Check if tenant can create a new bot."""
#     try:
#         tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
#         if not tenant:
#             return False, {"error_code": "TENANT_NOT_FOUND", "message": "Tenant not found."}

#         plan = session.query(BotPlan).filter_by(plan_id=tenant.tenant_plan_id).first()
#         if not plan:
#             return False, {"error_code": "PLAN_NOT_FOUND", "message": "Plan not found."}

#         bot_count = session.query(CustomBot).filter_by(tenant_id=tenant_id).count()
#         max_bots = getattr(plan, "no_bot", None) or getattr(plan, "plan_max_bots", None)

#         if max_bots and bot_count >= int(max_bots):
#             return False, {"error_code": "BOT_LIMIT_REACHED", "message": f"Bot limit {max_bots} reached."}

#         return True, {"message": "Bot creation allowed."}

#     except SQLAlchemyError as e:
#         logger.exception(f"DB error in check_create_bot({tenant_id}): {e}")
#         return False, {"error_code": "DATABASE_ERROR", "message": "Database error."}

def check_create_bot(session: Session, tenant_id: int) -> Tuple[bool, Dict[str, Any]]:
    """Check if tenant can create a new bot based on active subscription plan."""
    try:
        # get active subscription
        subscription = (
            session.query(TenantSubscription)
            .filter_by(tenant_id=tenant_id, subscription_status="active", del_flg=False)
            .first()
        )
        if not subscription:
            return False, {
                "error_code": "NO_ACTIVE_SUBSCRIPTION",
                "message": "No active subscription found for tenant."
            }

        # get plan from subscription
        plan = session.query(BotPlan).filter_by(plan_id=subscription.plan_id, del_flg=False).first()
        if not plan:
            return False, {"error_code": "PLAN_NOT_FOUND", "message": "Plan not found."}

        # count existing bots
        bot_count = session.query(CustomBot).filter_by(
            tenant_id=tenant_id, bot_status='Created'
        ).count()

        max_bots = getattr(plan, "no_bot", None) or getattr(plan, "plan_max_bots", None)

        if max_bots is not None and int(bot_count) >= int(max_bots):
            return False, {
                "error_code": "BOT_LIMIT_REACHED",
                "message": f"Bot limit of {max_bots} reached."
            }

        return True, {"message": "Bot creation allowed."}

    except SQLAlchemyError as e:
        logger.exception(f"DB error in check_create_bot({tenant_id}): {e}")
        return False, {"error_code": "DATABASE_ERROR", "message": "Database error."}


def can_send_message(session: Session, tenant_id: int, message_count: int = 1) -> Tuple[bool, Dict[str, Any]]:
    """Check if tenant can send message_count messages, considering overage."""
    try:
        if message_count <= 0:
            return False, {
                "error_code": "INVALID_PARAMETER",
                "message": "message_count must be > 0."
            }

        is_valid, result = is_valid_subscription(session, tenant_id)
        if not is_valid:
            return False, result

        subscription: TenantSubscription = result["subscription"]
        plan: BotPlan = result["plan"]

        # Ensure end date is valid
        if subscription.subscription_end:
            expiry_with_grace = _ensure_aware(subscription.subscription_end) + timedelta(days=GRACE_PERIOD_DAYS)
            if expiry_with_grace < _now():
                return False, {
                    "error_code": "SUBSCRIPTION_EXPIRED",
                    "message": "Subscription has expired."
                }

        remaining = int(subscription.remaining_msg) if subscription.remaining_msg is not None else 0
        overage_limit = int(plan.overage_limit) if plan.overage_limit is not None else 0

        if remaining >= message_count:
            return True, {
                "message": "Enough remaining messages.",
                "remaining_msg": remaining,
                "allowed": message_count
            }

        # Check if overage can cover the deficit
        deficit = message_count - remaining
        if overage_limit > 0 and deficit <= overage_limit:
            return True, {
                "message": "Allowed using overage.",
                "remaining_msg": remaining - message_count,  # may go negative
                "overage_used": deficit,
                "allowed": message_count
            }

        return False, {
            "error_code": "INSUFFICIENT_MESSAGES",
            "message": "Not enough messages.",
            "remaining_msg": remaining,
            "requested": message_count
        }

    except SQLAlchemyError as e:
        logger.exception(f"DB error in can_send_message({tenant_id}): {e}")
        return False, {
            "error_code": "DATABASE_ERROR",
            "message": "Database error while checking message allowance."
        }


def update_remaining_messages(session: Session, tenant_id: int, message_count: int = 1) -> Tuple[bool, Dict[str, Any]]:
    """Deduct messages safely and handle overage."""
    try:
        if message_count <= 0:
            return False, {"error_code": "INVALID_PARAMETER", "message": "message_count must be > 0."}

        is_valid, result = is_valid_subscription(session, tenant_id)
        if not is_valid:
            return False, result

        subscription = session.query(TenantSubscription).filter_by(
            tenant_id=tenant_id,
            subscription_status='active',
            del_flg=False
        ).with_for_update().first()

        if not subscription:
            return False, {"error_code": "SUBSCRIPTION_NOT_FOUND", "message": "Subscription not found."}

        plan = session.query(BotPlan).filter_by(plan_id=subscription.plan_id, del_flg=False).first()
        if not plan:
            return False, {"error_code": "PLAN_NOT_FOUND", "message": "Plan not found."}

        current_remaining = int(subscription.remaining_msg) if subscription.remaining_msg is not None else 0
        overage_limit = int(plan.overage_limit) if plan.overage_limit is not None else 0

        if current_remaining >= message_count:
            subscription.remaining_msg = current_remaining - message_count
            session.commit()
            return True, {"message": "Messages deducted.", "remaining_msg": subscription.remaining_msg}

        deficit = message_count - current_remaining
        if overage_limit <= 0 or deficit > overage_limit:
            return False, {"error_code": "OVERAGE_EXCEEDED", "message": "Overage exceeded or not allowed."}

        subscription.remaining_msg = current_remaining - message_count
        session.commit()
        return True, {"message": "Messages deducted with overage.", "remaining_msg": subscription.remaining_msg}

    except SQLAlchemyError as e:
        logger.exception(f"DB error in update_remaining_messages({tenant_id}): {e}")
        try:
            session.rollback()
        except Exception:
            logger.exception("Rollback failed after DB error.")
        return False, {"error_code": "DATABASE_ERROR", "message": "Database error."}


def get_basic_plan(session):
    """Fetch the basic plan dynamically (prefer price=0, fallback to name)."""
    # 1. Try free plan (price = 0)
    plan = session.query(BotPlan).filter(
        BotPlan.plan_price == 0,
        BotPlan.plan_status.is_(True)         # ✅ if True = active
    ).first()
    if plan:
        return plan

    # 2. Fallback: plan name "Basic Plan" (case-insensitive)
    return session.query(BotPlan).filter(
        BotPlan.plan_name.ilike("basic plan"),
        BotPlan.plan_status.is_(True) 
    ).first()


# def add_free_subscription(session,tenant_id):
#     session = next(db_session())
#     try:
#         tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
#         plan = get_basic_plan(session)

#         if not tenant or not plan:
#             return jsonify({
#                 "data": {},
#                 "message": "Invalid tenant_id or no active basic plan found",
#                 "status": "error"
#             }), 400

#         # subscription start = now, end = one month later
#         subscription_start = datetime.utcnow()
#         subscription_end = subscription_start + relativedelta(months=1)

#         subscription = TenantSubscription(
#             tenant_id=tenant.tenant_id,
#             plan_id=plan.plan_id,   # ✅ use actual plan_id dynamically
#             subscription_start=subscription_start,
#             subscription_end=subscription_end,
#             auto_renewal=False,
#             remaining_msg=plan.plan_messages or 100,   # ✅ fallback if field missing
#             total_plan_msg=plan.plan_messages or 100,  # ✅ use plan’s quota if available
#             subscription_status="active"
#         )

#         session.add(subscription)
#         session.commit()

#         return jsonify({
#             "data": {
#                 "subscription_id": subscription.subscription_id,
#                 "tenant_id": subscription.tenant_id,
#                 "plan_id": subscription.plan_id,
#                 "subscription_start": subscription.subscription_start,
#                 "subscription_end": subscription.subscription_end,
#                 "subscription_status": subscription.subscription_status
#             },
#             "message": "Tenant Subscription created successfully",
#             "status": "success"
#         }), 201

#     except Exception as e:
#         session.rollback()
#         logger.error(f"Error creating subscription: {e}")
#         return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
#     finally:
#         session.close()
#     """Check if tenant can create a new agent based on active subscription plan."""
#     try:
#         # get active subscription
#         subscription = (
#             session.query(TenantSubscription)
#             .filter_by(tenant_id=tenant_id, subscription_status="active", del_flg=False)
#             .first()
#         )
#         if not subscription:
#             return False, {
#                 "error_code": "NO_ACTIVE_SUBSCRIPTION",
#                 "message": "No active subscription found for tenant."
#             }

#         # get plan from subscription
#         plan = session.query(BotPlan).filter_by(plan_id=subscription.plan_id, del_flg=False).first()
#         if not plan:
#             return False, {"error_code": "PLAN_NOT_FOUND", "message": "Plan not found."}

#         # count existing agents
#         agent_count = session.query(Agent).filter_by(tenant_id=tenant_id, del_flg=False).count()
#         max_agents = getattr(plan, "no_agent", None) or getattr(plan, "plan_max_agents", None)

#         if max_agents and agent_count >= int(max_agents):
#             return False, {
#                 "error_code": "AGENT_LIMIT_REACHED",
#                 "message": f"Agent limit {max_agents} reached."
#             }

#         return True, {"message": "Agent creation allowed."}

#     except SQLAlchemyError as e:
#         logger.exception(f"DB error in check_create_agent({tenant_id}): {e}")
#         return False, {"error_code": "DATABASE_ERROR", "message": "Database error."}


def add_free_subscription(session, tenant_id):
    """Create a free/basic subscription for the given tenant_id."""
    try:
        tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
        plan = get_basic_plan(session)   # your helper to fetch "basic/free" plan

        if not tenant or not plan:
            logger.error("Invalid tenant_id or no active basic plan found")
            return None

        # subscription start = now, end = one month later
        subscription_start = datetime.utcnow()
        subscription_end = subscription_start + relativedelta(months=1)

        subscription = TenantSubscription(
            tenant_id=tenant.tenant_id,
            plan_id=plan.plan_id,
            subscription_start=subscription_start,
            subscription_end=subscription_end,
            auto_renewal=False,
            remaining_msg=plan.plan_messages or 100,
            total_plan_msg=plan.plan_messages or 100,
            remaining_bots=plan.no_bot or 1,
            remaining_agent=plan.no_agent or 1,
            subscription_status="active",
            del_flg=False
        )

        session.add(subscription)
        # ❌ don’t commit here, caller (google_login) will commit
        return subscription

    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        raise
    

def check_create_agent(session: Session, tenant_id: int) -> Tuple[bool, Dict[str, Any]]:
    """Check if tenant can create a new agent based on active subscription plan."""
    try:
        # get active subscription
        subscription = (
            session.query(TenantSubscription)
            .filter_by(tenant_id=tenant_id, subscription_status="active", del_flg=False)
            .first()
        )
        if not subscription:
            return False, {
                "error_code": "NO_ACTIVE_SUBSCRIPTION",
                "message": "No active subscription found for tenant."
            }

        # get plan from subscription
        plan = session.query(BotPlan).filter_by(plan_id=subscription.plan_id, del_flg=False).first()
        if not plan:
            return False, {"error_code": "PLAN_NOT_FOUND", "message": "Plan not found."}

        # count existing agents
        agent_count = session.query(Agent).filter_by(tenant_id=tenant_id, del_flg=False).count()
        max_agents = getattr(plan, "no_agent", None) or getattr(plan, "plan_max_agents", None)

        if max_agents and agent_count >= int(max_agents):
            return False, {
                "error_code": "AGENT_LIMIT_REACHED",
                "message": f"Agent Limit {max_agents} Reached."
            }

        return True, {"message": "Agent creation allowed."}

    except SQLAlchemyError as e:
        logger.exception(f"DB error in check_create_agent({tenant_id}): {e}")
        return False, {"error_code": "DATABASE_ERROR", "message": "Database error."}
# def check_create_agent(session: Session, tenant_id: int) -> Tuple[bool, Dict[str, Any]]:
#     """Check if tenant can create a new Agent."""
#     try:
#         tenant = session.query(Tenant).filter_by(tenant_id=tenant_id).first()
#         if not tenant:
#             return False, {"error_code": "TENANT_NOT_FOUND", "message": "Tenant not found."}

#         plan = session.query(BotPlan).filter_by(plan_id=tenant.tenant_plan_id).first()
#         if not plan:
#             return False, {"error_code": "PLAN_NOT_FOUND", "message": "Plan not found."}

#         agent_count = session.query(Agent).filter_by(tenant_id=tenant_id, del_flg=False).count()
#         max_agents = getattr(plan, "no_agent", None) or getattr(plan, "plan_max_agents", None)

#         if max_agents and agent_count >= int(max_agents):
#             return False, {"error_code": "AGENT_LIMIT_REACHED", "message": f"Agent limit {max_agents} reached."}

#         return True, {"message": "Agent creation allowed."}

#     except SQLAlchemyError as e:
#         logger.exception(f"DB error in check_create_agent({tenant_id}): {e}")
#         return False, {"error_code": "DATABASE_ERROR", "message": "Database error."}