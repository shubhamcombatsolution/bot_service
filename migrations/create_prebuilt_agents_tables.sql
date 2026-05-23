-- ============================================================================
-- PREBUILT AGENTS SYSTEM - DATABASE SCHEMA
-- ============================================================================
-- Purpose: Store super admin imported agents separately from tenant agents
-- No credentials stored at this level - only structure and requirements
-- ============================================================================

-- ────────────────────────────────────────────────────────────────────────────
-- TABLE 1: tbl_prebuilt_agents
-- Stores the agent configuration imported by super admin
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tbl_prebuilt_agents (
    prebuilt_agent_id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    agent_description TEXT,
    agent_role TEXT,
    agent_instructions TEXT,
    additional_instructions TEXT,
    
    -- LLM config (stored as strings, not FKs - generic across all tenants)
    llm_provider VARCHAR(50) NOT NULL,  -- "openai", "anthropic", etc.
    llm_model VARCHAR(100) NOT NULL,    -- "gpt-4-turbo", "claude-sonnet-4"
    llm_temperature FLOAT DEFAULT 0.7,
    llm_max_tokens INTEGER,
    
    -- Memory settings
    memory_plugin VARCHAR(50),  -- "short_term", "long_term", null
    
    -- Features & Safety
    features JSONB DEFAULT '{}',
    safe_ai_settings JSONB DEFAULT '{}',
    
    -- Examples
    examples TEXT,
    
    -- Metadata
    category VARCHAR(50),  -- "sales", "support", "marketing", etc.
    tags TEXT[],  -- Array of tags for search
    icon_url VARCHAR(255),
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_featured BOOLEAN DEFAULT FALSE,
    
    -- Audit
    created_by INTEGER,  -- super admin user_id
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    del_flg BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_prebuilt_agents_active ON tbl_prebuilt_agents(is_active, del_flg);
CREATE INDEX idx_prebuilt_agents_category ON tbl_prebuilt_agents(category);
CREATE INDEX idx_prebuilt_agents_featured ON tbl_prebuilt_agents(is_featured);

-- ────────────────────────────────────────────────────────────────────────────
-- TABLE 2: tbl_prebuilt_agent_tools
-- Defines which tools are required by each prebuilt agent
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tbl_prebuilt_agent_tools (
    id SERIAL PRIMARY KEY,
    prebuilt_agent_id INTEGER NOT NULL REFERENCES tbl_prebuilt_agents(prebuilt_agent_id) ON DELETE CASCADE,
    
    -- Tool info
    tool_name VARCHAR(50) NOT NULL,  -- "gmail", "hubspot", "system", etc.
    tool_type VARCHAR(20) DEFAULT 'local',  -- "local" or "mcp"
    action_tools JSONB DEFAULT '[]',  -- Array of action names
    
    -- MCP specific (only if tool_type='mcp')
    mcp_url VARCHAR(255),
    
    -- Requirement level
    is_required BOOLEAN DEFAULT TRUE,  -- If false, agent works without this tool
    
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(prebuilt_agent_id, tool_name)
);

CREATE INDEX idx_prebuilt_tools_agent ON tbl_prebuilt_agent_tools(prebuilt_agent_id);
CREATE INDEX idx_prebuilt_tools_name ON tbl_prebuilt_agent_tools(tool_name);

-- ────────────────────────────────────────────────────────────────────────────
-- TABLE 3: tbl_tenant_prebuilt_agents
-- Tracks which tenants have access to which prebuilt agents
-- Links to actual cloned agent instance once activated
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tbl_tenant_prebuilt_agents (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tbl_tenants(tenant_id) ON DELETE CASCADE,
    prebuilt_agent_id INTEGER NOT NULL REFERENCES tbl_prebuilt_agents(prebuilt_agent_id) ON DELETE CASCADE,
    
    -- Cloned agent reference (null until user activates)
    agent_id INTEGER REFERENCES tbl_agents(agent_id) ON DELETE SET NULL,
    
    -- Status tracking
    status VARCHAR(20) DEFAULT 'pending_tools',  -- pending_tools, ready, active, inactive
    
    -- Missing tools (updated dynamically)
    missing_tools JSONB DEFAULT '[]',  -- Array of tool names user needs to connect
    
    -- Audit
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP,
    last_checked_at TIMESTAMP,
    
    UNIQUE(tenant_id, prebuilt_agent_id)
);

CREATE INDEX idx_tenant_prebuilt_tenant ON tbl_tenant_prebuilt_agents(tenant_id);
CREATE INDEX idx_tenant_prebuilt_status ON tbl_tenant_prebuilt_agents(status);
CREATE INDEX idx_tenant_prebuilt_agent_id ON tbl_tenant_prebuilt_agents(agent_id);

-- ────────────────────────────────────────────────────────────────────────────
-- TABLE 4: tbl_prebuilt_agent_usage_stats (Optional - for analytics)
-- Track usage of prebuilt agents across all tenants
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tbl_prebuilt_agent_usage_stats (
    id SERIAL PRIMARY KEY,
    prebuilt_agent_id INTEGER NOT NULL REFERENCES tbl_prebuilt_agents(prebuilt_agent_id) ON DELETE CASCADE,
    
    -- Metrics
    total_activations INTEGER DEFAULT 0,
    total_messages INTEGER DEFAULT 0,
    active_tenants INTEGER DEFAULT 0,
    average_rating FLOAT,
    
    -- Last updated
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(prebuilt_agent_id)
);

-- ────────────────────────────────────────────────────────────────────────────
-- SEED DATA: Example prebuilt agents
-- ────────────────────────────────────────────────────────────────────────────

-- Example 1: Email Assistant (requires Gmail)
INSERT INTO tbl_prebuilt_agents (
    agent_name, agent_description, agent_role, agent_instructions,
    llm_provider, llm_model, llm_temperature,
    memory_plugin, category, tags, is_featured
) VALUES (
    'Email Assistant',
    'AI assistant that reads, drafts, and sends email replies automatically',
    'Professional email assistant with access to Gmail',
    'Read incoming emails, analyze content, draft appropriate responses, and send replies. Always maintain a professional tone.',
    'openai', 'gpt-4-turbo', 0.5,
    'short_term', 'productivity', ARRAY['email', 'gmail', 'communication'], TRUE
) ON CONFLICT DO NOTHING;

-- Tools for Email Assistant
INSERT INTO tbl_prebuilt_agent_tools (prebuilt_agent_id, tool_name, tool_type, action_tools, is_required)
SELECT 
    pa.prebuilt_agent_id,
    'gmail',
    'local',
    '["list_gmail_messages", "read_gmail_messages", "draft_gmail", "send_gmail", "mark_as_read"]'::jsonb,
    TRUE
FROM tbl_prebuilt_agents pa
WHERE pa.agent_name = 'Email Assistant'
ON CONFLICT (prebuilt_agent_id, tool_name) DO NOTHING;

INSERT INTO tbl_prebuilt_agent_tools (prebuilt_agent_id, tool_name, tool_type, action_tools, is_required)
SELECT 
    pa.prebuilt_agent_id,
    'system',
    'local',
    '["get_datetime", "parse_json"]'::jsonb,
    FALSE
FROM tbl_prebuilt_agents pa
WHERE pa.agent_name = 'Email Assistant'
ON CONFLICT (prebuilt_agent_id, tool_name) DO NOTHING;

-- Example 2: CRM Sales Assistant (requires HubSpot)
INSERT INTO tbl_prebuilt_agents (
    agent_name, agent_description, agent_role, agent_instructions,
    llm_provider, llm_model, llm_temperature,
    memory_plugin, category, tags, is_featured
) VALUES (
    'HubSpot Sales Assistant',
    'Manages leads, tracks deals, and updates contact information in HubSpot CRM',
    'Sales assistant with HubSpot CRM access',
    'Help sales team by looking up contacts, creating deals, updating pipeline stages, and logging notes in HubSpot.',
    'openai', 'gpt-4-turbo', 0.4,
    'short_term', 'sales', ARRAY['crm', 'hubspot', 'sales'], TRUE
) ON CONFLICT DO NOTHING;

-- Tools for HubSpot Sales Assistant
INSERT INTO tbl_prebuilt_agent_tools (prebuilt_agent_id, tool_name, tool_type, action_tools, is_required)
SELECT 
    pa.prebuilt_agent_id,
    'hubspot',
    'local',
    '["get_contact_by_email", "create_contact", "update_contact", "create_deal", "update_deal", "create_note", "search"]'::jsonb,
    TRUE
FROM tbl_prebuilt_agents pa
WHERE pa.agent_name = 'HubSpot Sales Assistant'
ON CONFLICT (prebuilt_agent_id, tool_name) DO NOTHING;

COMMENT ON TABLE tbl_prebuilt_agents IS 'Stores prebuilt agents imported by super admin - no tenant-specific data or credentials';
COMMENT ON TABLE tbl_prebuilt_agent_tools IS 'Defines tool requirements for prebuilt agents - users must have these tools authorized';
COMMENT ON TABLE tbl_tenant_prebuilt_agents IS 'Maps which tenants have access to which prebuilt agents - tracks activation status';
EOF
echo "✅ SQL migration file created"