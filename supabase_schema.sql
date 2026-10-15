-- =============================================================================
-- HSE Installer Onboarding Portal — Supabase Schema Migration
-- Run this in the Supabase SQL Editor (or as a migration file).
-- =============================================================================

-- Enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 1. installers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.installers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name    TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    access_token    UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    current_stage   TEXT NOT NULL DEFAULT 'gate_0'
                        CHECK (current_stage IN ('gate_0','stage_1','stage_2','complete')),
    current_status  TEXT NOT NULL DEFAULT 'pending_review'
                        CHECK (current_status IN ('pending_review','needs_fixes','approved')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for token-based lookups (the primary access pattern)
CREATE INDEX IF NOT EXISTS idx_installers_access_token
    ON public.installers (access_token);

-- ---------------------------------------------------------------------------
-- 2. personnel
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.personnel (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    installer_id    UUID NOT NULL REFERENCES public.installers (id) ON DELETE CASCADE,
    full_name       TEXT NOT NULL,
    id_number       TEXT NOT NULL,
    role            TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_personnel_installer_id
    ON public.personnel (installer_id);

-- ---------------------------------------------------------------------------
-- 3. document_requirements
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.document_requirements (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stage               TEXT NOT NULL CHECK (stage IN ('gate_0','stage_1','stage_2')),
    section             TEXT NOT NULL,         -- logical grouping, e.g. "Legal", "Safety"
    name                TEXT NOT NULL,         -- human-readable document name
    scope               TEXT NOT NULL CHECK (scope IN ('company','person')),
    requirement_level   TEXT NOT NULL CHECK (requirement_level IN ('mandatory','conditional')),
    installer_upload    BOOLEAN NOT NULL DEFAULT TRUE,
    has_expiry          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 4. document_submissions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.document_submissions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    installer_id        UUID NOT NULL REFERENCES public.installers (id) ON DELETE CASCADE,
    personnel_id        UUID REFERENCES public.personnel (id) ON DELETE SET NULL,
    requirement_id      UUID NOT NULL REFERENCES public.document_requirements (id) ON DELETE RESTRICT,
    file_path           TEXT NOT NULL,         -- Supabase Storage object path
    status              TEXT NOT NULL DEFAULT 'pending_review'
                            CHECK (status IN ('pending_review','approved','rejected')),
    rejection_reason    TEXT,
    expiry_date         DATE,
    reviewed_by         TEXT,                  -- admin user identifier
    reviewed_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_doc_submissions_installer_id
    ON public.document_submissions (installer_id);

CREATE INDEX IF NOT EXISTS idx_doc_submissions_status
    ON public.document_submissions (status);

-- ---------------------------------------------------------------------------
-- 5. Row Level Security (RLS) — basic policies
--    Tighten these before going to production.
-- ---------------------------------------------------------------------------

ALTER TABLE public.installers          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.personnel           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_submissions ENABLE ROW LEVEL SECURITY;

-- Allow service-role (backend) full access; restrict anon to nothing by default.
-- TODO: replace with proper auth.uid()-based policies when Supabase Auth is wired up.

DROP POLICY IF EXISTS "service_role_all_installers" ON public.installers;
CREATE POLICY "service_role_all_installers"
    ON public.installers FOR ALL
    USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "service_role_all_personnel" ON public.personnel;
CREATE POLICY "service_role_all_personnel"
    ON public.personnel FOR ALL
    USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "service_role_all_doc_requirements" ON public.document_requirements;
CREATE POLICY "service_role_all_doc_requirements"
    ON public.document_requirements FOR ALL
    USING (auth.role() = 'service_role');

DROP POLICY IF EXISTS "service_role_all_doc_submissions" ON public.document_submissions;
CREATE POLICY "service_role_all_doc_submissions"
    ON public.document_submissions FOR ALL
    USING (auth.role() = 'service_role');

-- ---------------------------------------------------------------------------
-- 6. Seed: document_requirements
--    Populate with your actual requirements list — placeholders below.
--    Replace / extend before running in production.
-- ---------------------------------------------------------------------------

INSERT INTO public.document_requirements
    (stage, section, name, scope, requirement_level, installer_upload, has_expiry)
VALUES
-- Stage 1 — Company documents
('stage_1', 'Legal',          'Company Registration Certificate',       'company', 'mandatory',    TRUE,  FALSE),
('stage_1', 'Legal',          'Tax Clearance Certificate',              'company', 'mandatory',    TRUE,  TRUE),
('stage_1', 'Legal',          'B-BBEE Certificate / Affidavit',         'company', 'mandatory',    TRUE,  TRUE),
('stage_1', 'Insurance',      'Public Liability Insurance Policy',      'company', 'mandatory',    TRUE,  TRUE),
('stage_1', 'Insurance',      'Workmen''s Compensation (COIDA) Letter', 'company', 'mandatory',    TRUE,  TRUE),
('stage_1', 'HSE',            'Health & Safety Policy (signed)',        'company', 'mandatory',    TRUE,  FALSE),
('stage_1', 'HSE',            'Company Method Statement',               'company', 'conditional',  TRUE,  FALSE),
('stage_1', 'Banking',        'Proof of Bank Account (letter/stamp)',   'company', 'mandatory',    TRUE,  FALSE),

-- Stage 2 — Personnel documents (person-scoped)
('stage_2', 'Identity',       'Certified ID Copy',                      'person',  'mandatory',    TRUE,  FALSE),
('stage_2', 'Qualifications', 'NQF / Trade Certificate',                'person',  'mandatory',    TRUE,  FALSE),
('stage_2', 'Qualifications', 'SAQCC / SAQA Registration',              'person',  'conditional',  TRUE,  TRUE),
('stage_2', 'Safety',         'Working at Heights Certificate',         'person',  'conditional',  TRUE,  TRUE),
('stage_2', 'Safety',         'First Aid Certificate',                  'person',  'conditional',  TRUE,  TRUE),
('stage_2', 'Safety',         'Induction Certificate',                  'person',  'mandatory',    TRUE,  FALSE),
('stage_2', 'Medical',        'Medical Fitness Certificate',            'person',  'mandatory',    TRUE,  TRUE)
;
