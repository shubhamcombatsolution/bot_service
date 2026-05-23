"""
Production-grade Wait Node with Data Mapping
CORRECTED VERSION - Ready for Production
"""

import re
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from engine.base_node import BaseNode
from logging_config import setup_logging
from engine.registry import register_node
from .utils.resolver import resolve_field

logger = setup_logging("WaitNode", level="DEBUG")


@register_node("WaitNode")
class WaitNode(BaseNode):
    """
    Wait Node with Data Mapping Support
    
    Config Example:
    {
        "webhookUrl": "http://api.com/rfq/{rfq_number}/status",
        "dataMapping": {
            "rfq_number": "gmail-trigger-1.extracted_data.rfq_number",
            "customer_email": "gmail-trigger-1.extracted_data.customer_email"
        },
        "successPath": "finalized",
        "successValue": true,
        "backoffMinutes": [1, 2, 5, 10],
        "maxRetries": 10,
        "timeoutMinutes": 120
    }
    """

    def execute(self, inputs: dict) -> dict:
        logger.info(f"⏳ WaitNode started: {self.node_id}")

        config = self.form_data or {}

        # Validate webhook URL
        webhook_template = config.get("webhookUrl")
        if not webhook_template:
            raise ValueError("❌ WaitNode requires webhookUrl")

        # Get configuration
        data_mapping = (
            config.get("dataMapping")
            or config.get("data_mapping")
            or config.get("config_parameters", {})
        )
        success_path = config.get("successPath", "finalized")
        success_value = config.get("successValue", True)
        backoff_minutes = config.get("backoffMinutes", [1, 2, 5])
        max_retries = int(config.get("maxRetries", 5))
        timeout_minutes = int(config.get("timeoutMinutes", 120))
        headers = config.get("headers", {})

        # Get execution context
        execution_id = inputs.get("execution_id")
        if not execution_id:
            raise ValueError("❌ WaitNode requires execution_id")

        # ========================================
        # 1️⃣ RESOLVE DYNAMIC VARIABLES
        # ========================================
        resolved_vars = {}
        
        if data_mapping:
            logger.info(f"🗺️ Resolving {len(data_mapping)} mapped variables")
            
            for var_name, path in data_mapping.items():
                try:
                    context = inputs.get("node_outputs") or inputs
                    value = resolve_field(
                        {
                            **inputs,
                            "node_outputs": context,
                            "workflow": inputs.get("workflow")
                        },
                        path
                    )
                    resolved_vars[var_name] = value
                    logger.debug(f"✅ Mapped: {var_name} = {value} (from {path})")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to map {var_name} from {path}: {e}")
                    resolved_vars[var_name] = None
        else:
            logger.warning("⚠️ No dataMapping/config_parameters configured. Trying direct webhook placeholder resolution.")

        # ========================================
        # 2️⃣ RESOLVE WEBHOOK URL WITH VARIABLES
        # ========================================
        webhook_url = webhook_template

        # Support both {var} and {{var}} syntax from workflow editor
        placeholders = re.findall(r'\{+\s*([^{}\s]+)\s*\}+', webhook_template)

        for placeholder in placeholders:
            value = resolved_vars.get(placeholder)

            if value is None:
                # Try direct resolution from the current context if not explicitly mapped
                try:
                    value = resolve_field(
                        {
                            **inputs,
                            "workflow": inputs.get("workflow"),
                            "node_outputs": inputs.get("node_outputs", {}),
                        },
                        placeholder,
                    )
                    if value is not None:
                        resolved_vars[placeholder] = value
                        logger.debug(f"🔄 Resolved placeholder from context: {{{placeholder}}} → {value}")
                except Exception:
                    value = None

            if value is not None:
                webhook_url = re.sub(
                    rf'\{{+\s*{re.escape(placeholder)}\s*\}}+',
                    str(value),
                    webhook_url,
                )
                logger.debug(f"🔄 Resolved: {{{placeholder}}} → {value}")
            else:
                logger.error(f"❌ Variable '{placeholder}' could not be resolved")
                raise ValueError(
                    f"Variable '{placeholder}' could not be resolved from wait node inputs or config_parameters"
                )

        logger.info(f"🔗 Resolved webhook URL: {webhook_url}")

        # ========================================
        # 3️⃣ COMPUTE TIMING
        # ========================================
        now = datetime.utcnow()
        next_poll_at = now + timedelta(minutes=backoff_minutes[0])
        timeout_at = now + timedelta(minutes=timeout_minutes)

        logger.info(
            f"⏰ WaitNode scheduled | "
            f"first_poll={next_poll_at.isoformat()}, "
            f"timeout={timeout_at.isoformat()}"
        )

        # ========================================
        # 4️⃣ RETURN WAITING STATUS
        # ========================================
        return {
            "status": "waiting",
            "node_id": self.node_id,
            "execution_id": execution_id,

            "config": {
                "webhook_url": webhook_url,  # ✅ Resolved URL
                "success_path": success_path,
                "success_value": success_value,
                "backoff_minutes": backoff_minutes,
                "max_retries": max_retries,
                "timeout_at": timeout_at.isoformat(),
                "headers": headers
            },

            "state": {
                "retry_count": 0,
                "next_poll_at": next_poll_at.isoformat(),
                "created_at": now.isoformat()
            },
            
            # ✅ NEW: Store mapped data for resume
            "mapped_data": resolved_vars,
            
            # ✅ NEW: Extract tracking key
            "tracking_key": self._extract_tracking_key(resolved_vars),
            "tracking_type": self._detect_tracking_type(resolved_vars)
        }

    def _extract_tracking_key(self, resolved_vars: Dict[str, Any]) -> Optional[str]:
        """Extract tracking key from resolved variables"""
        tracking_fields = [
            "rfq_number", "rfq_no", "rfq_id",
            "order_number", "order_id",
            "ticket_number", "ticket_id"
        ]
        
        for field in tracking_fields:
            if field in resolved_vars and resolved_vars[field]:
                return str(resolved_vars[field])
        
        # Fallback: first non-null value
        for value in resolved_vars.values():
            if value is not None:
                return str(value)
        
        return None

    def _detect_tracking_type(self, resolved_vars: Dict[str, Any]) -> str:
        """Detect tracking type from variable names"""
        keys_str = " ".join(resolved_vars.keys()).lower()
        
        if "rfq" in keys_str:
            return "rfq"
        elif "order" in keys_str:
            return "order"
        elif "ticket" in keys_str:
            return "ticket"
        else:
            return "custom"




class WaitNodePoller:
    """
    Handles polling logic for Wait Nodes
    Used by trigger service background loop
    """

    @staticmethod
    def poll_webhook(wait_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Poll webhook endpoint and check success condition
        
        Args:
            wait_state: Current wait node state from database
            
        Returns:
            {
                "success": bool,
                "should_retry": bool,
                "response_data": dict,
                "error": str (optional)
            }
        """
        config = wait_state.get("config", {})
        state = wait_state.get("state", {})
        
        webhook_url = config["webhook_url"]
        success_path = config["success_path"]
        success_value = config.get("success_value", True)
        headers = config.get("headers", {})
        retry_count = state.get("retry_count", 0)
        max_retries = config.get("max_retries", 5)

        logger.info(
            f"🔍 Polling webhook: url={webhook_url}, "
            f"retry={retry_count}/{max_retries}"
        )

        try:
            # Make HTTP request with timeout
            response = requests.get(
                webhook_url,
                headers=headers,
                timeout=30  # 30 second timeout
            )

            # Log response
            logger.debug(
                f"📥 Webhook response: status={response.status_code}, "
                f"body={response.text[:200]}"
            )

            # Check HTTP status
            if response.status_code != 200:
                logger.warning(
                    f"⚠️ Webhook returned {response.status_code}: {response.text[:100]}"
                )
                return {
                    "success": False,
                    "should_retry": retry_count < max_retries,
                    "error": f"HTTP {response.status_code}"
                }

            # Parse JSON response
            try:
                response_data = response.json()
            except ValueError as e:
                logger.error(f"❌ Invalid JSON response: {e}")
                return {
                    "success": False,
                    "should_retry": retry_count < max_retries,
                    "error": "Invalid JSON response"
                }

            # Extract value at success_path
            actual_value = WaitNodePoller._extract_nested_value(
                response_data,
                success_path
            )

            # Check if success condition is met
            is_success = actual_value == success_value

            logger.info(
                f"✅ Success check: path={success_path}, "
                f"expected={success_value}, actual={actual_value}, "
                f"match={is_success}"
            )

            if is_success:
                # SUCCESS - optionally fetch additional data
                additional_data = None
                fetch_url = config.get("fetch_url_on_success")
                
                if fetch_url:
                    logger.info(f"📡 Fetching additional data from: {fetch_url}")
                    try:
                        fetch_resp = requests.get(fetch_url, headers=headers, timeout=30)
                        if fetch_resp.status_code == 200:
                            additional_data = fetch_resp.json()
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to fetch additional data: {e}")

                return {
                    "success": True,
                    "should_retry": False,
                    "response_data": response_data,
                    "additional_data": additional_data
                }
            else:
                # NOT SUCCESS YET - should retry
                return {
                    "success": False,
                    "should_retry": retry_count < max_retries,
                    "response_data": response_data,
                    "error": f"Condition not met: {success_path}={actual_value}"
                }

        except requests.exceptions.Timeout:
            logger.error(f"⏱️ Webhook request timeout: {webhook_url}")
            return {
                "success": False,
                "should_retry": retry_count < max_retries,
                "error": "Request timeout"
            }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Webhook request failed: {e}")
            return {
                "success": False,
                "should_retry": retry_count < max_retries,
                "error": f"Network error: {str(e)}"
            }
        
        except Exception as e:
            logger.exception(f"❌ Unexpected error polling webhook: {e}")
            return {
                "success": False,
                "should_retry": retry_count < max_retries,
                "error": f"Unexpected error: {str(e)}"
            }

    @staticmethod
    def _extract_nested_value(data: Dict, path: str) -> Any:
        """
        Extract nested value from dict using dot notation
        
        Examples:
            data = {"status": "completed"}
            path = "status" -> "completed"
            
            data = {"data": {"status": "completed"}}
            path = "data.status" -> "completed"
        """
        keys = path.split(".")
        value = data
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
                
        return value

    @staticmethod
    def calculate_next_poll_time(
        retry_count: int,
        backoff_minutes: list
    ) -> datetime:
        """
        Calculate next poll time using backoff strategy
        
        Args:
            retry_count: Current retry attempt (0-indexed)
            backoff_minutes: List of backoff intervals
            
        Returns:
            Next poll datetime
        """
        # Use last backoff value if we exceed list length
        index = min(retry_count, len(backoff_minutes) - 1)
        delay_minutes = backoff_minutes[index]
        
        next_poll = datetime.utcnow() + timedelta(minutes=delay_minutes)
        
        logger.debug(
            f"⏰ Next poll calculated: retry={retry_count}, "
            f"delay={delay_minutes}min, next={next_poll.isoformat()}"
        )
        
        return next_poll