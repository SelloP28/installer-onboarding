-- =============================================================================
-- HSE Installer Onboarding Portal — Verification Engine Migration (Prompt 3)
-- Run this in the Supabase SQL Editor after supabase_gate0_migration.sql.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Extend installers.current_status to permit 'needs_review'
--    Prompt 3 requires routing knockouts or multi-issue submissions to 'needs_review'.
-- ---------------------------------------------------------------------------
ALTER TABLE public.installers
    DROP CONSTRAINT IF EXISTS installers_current_status_check;

ALTER TABLE public.installers
    ADD CONSTRAINT installers_current_status_check
        CHECK (current_status IN ('pending_review', 'needs_fixes', 'approved', 'needs_review'));

-- Add status_reason to store feedback notes or explanation for needs_fixes/needs_review
ALTER TABLE public.installers
    ADD COLUMN IF NOT EXISTS status_reason TEXT;

-- ---------------------------------------------------------------------------
-- 2. verification_logs table
--    Captures complete telemetry for every evaluation run:
--    - Structured rules engine results & knockouts
--    - Vision extraction results (name, reg number, signature block)
--    - Raw un-thresholded confidence scores for future calibration
--    - Automated decision & human-readable explanation
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.verification_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    installer_id    UUID NOT NULL REFERENCES public.installers (id) ON DELETE CASCADE,
    stage           TEXT NOT NULL DEFAULT 'gate_0',
    rules_passed    BOOLEAN NOT NULL,
    rules_result    JSONB NOT NULL,
    vision_result   JSONB,
    raw_confidence  JSONB,
    decision        TEXT NOT NULL CHECK (decision IN ('stage_1', 'needs_fixes', 'needs_review')),
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_verification_logs_installer_id
    ON public.verification_logs (installer_id);

CREATE INDEX IF NOT EXISTS idx_verification_logs_created_at
    ON public.verification_logs (created_at DESC);

-- ---------------------------------------------------------------------------
-- 3. Row Level Security for verification_logs
-- ---------------------------------------------------------------------------
ALTER TABLE public.verification_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all_verification_logs" ON public.verification_logs;
CREATE POLICY "service_role_all_verification_logs"
    ON public.verification_logs FOR ALL
    USING (auth.role() = 'service_role');
