
CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL, 
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
)

;


CREATE TABLE tbl_bot_plans (
	plan_id SERIAL NOT NULL, 
	plan_name VARCHAR(255) NOT NULL, 
	plan_description TEXT, 
	plan_price NUMERIC(10, 2) NOT NULL, 
	plan_duration INTEGER NOT NULL, 
	plan_status BOOLEAN, 
	payment_status VARCHAR(50) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_bot_plans_pkey PRIMARY KEY (plan_id)
)

;


CREATE TABLE tbl_custombot (
	bot_id SERIAL NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	bot_name VARCHAR(255) NOT NULL, 
	tone_of_voice toneofvoiceenum NOT NULL, 
	industry industryenum NOT NULL, 
	avatar VARCHAR(255) NOT NULL, 
	purpose VARCHAR(500) NOT NULL, 
	core_features JSON, 
	instructions JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	del_flg BOOLEAN, 
	status BOOLEAN, 
	CONSTRAINT tbl_custombot_pkey PRIMARY KEY (bot_id), 
	CONSTRAINT tbl_custombot_bot_name_key UNIQUE (bot_name)
)

;


CREATE TABLE tbl_embedding_models (
	embedding_id SERIAL NOT NULL, 
	model_name VARCHAR(255) NOT NULL, 
	api_key VARCHAR(255) NOT NULL, 
	chunk_size INTEGER, 
	chunk_overlap INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_embedding_models_pkey PRIMARY KEY (embedding_id)
)

;


CREATE TABLE tbl_error (
	error_id SERIAL NOT NULL, 
	error_message TEXT NOT NULL, 
	error_code VARCHAR(50), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	tenant_id INTEGER, 
	bot_id INTEGER, 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_error_pkey PRIMARY KEY (error_id)
)

;


CREATE TABLE tbl_knowledge_base (
	knowledge_base_id SERIAL NOT NULL, 
	knowledge_base_name VARCHAR(255) NOT NULL, 
	upload_pdf VARCHAR(255) NOT NULL, 
	scrap_url VARCHAR(255) NOT NULL, 
	max_crawl_pages INTEGER, 
	max_crawl_depth INTEGER, 
	dynamic_wait INTEGER, 
	raw_text TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_knowledge_base_pkey PRIMARY KEY (knowledge_base_id)
)

;


CREATE TABLE tbl_llm (
	llm_id SERIAL NOT NULL, 
	provider VARCHAR(255) NOT NULL, 
	model_name VARCHAR(255) NOT NULL, 
	api_key_temp VARCHAR(255) NOT NULL, 
	max_output_tokens INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_llm_pkey PRIMARY KEY (llm_id)
)

;


CREATE TABLE tbl_loginuser (
	login_id SERIAL NOT NULL, 
	username VARCHAR(100) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	email VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	tenant_id INTEGER NOT NULL, 
	role VARCHAR(100), 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_loginuser_pkey PRIMARY KEY (login_id), 
	CONSTRAINT tbl_loginuser_email_key UNIQUE (email)
)

;


CREATE TABLE tbl_roles (
	role_id SERIAL NOT NULL, 
	role_name VARCHAR(100) NOT NULL, 
	role_description TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_roles_pkey PRIMARY KEY (role_id), 
	CONSTRAINT tbl_roles_role_name_key UNIQUE (role_name)
)

;


CREATE TABLE tbl_superadmin (
	superadmin_id SERIAL NOT NULL, 
	superadmin_username VARCHAR(255) NOT NULL, 
	superadmin_email VARCHAR(255) NOT NULL, 
	superadmin_password VARCHAR(255) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_superadmin_pkey PRIMARY KEY (superadmin_id), 
	CONSTRAINT tbl_superadmin_superadmin_email_key UNIQUE (superadmin_email), 
	CONSTRAINT tbl_superadmin_superadmin_username_key UNIQUE (superadmin_username)
)

;


CREATE TABLE tbl_system_embedding_models (
	embedding_id SERIAL NOT NULL, 
	model_name VARCHAR(255) NOT NULL, 
	api_key VARCHAR(255) NOT NULL, 
	chunk_size INTEGER, 
	chunk_overlap INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_system_embedding_models_pkey PRIMARY KEY (embedding_id)
)

;


CREATE TABLE tbl_system_llm (
	llm_id SERIAL NOT NULL, 
	provider VARCHAR(255) NOT NULL, 
	model_name VARCHAR(255) NOT NULL, 
	api_key_temp VARCHAR(255) NOT NULL, 
	max_output_tokens INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_system_llm_pkey PRIMARY KEY (llm_id)
)

;


CREATE TABLE tbl_tenant_subscriptions (
	subscription_id SERIAL NOT NULL, 
	tenant_id INTEGER, 
	plan_id INTEGER, 
	subscription_start TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	subscription_end TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	auto_renewal BOOLEAN, 
	remaining_credits INTEGER, 
	total_plan_credits INTEGER, 
	subscription_status subscription_status_enum, 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_tenant_subscriptions_pkey PRIMARY KEY (subscription_id)
)

;


CREATE TABLE tbl_tenants (
	tenant_id SERIAL NOT NULL, 
	tenant_name VARCHAR(255) NOT NULL, 
	tenant_key VARCHAR(255) NOT NULL, 
	tenant_address VARCHAR(255), 
	tenant_emailid VARCHAR(255) NOT NULL, 
	tenant_contact VARCHAR(20), 
	"tenant_GSTNo" VARCHAR(100), 
	"tenant_PAN" VARCHAR(100), 
	tenant_city VARCHAR(100), 
	tenant_country VARCHAR(100), 
	tenant_postcode VARCHAR(100), 
	tenant_status VARCHAR(100), 
	tenant_plan_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	del_flg BOOLEAN, 
	CONSTRAINT tbl_tenants_pkey PRIMARY KEY (tenant_id), 
	CONSTRAINT tbl_tenants_tenant_plan_id_fkey FOREIGN KEY(tenant_plan_id) REFERENCES tbl_bot_plans (plan_id), 
	CONSTRAINT tbl_tenants_tenant_emailid_key UNIQUE (tenant_emailid)
)

;

