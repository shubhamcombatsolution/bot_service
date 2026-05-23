-- =============================================================================
-- BBA Initial Seed Data SQL Script
-- =============================================================================
-- This script seeds the initial data required for the BBA platform:
-- 1. SuperAdmin user (default password: Admin@123)
-- 2. Base LLM Providers (36 providers)
-- 3. Tools (5 tools)
--
-- Usage: 
--   docker-compose exec -T postgres psql -U postgres -d db_botbuilder -f /path/to/seed_data.sql
--   OR
--   Copy and paste into psql after connecting to the database
--
-- IMPORTANT: Change the superadmin password after first login!
-- =============================================================================

-- Start transaction
BEGIN;

-- =============================================================================
-- 1. SUPERADMIN USER
-- =============================================================================
-- Default credentials: superadmin@jnanic.com / Admin@123
-- Password hash generated using: generate_password_hash("Admin@123", method="pbkdf2:sha256")

INSERT INTO tbl_superadmin (
    superadmin_username, 
    superadmin_email, 
    superadmin_password,
    created_at,
    updated_at,
    del_flg
) VALUES (
    'superadmin',
    'superadmin@jnanic.com',
    'pbkdf2:sha256:1000000$YsN3JnFr5JDU3x8S$aea7bafc34147856a8a8b0edf485a84c190429f51837b8dfd238f62331fcc05d',
    NOW(),
    NOW(),
    FALSE
) ON CONFLICT (superadmin_email) DO NOTHING;

-- =============================================================================
-- 2. BASE LLM PROVIDERS
-- =============================================================================
-- These are the available LLM providers and models that tenants can use

INSERT INTO tbl_basellm (base_provider, base_model_name, base_model_type, created_at, del_flg) VALUES
-- OpenAI Models
('OpenAI', 'GPT-4o', 'Text', NOW(), FALSE),
('OpenAI', 'GPT-4o', 'Vision', NOW(), FALSE),
('OpenAI', 'GPT-4o', 'Audio', NOW(), FALSE),
('OpenAI', 'GPT-4-turbo', 'Text', NOW(), FALSE),
('OpenAI', 'GPT-4-turbo', 'Vision', NOW(), FALSE),
('OpenAI', 'GPT-4', 'Vision', NOW(), FALSE),
('OpenAI', 'GPT-4', 'Text', NOW(), FALSE),
('OpenAI', 'GPT-3.5-turbo', 'Text', NOW(), FALSE),
('OpenAI', 'text-embedding-ada-002', 'Embedding', NOW(), FALSE),
('OpenAI', 'text-embedding-3-small', 'Embedding', NOW(), FALSE),
('OpenAI', 'text-embedding-3-large', 'Embedding', NOW(), FALSE),

-- Google DeepMind Models
('Google DeepMind', 'Gemini Ultra', 'Text, Multimodal', NOW(), FALSE),
('Google DeepMind', 'Gemini Pro', 'Text, Multimodal', NOW(), FALSE),
('Google DeepMind', 'Gemini Flash', 'Text, Multimodal', NOW(), FALSE),
('Google DeepMind', 'Gemini Nano', 'Text, On-Device', NOW(), FALSE),
('Google DeepMind', 'Gemini Robotics', 'Robotics AI', NOW(), FALSE),

-- Anthropic Models
('Anthropic', 'Claude 3', 'Text', NOW(), FALSE),
('Anthropic', 'Claude 3.5', 'Text', NOW(), FALSE),

-- Perplexity Models
('Perplexity', 'pplx-7b-online', 'Text with realtime', NOW(), FALSE),
('Perplexity', 'pplx-70b-online', 'Text with realtime', NOW(), FALSE),

-- Mistral AI Models
('Mistral AI', 'Mistral-7B', 'Text', NOW(), FALSE),
('Mistral AI', 'Mixtral-8x7', 'Text', NOW(), FALSE),

-- Meta Llama Models
('Meta (Llama)', 'Llama 3-8B', 'Text', NOW(), FALSE),
('Meta (Llama)', 'Llama 3-70B', 'Text', NOW(), FALSE),

-- xAI Models
('xAI', 'Grok-1', 'Text', NOW(), FALSE),
('xAI', 'Grok-2', 'Text', NOW(), FALSE),

-- Cohere Models
('Cohere', 'Command', 'Text', NOW(), FALSE),
('Cohere', 'Command-R', 'Text', NOW(), FALSE),
('Cohere', 'Embed v3', 'Embedding', NOW(), FALSE),
('Cohere', 'Rerank v3', 'Ranking', NOW(), FALSE),

-- Hugging Face Models
('Hugging Face', 'GPT-2', 'Text', NOW(), FALSE),
('Hugging Face', 'GPT-J', 'Text', NOW(), FALSE),
('Hugging Face', 'GPT-NeoX-20B', 'Text', NOW(), FALSE),
('Hugging Face', 'BLOOM', 'Text', NOW(), FALSE),
('Hugging Face', 'Whisper', 'Speech-to-Text', NOW(), FALSE),
('Hugging Face', 'BERT', 'Text', NOW(), FALSE)

ON CONFLICT DO NOTHING;

-- =============================================================================
-- 3. TOOLS
-- =============================================================================
-- These are the available integrations/tools for bots

INSERT INTO tbl_tools (tool_name, tool_description, tool_logo, tool_class, created_at, updated_at, del_flg) VALUES
('Calendar', 'A time-management tool for scheduling appointments, meetings, and events', '/src/assets/calendar.png', NULL, NOW(), NOW(), FALSE),
('Gmail', 'Google''s email service for sending and receiving emails', '/src/assets/gmail.png', NULL, NOW(), NOW(), FALSE),
('Google Maps', 'A mapping and navigation service for directions and location search', '/src/assets/googleMap.png', NULL, NOW(), NOW(), FALSE),
('Hubspot', 'A CRM platform for sales, marketing, and customer service', '/src/assets/hubSpot.png', NULL, NOW(), NOW(), FALSE),
('GSheets', 'Cloud-based spreadsheet application for data management', '/src/assets/sheets.png', NULL, NOW(), NOW(), FALSE)

ON CONFLICT DO NOTHING;

-- =============================================================================
-- 4. BOT PLANS (Optional - Basic Plans)
-- =============================================================================
-- Uncomment if you want to seed default subscription plans

/*
INSERT INTO tbl_bot_plans (
    plan_name, plan_description, plan_price, plan_duration, 
    plan_status, payment_status, plan_messages, no_bot, no_agent, 
    message_rollover, overage_limit, created_at, updated_at, del_flg
) VALUES
('Free', 'Free tier with limited features', 0, 'monthly', 'Active', 'NA', 100, 1, 2, FALSE, 0, NOW(), NOW(), FALSE),
('Starter', 'Starter plan for small businesses', 29, 'monthly', 'Active', 'Pending', 1000, 3, 5, FALSE, 100, NOW(), NOW(), FALSE),
('Professional', 'Professional plan for growing teams', 99, 'monthly', 'Active', 'Pending', 5000, 10, 20, TRUE, 500, NOW(), NOW(), FALSE),
('Enterprise', 'Enterprise plan with unlimited features', 299, 'monthly', 'Active', 'Pending', 50000, -1, -1, TRUE, -1, NOW(), NOW(), FALSE)
ON CONFLICT DO NOTHING;
*/

-- =============================================================================
-- 5. ROLES (Optional - Basic Roles)
-- =============================================================================
-- Uncomment if you want to seed default roles

/*
INSERT INTO tbl_roles (role_name, role_description, created_at, updated_at, del_flg) VALUES
('admin', 'Full administrative access', NOW(), NOW(), FALSE),
('editor', 'Can edit bots and knowledge bases', NOW(), NOW(), FALSE),
('viewer', 'Read-only access', NOW(), NOW(), FALSE)
ON CONFLICT DO NOTHING;
*/

-- Commit transaction
COMMIT;

-- =============================================================================
-- Verification Queries (run after seeding)
-- =============================================================================
-- SELECT COUNT(*) as superadmin_count FROM tbl_superadmin;
-- SELECT COUNT(*) as llm_providers_count FROM tbl_basellm;
-- SELECT COUNT(*) as tools_count FROM tbl_tools;

-- =============================================================================
-- END OF SEED DATA
-- =============================================================================

