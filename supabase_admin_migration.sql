-- =============================================================================
-- HSE Installer Onboarding Portal — Admin Dashboard & Audit Log Migration (Prompt 5)
-- Run this in the Supabase SQL Editor.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. audit_log table
--    Tracks all compliance staff decisions (approvals, rejections, overrides)
--    across Gate 0 and subsequent document stages.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    installer_id    UUID NOT NULL REFERENCES public.installers (id) ON DELETE CASCADE,
    actor           TEXT NOT NULL DEFAULT 'compliance_admin',
    action          TEXT NOT NULL,
    details         JSONB,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_installer_id
    ON public.audit_log (installer_id);

CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
    ON public.audit_log (timestamp DESC);

-- ---------------------------------------------------------------------------
-- 2. Row Level Security for audit_log
-- ---------------------------------------------------------------------------
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all_audit_log" ON public.audit_log;
CREATE POLICY "service_role_all_audit_log"
    ON public.audit_log FOR ALL
    USING (auth.role() = 'service_role');

-- In development with anon API key, allow reading and inserting audit logs
DROP POLICY IF EXISTS "anon_all_audit_log" ON public.audit_log;
CREATE POLICY "anon_all_audit_log"
    ON public.audit_log FOR ALL
    USING (true)
    WITH CHECK (true);
