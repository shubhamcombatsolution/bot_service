-- =====================================================================
-- Migration: Add Prebuilt Agents System
-- Description: Creates tables for Super Admin managed prebuilt agents
-- Author: System
-- Date: 2026-02-19
-- =====================================================================

-- =====================================================================
-- TABLE: tbl_prebuilt_agents
-- Stores agent templates managed by Super Admin (NO credentials stored)
-- =====================================================================
CREATE TABLE IF NOT EXISTS tbl_prebuilt_agents (
    prebuilt_agent_id SERIAL PRIMARY KEY,
    
    -- Agent Metadata
    agent_name VARCHAR(255) NOT NULL,
    agent_description TEXT,
    agent_role TEXT,
    agent_instructions TEXT,
    
    -- Categorization
    category VARCHAR(100),  -- e.g., 'Sales', 'Marketing', 'Support', 'HR'
    tags TEXT[],  -- Array of searchable tags
    is_featured BOOLEAN DEFAULT FALSE,
    display_order INTEGER DEFAULT 0,
    
    -- LLM Configuration
    llm_provider VARCHAR(50) NOT NULL,  -- 'openai', 'anthropic', etc.
    llm_model VARCHAR(100) NOT NULL,    -- 'gpt-4-turbo', 'claude-sonnet-4'
    temperature DECIMAL(3,2) DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 1000,
    
    -- Features & Settings
    features JSONB DEFAULT '{}'::jsonb,
    safe_ai_settings JSONB DEFAULT '{}'::jsonb,
    additional_instructions TEXT,
    examples TEXT,
    
    -- Memory Configuration
    memory_type VARCHAR(50),  -- 'short_term', 'long_term', NULL
    memory_enabled BOOLEAN DEFAULT FALSE,
    
    -- Tools Configuration (NO credentials - just requirements)
    required_tools JSONB DEFAULT '[]'::jsonb,
    -- Example: [
    --   {"tool_name": "hubspot", "action_tools": ["get_contact_by_email", "create_deal"]},
    --   {"tool_name": "gmail", "action_tools": ["send_gmail"]}
    -- ]
    
    -- Knowledge Base (templates - actual KB created on clone)
    knowledge_base_config JSONB DEFAULT '{}'::jsonb,
    
    -- Plan Restrictions
    minimum_plan_level INTEGER DEFAULT 1,  -- 1=Free, 2=Pro, 3=Team, 4=Enterprise
    
    -- Status & Visibility
    is_active BOOLEAN DEFAULT TRUE,
    is_public BOOLEAN DEFAULT TRUE,  -- If false, only visible to specific plans
    
    -- Statistics
    clone_count INTEGER DEFAULT 0,  -- How many times cloned by tenants
    average_rating DECIMAL(3,2),    -- User ratings
    
    -- Audit
    created_by INTEGER,  -- Super Admin user_id
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    del_flg BOOLEAN DEFAULT FALSE
);

-- Indexes for performance
CREATE INDEX idx_prebuilt_agents_category ON tbl_prebuilt_agents(category) WHERE del_flg = FALSE;
CREATE INDEX idx_prebuilt_agents_featured ON tbl_prebuilt_agents(is_featured) WHERE del_flg = FALSE AND is_active = TRUE;
CREATE INDEX idx_prebuilt_agents_active ON tbl_prebuilt_agents(is_active) WHERE del_flg = FALSE;
CREATE INDEX idx_prebuilt_agents_tags ON tbl_prebuilt_agents USING GIN(tags);

-- =====================================================================
-- TABLE: tbl_tenant_cloned_agents
-- Tracks which prebuilt agents have been cloned to which tenants
-- =====================================================================
CREATE TABLE IF NOT EXISTS tbl_tenant_cloned_agents (
    id SERIAL PRIMARY KEY,
    
    tenant_id INTEGER NOT NULL REFERENCES tbl_tenants(tenant_id) ON DELETE CASCADE,
    prebuilt_agent_id INTEGER NOT NULL REFERENCES tbl_prebuilt_agents(prebuilt_agent_id) ON DELETE CASCADE,
    cloned_agent_id INTEGER NOT NULL REFERENCES tbl_agents(agent_id) ON DELETE CASCADE,
    
    -- Track cloning
    cloned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- User feedback
    user_rating INTEGER CHECK (user_rating BETWEEN 1 AND 5),
    user_feedback TEXT,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,  -- User can deactivate cloned agent
    
    UNIQUE(tenant_id, prebuilt_agent_id)  -- Each tenant can clone each prebuilt agent only once
);

-- Indexes
CREATE INDEX idx_tenant_cloned_tenant ON tbl_tenant_cloned_agents(tenant_id);
CREATE INDEX idx_tenant_cloned_prebuilt ON tbl_tenant_cloned_agents(prebuilt_agent_id);
CREATE INDEX idx_tenant_cloned_agent ON tbl_tenant_cloned_agents(cloned_agent_id);

-- =====================================================================
-- TABLE: tbl_prebuilt_agent_analytics
-- Analytics for prebuilt agents (optional - for Super Admin dashboard)
-- =====================================================================
CREATE TABLE IF NOT EXISTS tbl_prebuilt_agent_analytics (
    id SERIAL PRIMARY KEY,
    
    prebuilt_agent_id INTEGER NOT NULL REFERENCES tbl_prebuilt_agents(prebuilt_agent_id) ON DELETE CASCADE,
    
    event_type VARCHAR(50) NOT NULL,  -- 'view', 'clone', 'activate', 'deactivate', 'rate'
    tenant_id INTEGER REFERENCES tbl_tenants(tenant_id) ON DELETE SET NULL,
    
    metadata JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for analytics queries
CREATE INDEX idx_prebuilt_analytics_agent ON tbl_prebuilt_agent_analytics(prebuilt_agent_id);
CREATE INDEX idx_prebuilt_analytics_event ON tbl_prebuilt_agent_analytics(event_type);
CREATE INDEX idx_prebuilt_analytics_date ON tbl_prebuilt_agent_analytics(created_at);

-- =====================================================================
-- Comments for documentation
-- =====================================================================
COMMENT ON TABLE tbl_prebuilt_agents IS 'Super Admin managed agent templates (no credentials stored)';
COMMENT ON COLUMN tbl_prebuilt_agents.required_tools IS 'JSON array of tool requirements - credentials provided by tenant on clone';
COMMENT ON COLUMN tbl_prebuilt_agents.minimum_plan_level IS '1=Free, 2=Pro, 3=Team, 4=Enterprise';

COMMENT ON TABLE tbl_tenant_cloned_agents IS 'Tracks prebuilt agents cloned to tenant accounts';
COMMENT ON TABLE tbl_prebuilt_agent_analytics IS 'Analytics and usage tracking for prebuilt agents';

-- =====================================================================
-- Sample Data (Optional - for testing)
-- =====================================================================
-- INSERT INTO tbl_prebuilt_agents (
--     agent_name, agent_description, agent_role, category, tags,
--     llm_provider, llm_model, required_tools, is_featured
-- ) VALUES (
--     'HubSpot Lead Qualifier',
--     'Automatically qualifies inbound leads from email and updates HubSpot CRM',
--     'Lead qualification specialist',
--     'Sales',
--     ARRAY['sales', 'crm', 'lead-generation', 'hubspot'],
--     'openai',
--     'gpt-4-turbo',
--     '[{"tool_name": "hubspot", "action_tools": ["get_contact_by_email", "create_deal", "update_contact"]}, {"tool_name": "gmail", "action_tools": ["read_gmail_messages", "send_gmail"]}]'::jsonb,
--     TRUE
-- );
