


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";






CREATE OR REPLACE FUNCTION "public"."get_task_by_id"("p_task_id" "uuid") RETURNS TABLE("id" "uuid", "user_id" "uuid", "status" "text", "output" "text")
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
BEGIN
    RETURN QUERY
    SELECT t.id, t.user_id, t.status, t.output
    FROM agent_tasks t
    WHERE t.id = p_task_id;
END;
$$;


ALTER FUNCTION "public"."get_task_by_id"("p_task_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."is_project_owner"("p_project_id" "uuid") RETURNS boolean
    LANGUAGE "sql" STABLE SECURITY DEFINER
    AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.project_users
    WHERE project_id = p_project_id 
    AND user_id = auth.uid() 
    AND role = 'owner'
  );
$$;


ALTER FUNCTION "public"."is_project_owner"("p_project_id" "uuid") OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_task_status"("p_task_id" "uuid", "p_status" "text" DEFAULT NULL::"text", "p_output" "text" DEFAULT NULL::"text", "p_error" "text" DEFAULT NULL::"text", "p_exit_code" integer DEFAULT NULL::integer, "p_started_at" timestamp with time zone DEFAULT NULL::timestamp with time zone, "p_completed_at" timestamp with time zone DEFAULT NULL::timestamp with time zone) RETURNS TABLE("id" "uuid", "status" "text", "output" "text", "updated_at" timestamp with time zone)
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
DECLARE
    v_existing_output text;
    v_new_output text;
BEGIN
    -- Get existing output for appending
    SELECT t.output INTO v_existing_output FROM agent_tasks t WHERE t.id = p_task_id;
    
    -- Append new output if provided
    IF p_output IS NOT NULL THEN
        v_new_output := COALESCE(v_existing_output, '') || p_output;
    ELSE
        v_new_output := v_existing_output;
    END IF;
    
    -- Update the task
    UPDATE agent_tasks t
    SET 
        status = COALESCE(p_status, t.status),
        output = v_new_output,
        error = COALESCE(p_error, t.error),
        exit_code = COALESCE(p_exit_code, t.exit_code),
        started_at = COALESCE(p_started_at, t.started_at),
        completed_at = COALESCE(p_completed_at, t.completed_at),
        updated_at = NOW()
    WHERE t.id = p_task_id
    RETURNING t.id, t.status, t.output, t.updated_at
    INTO id, status, output, updated_at;
    
    RETURN NEXT;
END;
$$;


ALTER FUNCTION "public"."update_task_status"("p_task_id" "uuid", "p_status" "text", "p_output" "text", "p_error" "text", "p_exit_code" integer, "p_started_at" timestamp with time zone, "p_completed_at" timestamp with time zone) OWNER TO "postgres";


CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION "public"."update_updated_at_column"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."agent_sequences" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "project_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text" NOT NULL,
    "status" "text" DEFAULT 'in_progress'::"text" NOT NULL,
    "stages" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "artifacts" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "events" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."agent_sequences" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."agent_tasks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "device_id" "text" NOT NULL,
    "agent_type" "text" NOT NULL,
    "task_type" "text" NOT NULL,
    "payload" "jsonb" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text",
    "result" "jsonb",
    "error" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "output" "text",
    "exit_code" integer,
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "session_id" "uuid",
    "user_prompt" "text"
);


ALTER TABLE "public"."agent_tasks" OWNER TO "postgres";


COMMENT ON COLUMN "public"."agent_tasks"."error" IS 'Error message if task failed';



COMMENT ON COLUMN "public"."agent_tasks"."output" IS 'Streaming output from agent execution, appended during execution';



COMMENT ON COLUMN "public"."agent_tasks"."exit_code" IS 'Process exit code (0 = success)';



COMMENT ON COLUMN "public"."agent_tasks"."started_at" IS 'Timestamp when daemon began execution';



COMMENT ON COLUMN "public"."agent_tasks"."completed_at" IS 'Timestamp when task finished';



CREATE TABLE IF NOT EXISTS "public"."agents" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "agent_key" "text" NOT NULL,
    "command" "text" NOT NULL,
    "description" "text",
    "version" "text",
    "capabilities" "jsonb" DEFAULT '[]'::"jsonb",
    "args" "jsonb" NOT NULL,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."agents" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."api_keys" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "project_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "key_hash" "text" NOT NULL,
    "key_prefix" "text" NOT NULL,
    "last_four" "text" NOT NULL,
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "last_used_at" timestamp with time zone
);


ALTER TABLE "public"."api_keys" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."chat_sessions" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "title" "text",
    "is_starred" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "agent_type" "text",
    "device_id" "text"
);


ALTER TABLE "public"."chat_sessions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."composable_workflows" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid",
    "project_id" "uuid",
    "name" "text" NOT NULL,
    "description" "text",
    "template" "text",
    "stages" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "connections" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "parallel_stages" "jsonb" DEFAULT '[]'::"jsonb",
    "metadata" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."composable_workflows" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."events" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "org_id" "text",
    "org_name" "text",
    "actor" "text" NOT NULL,
    "type" "text" NOT NULL,
    "role" "text",
    "content" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "orchestration_id" "uuid",
    "metadata" "jsonb"
);


ALTER TABLE "public"."events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."features" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "project_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text" NOT NULL,
    "status" "text" DEFAULT 'in_progress'::"text" NOT NULL,
    "stages" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "artifacts" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "events" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."features" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."github_installations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "project_id" "uuid" NOT NULL,
    "user_id" "uuid",
    "installation_id" bigint NOT NULL,
    "account_type" "text" NOT NULL,
    "account_login" "text" NOT NULL,
    "account_id" bigint NOT NULL,
    "target_type" "text" NOT NULL,
    "permissions" "jsonb" DEFAULT '{}'::"jsonb",
    "events" "jsonb" DEFAULT '[]'::"jsonb",
    "suspended_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."github_installations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."github_repositories" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "installation_id" "uuid",
    "github_id" bigint NOT NULL,
    "owner" "text" NOT NULL,
    "name" "text" NOT NULL,
    "full_name" "text" NOT NULL,
    "description" "text",
    "is_private" boolean DEFAULT false,
    "default_branch" "text" DEFAULT 'main'::"text",
    "html_url" "text",
    "synced_at" timestamp with time zone DEFAULT "now"(),
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."github_repositories" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."github_webhook_events" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "installation_id" bigint,
    "event_type" "text" NOT NULL,
    "action" "text",
    "payload" "jsonb" NOT NULL,
    "processed" boolean DEFAULT false,
    "processed_at" timestamp with time zone,
    "error" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."github_webhook_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."hitl_requests" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "task_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "prompt" "text" NOT NULL,
    "options" "jsonb",
    "response" "text",
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "responded_at" timestamp with time zone,
    "expires_at" timestamp with time zone DEFAULT ("now"() + '00:05:00'::interval) NOT NULL,
    CONSTRAINT "hitl_requests_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'responded'::"text", 'expired'::"text", 'cancelled'::"text"])))
);

ALTER TABLE ONLY "public"."hitl_requests" REPLICA IDENTITY FULL;


ALTER TABLE "public"."hitl_requests" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."mcp_servers" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "project_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text",
    "transport_type" "text" NOT NULL,
    "url" "text",
    "command" "text",
    "args" "jsonb" DEFAULT '[]'::"jsonb",
    "env" "jsonb" DEFAULT '{}'::"jsonb",
    "headers" "jsonb" DEFAULT '{}'::"jsonb",
    "discovered_tools" "jsonb" DEFAULT '[]'::"jsonb",
    "discovered_resources" "jsonb" DEFAULT '[]'::"jsonb",
    "discovered_prompts" "jsonb" DEFAULT '[]'::"jsonb",
    "status" "text" DEFAULT 'disconnected'::"text" NOT NULL,
    "last_connected_at" timestamp with time zone,
    "last_error" "text",
    "icon_url" "text",
    "is_active" boolean DEFAULT true,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."mcp_servers" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."orchestrations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "project_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "description" "text",
    "status" "text" DEFAULT 'draft'::"text" NOT NULL,
    "template" "text",
    "config" "jsonb" DEFAULT '{}'::"jsonb",
    "stages" "jsonb" DEFAULT '[]'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"(),
    "user_id" "uuid"
);


ALTER TABLE "public"."orchestrations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."paired_devices" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "relay_url" "text" NOT NULL,
    "status" "text" DEFAULT 'connecting'::"text" NOT NULL,
    "hostname" "text",
    "os" "text",
    "paired_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "last_seen" timestamp with time zone,
    "working_directory" "text" DEFAULT '~'::"text",
    "recent_directories" "jsonb" DEFAULT '[]'::"jsonb"
);


ALTER TABLE "public"."paired_devices" OWNER TO "postgres";


COMMENT ON COLUMN "public"."paired_devices"."working_directory" IS 'Current working directory for agent tasks on this device. Defaults to home (~).';



COMMENT ON COLUMN "public"."paired_devices"."recent_directories" IS 'Recently used directories as JSON array for quick switching. Max 5 entries.';



CREATE TABLE IF NOT EXISTS "public"."project_users" (
    "project_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "role" "text" DEFAULT 'member'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."project_users" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."projects" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "settings" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."projects" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ssh_connections" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "host" "text" NOT NULL,
    "port" integer DEFAULT 22 NOT NULL,
    "username" "text" NOT NULL,
    "auth_method" "text" DEFAULT 'password'::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."ssh_connections" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."tasks" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "title" "text" NOT NULL,
    "description" "text" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text",
    "orchestration_id" "uuid",
    "assigned_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "result" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."tasks" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."user_integrations" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "provider" "text" NOT NULL,
    "provider_user_id" "text",
    "provider_username" "text",
    "access_token" "text" NOT NULL,
    "refresh_token" "text",
    "scopes" "text"[],
    "expires_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."user_integrations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."workflow_templates" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "text",
    "name" "text" NOT NULL,
    "description" "text",
    "template_key" "text" NOT NULL,
    "stages" "jsonb" NOT NULL,
    "config" "jsonb" DEFAULT '{}'::"jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."workflow_templates" OWNER TO "postgres";


ALTER TABLE ONLY "public"."agent_sequences"
    ADD CONSTRAINT "agent_sequences_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."agent_tasks"
    ADD CONSTRAINT "agent_tasks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."agents"
    ADD CONSTRAINT "agents_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."api_keys"
    ADD CONSTRAINT "api_keys_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."chat_sessions"
    ADD CONSTRAINT "chat_sessions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."composable_workflows"
    ADD CONSTRAINT "composable_workflows_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."events"
    ADD CONSTRAINT "events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."features"
    ADD CONSTRAINT "features_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."github_installations"
    ADD CONSTRAINT "github_installations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."github_repositories"
    ADD CONSTRAINT "github_repositories_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."github_webhook_events"
    ADD CONSTRAINT "github_webhook_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hitl_requests"
    ADD CONSTRAINT "hitl_requests_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."mcp_servers"
    ADD CONSTRAINT "mcp_servers_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."orchestrations"
    ADD CONSTRAINT "orchestrations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."paired_devices"
    ADD CONSTRAINT "paired_devices_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."project_users"
    ADD CONSTRAINT "project_users_pkey" PRIMARY KEY ("project_id", "user_id");



ALTER TABLE ONLY "public"."projects"
    ADD CONSTRAINT "projects_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."ssh_connections"
    ADD CONSTRAINT "ssh_connections_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."tasks"
    ADD CONSTRAINT "tasks_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."user_integrations"
    ADD CONSTRAINT "user_integrations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."workflow_templates"
    ADD CONSTRAINT "workflow_templates_pkey" PRIMARY KEY ("id");



CREATE INDEX "idx_agent_sequences_project" ON "public"."agent_sequences" USING "btree" ("project_id");



CREATE INDEX "idx_agent_tasks_device" ON "public"."agent_tasks" USING "btree" ("device_id");



CREATE INDEX "idx_agent_tasks_session" ON "public"."agent_tasks" USING "btree" ("session_id", "created_at");



CREATE INDEX "idx_agent_tasks_status" ON "public"."agent_tasks" USING "btree" ("status");



CREATE INDEX "idx_agent_tasks_user" ON "public"."agent_tasks" USING "btree" ("user_id");



CREATE INDEX "idx_agents_user" ON "public"."agents" USING "btree" ("user_id");



CREATE INDEX "idx_api_keys_project" ON "public"."api_keys" USING "btree" ("project_id");



CREATE INDEX "idx_chat_sessions_user_updated" ON "public"."chat_sessions" USING "btree" ("user_id", "updated_at" DESC);



CREATE INDEX "idx_composable_workflows_project" ON "public"."composable_workflows" USING "btree" ("project_id");



CREATE INDEX "idx_composable_workflows_user" ON "public"."composable_workflows" USING "btree" ("user_id");



CREATE INDEX "idx_events_created" ON "public"."events" USING "btree" ("created_at" DESC);



CREATE INDEX "idx_events_orchestration" ON "public"."events" USING "btree" ("orchestration_id");



CREATE INDEX "idx_features_project" ON "public"."features" USING "btree" ("project_id");



CREATE INDEX "idx_github_installations_project" ON "public"."github_installations" USING "btree" ("project_id");



CREATE INDEX "idx_github_repositories_installation" ON "public"."github_repositories" USING "btree" ("installation_id");



CREATE INDEX "idx_github_webhook_events_installation" ON "public"."github_webhook_events" USING "btree" ("installation_id");



CREATE INDEX "idx_github_webhook_events_processed" ON "public"."github_webhook_events" USING "btree" ("processed");



CREATE INDEX "idx_hitl_requests_expires_at" ON "public"."hitl_requests" USING "btree" ("expires_at") WHERE ("status" = 'pending'::"text");



CREATE INDEX "idx_hitl_requests_task_id" ON "public"."hitl_requests" USING "btree" ("task_id");



CREATE INDEX "idx_hitl_requests_user_pending" ON "public"."hitl_requests" USING "btree" ("user_id", "status") WHERE ("status" = 'pending'::"text");



CREATE INDEX "idx_mcp_servers_project" ON "public"."mcp_servers" USING "btree" ("project_id");



CREATE INDEX "idx_orchestrations_project" ON "public"."orchestrations" USING "btree" ("project_id");



CREATE INDEX "idx_orchestrations_status" ON "public"."orchestrations" USING "btree" ("status");



CREATE INDEX "idx_orchestrations_user_id" ON "public"."orchestrations" USING "btree" ("user_id");



CREATE INDEX "idx_project_users_user" ON "public"."project_users" USING "btree" ("user_id");



CREATE INDEX "idx_tasks_orchestration" ON "public"."tasks" USING "btree" ("orchestration_id");



CREATE INDEX "idx_tasks_status" ON "public"."tasks" USING "btree" ("status");



CREATE INDEX "idx_user_integrations_provider" ON "public"."user_integrations" USING "btree" ("user_id", "provider");



CREATE INDEX "idx_user_integrations_user" ON "public"."user_integrations" USING "btree" ("user_id");



CREATE OR REPLACE TRIGGER "update_agent_sequences_updated_at" BEFORE UPDATE ON "public"."agent_sequences" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_agent_tasks_updated_at" BEFORE UPDATE ON "public"."agent_tasks" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_agents_updated_at" BEFORE UPDATE ON "public"."agents" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_composable_workflows_updated_at" BEFORE UPDATE ON "public"."composable_workflows" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_features_updated_at" BEFORE UPDATE ON "public"."features" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_github_installations_updated_at" BEFORE UPDATE ON "public"."github_installations" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_mcp_servers_updated_at" BEFORE UPDATE ON "public"."mcp_servers" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_orchestrations_updated_at" BEFORE UPDATE ON "public"."orchestrations" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_tasks_updated_at" BEFORE UPDATE ON "public"."tasks" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_user_integrations_updated_at" BEFORE UPDATE ON "public"."user_integrations" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



CREATE OR REPLACE TRIGGER "update_workflow_templates_updated_at" BEFORE UPDATE ON "public"."workflow_templates" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();



ALTER TABLE ONLY "public"."agent_sequences"
    ADD CONSTRAINT "agent_sequences_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."agent_tasks"
    ADD CONSTRAINT "agent_tasks_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "public"."chat_sessions"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."agent_tasks"
    ADD CONSTRAINT "agent_tasks_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."agents"
    ADD CONSTRAINT "agents_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."api_keys"
    ADD CONSTRAINT "api_keys_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."chat_sessions"
    ADD CONSTRAINT "chat_sessions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."composable_workflows"
    ADD CONSTRAINT "composable_workflows_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."composable_workflows"
    ADD CONSTRAINT "composable_workflows_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."events"
    ADD CONSTRAINT "events_orchestration_id_fkey" FOREIGN KEY ("orchestration_id") REFERENCES "public"."orchestrations"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."features"
    ADD CONSTRAINT "features_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."github_installations"
    ADD CONSTRAINT "github_installations_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."github_installations"
    ADD CONSTRAINT "github_installations_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."github_repositories"
    ADD CONSTRAINT "github_repositories_installation_id_fkey" FOREIGN KEY ("installation_id") REFERENCES "public"."github_installations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."hitl_requests"
    ADD CONSTRAINT "hitl_requests_task_id_fkey" FOREIGN KEY ("task_id") REFERENCES "public"."agent_tasks"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."mcp_servers"
    ADD CONSTRAINT "mcp_servers_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."orchestrations"
    ADD CONSTRAINT "orchestrations_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."orchestrations"
    ADD CONSTRAINT "orchestrations_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id");



ALTER TABLE ONLY "public"."paired_devices"
    ADD CONSTRAINT "paired_devices_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."project_users"
    ADD CONSTRAINT "project_users_project_id_fkey" FOREIGN KEY ("project_id") REFERENCES "public"."projects"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."project_users"
    ADD CONSTRAINT "project_users_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."projects"
    ADD CONSTRAINT "projects_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ssh_connections"
    ADD CONSTRAINT "ssh_connections_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."tasks"
    ADD CONSTRAINT "tasks_orchestration_id_fkey" FOREIGN KEY ("orchestration_id") REFERENCES "public"."orchestrations"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."user_integrations"
    ADD CONSTRAINT "user_integrations_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



CREATE POLICY "Anyone can view workflow templates" ON "public"."workflow_templates" FOR SELECT USING (true);



CREATE POLICY "Project owners can manage members" ON "public"."project_users" USING ("public"."is_project_owner"("project_id")) WITH CHECK ("public"."is_project_owner"("project_id"));



CREATE POLICY "Service role can delete agent tasks" ON "public"."agent_tasks" FOR DELETE TO "service_role" USING (true);



CREATE POLICY "Service role can insert agent tasks" ON "public"."agent_tasks" FOR INSERT TO "service_role" WITH CHECK (true);



CREATE POLICY "Service role can manage webhook events" ON "public"."github_webhook_events" USING (true);



CREATE POLICY "Service role can read all agent tasks" ON "public"."agent_tasks" FOR SELECT TO "service_role" USING (true);



CREATE POLICY "Service role can update all agent tasks" ON "public"."agent_tasks" FOR UPDATE TO "service_role" USING (true) WITH CHECK (true);



CREATE POLICY "Users can create own agent tasks" ON "public"."agent_tasks" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can delete own agent tasks" ON "public"."agent_tasks" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can delete their own connections" ON "public"."ssh_connections" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can delete their own devices" ON "public"."paired_devices" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can delete their own projects" ON "public"."projects" FOR DELETE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can insert events" ON "public"."events" FOR INSERT WITH CHECK (true);



CREATE POLICY "Users can insert own orchestrations" ON "public"."orchestrations" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can insert own tasks" ON "public"."agent_tasks" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can insert their own connections" ON "public"."ssh_connections" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can insert their own devices" ON "public"."paired_devices" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can insert their own projects" ON "public"."projects" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can manage API keys for their projects" ON "public"."api_keys" USING ((EXISTS ( SELECT 1
   FROM "public"."project_users" "pu"
  WHERE (("pu"."project_id" = "api_keys"."project_id") AND ("pu"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can manage MCP servers for their projects" ON "public"."mcp_servers" USING ((EXISTS ( SELECT 1
   FROM "public"."project_users" "pu"
  WHERE (("pu"."project_id" = "mcp_servers"."project_id") AND ("pu"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can manage features for their projects" ON "public"."features" USING ((EXISTS ( SELECT 1
   FROM "public"."project_users" "pu"
  WHERE (("pu"."project_id" = "features"."project_id") AND ("pu"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can manage orchestrations for their projects" ON "public"."orchestrations" USING ((EXISTS ( SELECT 1
   FROM "public"."project_users" "pu"
  WHERE (("pu"."project_id" = "orchestrations"."project_id") AND ("pu"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can manage own GitHub installations" ON "public"."github_installations" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can manage own agents" ON "public"."agents" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can manage own integrations" ON "public"."user_integrations" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can manage own templates" ON "public"."workflow_templates" USING (((("user_id")::"uuid" = "auth"."uid"()) OR ("user_id" IS NULL)));



CREATE POLICY "Users can manage own workflows" ON "public"."composable_workflows" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can manage sequences for their projects" ON "public"."agent_sequences" USING ((EXISTS ( SELECT 1
   FROM "public"."project_users" "pu"
  WHERE (("pu"."project_id" = "agent_sequences"."project_id") AND ("pu"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can manage tasks for their orchestrations" ON "public"."tasks" USING ((EXISTS ( SELECT 1
   FROM ("public"."orchestrations" "o"
     JOIN "public"."project_users" "pu" ON (("pu"."project_id" = "o"."project_id")))
  WHERE (("o"."id" = "tasks"."orchestration_id") AND ("pu"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can manage their own sessions" ON "public"."chat_sessions" USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update own agent tasks" ON "public"."agent_tasks" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update own orchestrations" ON "public"."orchestrations" FOR UPDATE USING ((("auth"."uid"() = "user_id") OR ("project_id" IN ( SELECT "projects"."id"
   FROM "public"."projects"
  WHERE ("projects"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can update own tasks" ON "public"."agent_tasks" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update their own connections" ON "public"."ssh_connections" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update their own devices" ON "public"."paired_devices" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can update their own projects" ON "public"."projects" FOR UPDATE USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view GitHub installations for their projects" ON "public"."github_installations" FOR SELECT USING ((("auth"."uid"() = "user_id") OR (EXISTS ( SELECT 1
   FROM "public"."project_users" "pu"
  WHERE (("pu"."project_id" = "github_installations"."project_id") AND ("pu"."user_id" = "auth"."uid"()))))));



CREATE POLICY "Users can view MCP servers for their projects" ON "public"."mcp_servers" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."project_users" "pu"
  WHERE (("pu"."project_id" = "mcp_servers"."project_id") AND ("pu"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can view events for their orchestrations" ON "public"."events" FOR SELECT USING ((("orchestration_id" IS NULL) OR (EXISTS ( SELECT 1
   FROM ("public"."orchestrations" "o"
     JOIN "public"."project_users" "pu" ON (("pu"."project_id" = "o"."project_id")))
  WHERE (("o"."id" = "events"."orchestration_id") AND ("pu"."user_id" = "auth"."uid"()))))));



CREATE POLICY "Users can view features for their projects" ON "public"."features" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."project_users" "pu"
  WHERE (("pu"."project_id" = "features"."project_id") AND ("pu"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can view orchestrations for their projects" ON "public"."orchestrations" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."project_users" "pu"
  WHERE (("pu"."project_id" = "orchestrations"."project_id") AND ("pu"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can view own agent tasks" ON "public"."agent_tasks" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view own agents" ON "public"."agents" FOR SELECT USING ((("auth"."uid"() = "user_id") OR ("user_id" IS NULL)));



CREATE POLICY "Users can view own integrations" ON "public"."user_integrations" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view own orchestrations" ON "public"."orchestrations" FOR SELECT USING ((("auth"."uid"() = "user_id") OR ("project_id" IN ( SELECT "projects"."id"
   FROM "public"."projects"
  WHERE ("projects"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can view own tasks" ON "public"."agent_tasks" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view own workflows" ON "public"."composable_workflows" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view projects they belong to" ON "public"."project_users" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view repos for their installations" ON "public"."github_repositories" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."github_installations" "gi"
  WHERE (("gi"."id" = "github_repositories"."installation_id") AND (("gi"."user_id" = "auth"."uid"()) OR (EXISTS ( SELECT 1
           FROM "public"."project_users" "pu"
          WHERE (("pu"."project_id" = "gi"."project_id") AND ("pu"."user_id" = "auth"."uid"())))))))));



CREATE POLICY "Users can view sequences for their projects" ON "public"."agent_sequences" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM "public"."project_users" "pu"
  WHERE (("pu"."project_id" = "agent_sequences"."project_id") AND ("pu"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can view tasks for their orchestrations" ON "public"."tasks" FOR SELECT USING ((EXISTS ( SELECT 1
   FROM ("public"."orchestrations" "o"
     JOIN "public"."project_users" "pu" ON (("pu"."project_id" = "o"."project_id")))
  WHERE (("o"."id" = "tasks"."orchestration_id") AND ("pu"."user_id" = "auth"."uid"())))));



CREATE POLICY "Users can view their own connections" ON "public"."ssh_connections" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view their own devices" ON "public"."paired_devices" FOR SELECT USING (("auth"."uid"() = "user_id"));



CREATE POLICY "Users can view their own projects" ON "public"."projects" FOR SELECT USING (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."agent_sequences" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."agent_tasks" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."agents" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."api_keys" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."chat_sessions" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."composable_workflows" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."features" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."github_installations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."github_repositories" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."github_webhook_events" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."mcp_servers" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."orchestrations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."paired_devices" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."project_users" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."projects" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."ssh_connections" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."tasks" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."user_integrations" ENABLE ROW LEVEL SECURITY;


ALTER TABLE "public"."workflow_templates" ENABLE ROW LEVEL SECURITY;




ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";






ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."agent_sequences";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."agent_tasks";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."events";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."hitl_requests";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."orchestrations";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."paired_devices";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."ssh_connections";



ALTER PUBLICATION "supabase_realtime" ADD TABLE ONLY "public"."tasks";



GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";

























































































































































GRANT ALL ON FUNCTION "public"."get_task_by_id"("p_task_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."get_task_by_id"("p_task_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_task_by_id"("p_task_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."is_project_owner"("p_project_id" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."is_project_owner"("p_project_id" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."is_project_owner"("p_project_id" "uuid") TO "service_role";



GRANT ALL ON FUNCTION "public"."update_task_status"("p_task_id" "uuid", "p_status" "text", "p_output" "text", "p_error" "text", "p_exit_code" integer, "p_started_at" timestamp with time zone, "p_completed_at" timestamp with time zone) TO "anon";
GRANT ALL ON FUNCTION "public"."update_task_status"("p_task_id" "uuid", "p_status" "text", "p_output" "text", "p_error" "text", "p_exit_code" integer, "p_started_at" timestamp with time zone, "p_completed_at" timestamp with time zone) TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_task_status"("p_task_id" "uuid", "p_status" "text", "p_output" "text", "p_error" "text", "p_exit_code" integer, "p_started_at" timestamp with time zone, "p_completed_at" timestamp with time zone) TO "service_role";



GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "service_role";


















GRANT ALL ON TABLE "public"."agent_sequences" TO "anon";
GRANT ALL ON TABLE "public"."agent_sequences" TO "authenticated";
GRANT ALL ON TABLE "public"."agent_sequences" TO "service_role";



GRANT ALL ON TABLE "public"."agent_tasks" TO "anon";
GRANT ALL ON TABLE "public"."agent_tasks" TO "authenticated";
GRANT ALL ON TABLE "public"."agent_tasks" TO "service_role";



GRANT ALL ON TABLE "public"."agents" TO "anon";
GRANT ALL ON TABLE "public"."agents" TO "authenticated";
GRANT ALL ON TABLE "public"."agents" TO "service_role";



GRANT ALL ON TABLE "public"."api_keys" TO "anon";
GRANT ALL ON TABLE "public"."api_keys" TO "authenticated";
GRANT ALL ON TABLE "public"."api_keys" TO "service_role";



GRANT ALL ON TABLE "public"."chat_sessions" TO "anon";
GRANT ALL ON TABLE "public"."chat_sessions" TO "authenticated";
GRANT ALL ON TABLE "public"."chat_sessions" TO "service_role";



GRANT ALL ON TABLE "public"."composable_workflows" TO "anon";
GRANT ALL ON TABLE "public"."composable_workflows" TO "authenticated";
GRANT ALL ON TABLE "public"."composable_workflows" TO "service_role";



GRANT ALL ON TABLE "public"."events" TO "anon";
GRANT ALL ON TABLE "public"."events" TO "authenticated";
GRANT ALL ON TABLE "public"."events" TO "service_role";



GRANT ALL ON TABLE "public"."features" TO "anon";
GRANT ALL ON TABLE "public"."features" TO "authenticated";
GRANT ALL ON TABLE "public"."features" TO "service_role";



GRANT ALL ON TABLE "public"."github_installations" TO "anon";
GRANT ALL ON TABLE "public"."github_installations" TO "authenticated";
GRANT ALL ON TABLE "public"."github_installations" TO "service_role";



GRANT ALL ON TABLE "public"."github_repositories" TO "anon";
GRANT ALL ON TABLE "public"."github_repositories" TO "authenticated";
GRANT ALL ON TABLE "public"."github_repositories" TO "service_role";



GRANT ALL ON TABLE "public"."github_webhook_events" TO "anon";
GRANT ALL ON TABLE "public"."github_webhook_events" TO "authenticated";
GRANT ALL ON TABLE "public"."github_webhook_events" TO "service_role";



GRANT ALL ON TABLE "public"."hitl_requests" TO "anon";
GRANT ALL ON TABLE "public"."hitl_requests" TO "authenticated";
GRANT ALL ON TABLE "public"."hitl_requests" TO "service_role";



GRANT ALL ON TABLE "public"."mcp_servers" TO "anon";
GRANT ALL ON TABLE "public"."mcp_servers" TO "authenticated";
GRANT ALL ON TABLE "public"."mcp_servers" TO "service_role";



GRANT ALL ON TABLE "public"."orchestrations" TO "anon";
GRANT ALL ON TABLE "public"."orchestrations" TO "authenticated";
GRANT ALL ON TABLE "public"."orchestrations" TO "service_role";



GRANT ALL ON TABLE "public"."paired_devices" TO "anon";
GRANT ALL ON TABLE "public"."paired_devices" TO "authenticated";
GRANT ALL ON TABLE "public"."paired_devices" TO "service_role";



GRANT ALL ON TABLE "public"."project_users" TO "anon";
GRANT ALL ON TABLE "public"."project_users" TO "authenticated";
GRANT ALL ON TABLE "public"."project_users" TO "service_role";



GRANT ALL ON TABLE "public"."projects" TO "anon";
GRANT ALL ON TABLE "public"."projects" TO "authenticated";
GRANT ALL ON TABLE "public"."projects" TO "service_role";



GRANT ALL ON TABLE "public"."ssh_connections" TO "anon";
GRANT ALL ON TABLE "public"."ssh_connections" TO "authenticated";
GRANT ALL ON TABLE "public"."ssh_connections" TO "service_role";



GRANT ALL ON TABLE "public"."tasks" TO "anon";
GRANT ALL ON TABLE "public"."tasks" TO "authenticated";
GRANT ALL ON TABLE "public"."tasks" TO "service_role";



GRANT ALL ON TABLE "public"."user_integrations" TO "anon";
GRANT ALL ON TABLE "public"."user_integrations" TO "authenticated";
GRANT ALL ON TABLE "public"."user_integrations" TO "service_role";



GRANT ALL ON TABLE "public"."workflow_templates" TO "anon";
GRANT ALL ON TABLE "public"."workflow_templates" TO "authenticated";
GRANT ALL ON TABLE "public"."workflow_templates" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































drop extension if exists "pg_net";


