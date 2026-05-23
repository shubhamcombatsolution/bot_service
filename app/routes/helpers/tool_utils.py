from flask_jwt_extended import get_jwt
from collections import defaultdict
from app.models import Tools, ToolAuthorization



def normalize_tool_name(name: str) -> str:
    """
    Converts:
    - Jnanic_MCP_Gmail → gmail
    - Gmail → gmail
    - GSheets → gsheets
    """
    value = (name or "").lower().replace("jnanic_mcp_", "").strip()
    return value.replace("_", "").replace("-", "").replace(" ", "")

def get_enabled_tools_for_tenant():
    """
    Returns list of enabled tool names for the current tenant.
    If none found, returns empty list.
    Does NOT raise error.
    """

    claims = get_jwt()
    tenant_id = claims.get("tenant_id")

    if not tenant_id:
        return []

    # Fetch all catalog tools
    all_tools = Tools.query.filter_by(del_flg=False).all()

    # Fetch authorized tools for tenant
    auth_tools = ToolAuthorization.query.filter_by(
        tenant_id=tenant_id,
        del_flag=False
    ).all()

    # Map normalized authorized tool names
    authorized_base_names = set()

    for auth in auth_tools:
        base_tool = normalize_tool_name(auth.tool_name)
        authorized_base_names.add(base_tool)

    enabled_tools = []

    for tool in all_tools:
        base_tool = normalize_tool_name(tool.tool_name)

        if base_tool in authorized_base_names:
            enabled_tools.append(tool.tool_name)

    return enabled_tools
