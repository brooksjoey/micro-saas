-- ============================================================================
-- Row Level Security (RLS) Policies for Micro-SaaS Platform
-- ============================================================================
-- 
-- This file defines Supabase/PostgreSQL RLS policies for multi-tenant data
-- isolation. Each authenticated user can only access their own data, while
-- service roles (for webhooks, workers, cron jobs) have appropriate access.
--
-- Policy Strategy:
-- - Users: Each user can only see/modify their own record
-- - Jobs: Users see their own jobs; service role sees all
-- - Subscriptions: Users see their own subscriptions
-- - Usage Counters: Users see their own usage
-- - Usage Events: Append-only for service role; read-only for users
--
-- Roles:
-- - authenticated: Regular users authenticated via Supabase Auth
-- - service_role: Backend services (API, workers, cron)
-- - anon: Anonymous users (minimal access)
--
-- Usage:
-- Apply this file via Supabase SQL editor or include in migrations.
-- ============================================================================

-- Enable RLS on all user-facing tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_counters ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Helper function to get current user ID from JWT
-- ============================================================================
-- Supabase provides auth.uid() which returns the user's ID from the JWT 'sub' claim

-- ============================================================================
-- USERS TABLE POLICIES
-- ============================================================================

-- Users can read their own record
CREATE POLICY "users_select_own" ON users
    FOR SELECT
    USING (auth.uid() = id);

-- Users can update their own record (limited fields should be enforced at app level)
CREATE POLICY "users_update_own" ON users
    FOR UPDATE
    USING (auth.uid() = id);

-- Service role can read all users
CREATE POLICY "users_service_select" ON users
    FOR SELECT
    TO service_role
    USING (true);

-- Service role can insert/update users (for syncing from Supabase Auth)
CREATE POLICY "users_service_insert" ON users
    FOR INSERT
    TO service_role
    WITH CHECK (true);

CREATE POLICY "users_service_update" ON users
    FOR UPDATE
    TO service_role
    USING (true);

-- ============================================================================
-- JOBS TABLE POLICIES
-- ============================================================================

-- Users can read their own jobs
CREATE POLICY "jobs_select_own" ON jobs
    FOR SELECT
    USING (user_id = auth.uid());

-- Users can insert jobs for themselves
CREATE POLICY "jobs_insert_own" ON jobs
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Users can update their own jobs (e.g., cancel)
CREATE POLICY "jobs_update_own" ON jobs
    FOR UPDATE
    USING (user_id = auth.uid());

-- Service role can read/write all jobs (for workers)
CREATE POLICY "jobs_service_all" ON jobs
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- SUBSCRIPTIONS TABLE POLICIES
-- ============================================================================

-- Users can read their own subscriptions
CREATE POLICY "subscriptions_select_own" ON subscriptions
    FOR SELECT
    USING (user_id = auth.uid());

-- Only service role can insert/update subscriptions (via Stripe webhooks)
CREATE POLICY "subscriptions_service_all" ON subscriptions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- USAGE_COUNTERS TABLE POLICIES
-- ============================================================================

-- Users can read their own usage counters
CREATE POLICY "usage_counters_select_own" ON usage_counters
    FOR SELECT
    USING (user_id = auth.uid());

-- Only service role can modify usage counters
CREATE POLICY "usage_counters_service_all" ON usage_counters
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- USAGE_EVENTS TABLE POLICIES
-- ============================================================================

-- Users can read their own usage events
CREATE POLICY "usage_events_select_own" ON usage_events
    FOR SELECT
    USING (user_id = auth.uid());

-- Only service role can insert usage events (append-only audit log)
CREATE POLICY "usage_events_service_insert" ON usage_events
    FOR INSERT
    TO service_role
    WITH CHECK (true);

-- Service role can read all usage events (for reconciliation)
CREATE POLICY "usage_events_service_select" ON usage_events
    FOR SELECT
    TO service_role
    USING (true);

-- No one can update or delete usage events (append-only)
-- (No UPDATE or DELETE policies defined)

-- ============================================================================
-- ANONYMOUS ACCESS (strictly limited)
-- ============================================================================

-- Anonymous users cannot access any tables
-- (No policies for 'anon' role means no access by default with RLS enabled)

-- ============================================================================
-- NOTES ON SECURITY MODEL
-- ============================================================================
-- 
-- 1. The service_role should only be used by backend services, never exposed
--    to clients. The SUPABASE_SERVICE_ROLE_KEY must be kept secret.
--
-- 2. The authenticated role policies use auth.uid() which is automatically
--    set by Supabase when validating JWT tokens.
--
-- 3. Usage events are append-only to maintain audit integrity. Updates and
--    deletes are not permitted even for service_role (enforced at app level).
--
-- 4. Stripe webhook handlers and workers use service_role to bypass user
--    restrictions when processing billing events or job updates.
--
-- 5. Consider adding row-level audit columns (created_by, updated_by) for
--    enhanced compliance tracking.
--
-- ============================================================================
