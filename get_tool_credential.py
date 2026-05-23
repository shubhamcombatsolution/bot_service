"""
Helper module to fetch tool credentials from the database.
Used by workflow nodes to retrieve stored credentials for Slack, WhatsApp, etc.
"""

import json
import logging
from typing import Optional, Dict, Any
from sqlalchemy import text

from app.database.DatabaseOperationPostgreSQL import db_session

logger = logging.getLogger(__name__)


def get_tool_credential(
    tenant_id: int,
    tool_name: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch credentials for a specific tool from the database.
    
    Args:
        tenant_id: The tenant ID to fetch credentials for
        tool_name: The name of the tool (e.g., "slack", "whatsapp")
    
    Returns:
        A dict with structure:
        {
            "tenant_id": int,
            "tool_name": str,
            "credentials": {...}  // The actual credentials from token_json
        }
        
        Returns None if credentials are not found or on error.
    """
    session = None
    try:
        session = next(db_session())
        
        query = text("""
            SELECT token_json
            FROM tbl_tool_authorization
            WHERE tenant_id = :tenant_id
              AND LOWER(tool_name) = LOWER(:tool_name)
              AND del_flag = false
            ORDER BY updated_at DESC
            LIMIT 1
        """)
        
        result = session.execute(query, {
            "tenant_id": int(tenant_id),
            "tool_name": tool_name,
        }).fetchone()
        
        if not result:
            logger.debug(f"No credentials found for tenant_id={tenant_id}, tool={tool_name}")
            return None
        
        token_data = result[0]
        
        # Parse the stored JSON if it's a string
        if isinstance(token_data, dict):
            credentials_json = token_data
        else:
            try:
                credentials_json = json.loads(token_data) if token_data else {}
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON stored for tool={tool_name}, tenant_id={tenant_id}")
                return None
        
        # Return in the same structure as the REST API endpoint
        return {
            "tenant_id": int(tenant_id),
            "tool_name": tool_name,
            "credentials": credentials_json,
        }
        
    except Exception as e:
        logger.error(f"Error fetching credentials for tool={tool_name}, tenant_id={tenant_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
