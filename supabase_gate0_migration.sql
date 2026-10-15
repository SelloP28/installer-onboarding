-- =============================================================================
-- Gate 0 Migration — run AFTER supabase_schema.sql
-- Adds: prequalification_forms table, signature_method on document_submissions,
--       NDA seed row in document_requirements, and open-access RLS for gate-0
--       new-registration flow (no auth token exists yet at that point).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Add signature_method column to document_submissions
--    (reserved for future canvas e-signature integration)
-- ---------------------------------------------------------------------------
ALTER TABLE public.document_submissions
    ADD COLUMN IF NOT EXISTS signature_method TEXT DEFAULT 'typed'
        CHECK (signature_method IN ('typed', 'canvas', 'docusign', 'uploaded'));

-- ---------------------------------------------------------------------------
-- 2. prequalification_forms
--    One row per installer — structured storage of every Gate 0 form field.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.prequalification_forms (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    installer_id                UUID NOT NULL UNIQUE
                                    REFERENCES public.installers (id) ON DELETE CASCADE,

    -- Section 1: Company Information
    cipc_reg_number             TEXT,
    tax_clearance_number        TEXT,
    bbbee_level                 TEXT,
    physical_address            TEXT,
    years_in_business           INTEGER,

    -- Section 2: Contact Person
    contact_name                TEXT,
    contact_position            TEXT,
    contact_phone               TEXT,
    contact_email               TEXT,

    -- Section 3: Track Record
    prior_project_count         INTEGER,
    project_sizes               TEXT,
    geographic_areas            TEXT[],          -- PostgreSQL native array

    -- Section 4: Technical Capability
    bop_capability              BOOLEAN,
    maintenance_capability      BOOLEAN,

    -- Section 5: Electrical Compliance
    dol_reg_number              TEXT,
    wiremans_licence_number     TEXT,
    coc_personnel               JSONB,           -- [{name, reg_number}, ...]
    pv_greencard                BOOLEAN,

    -- Section 6: Compliance Documentation (attestations)
    good_standing_attached      BOOLEAN,
    liability_insurance_attached BOOLEAN,
    hse_policy_attached         BOOLEAN,
    hse_documentation_available BOOLEAN,

    -- Section 7: Tools & Equipment
    tools_available             BOOLEAN,
    tool_inspection_routine     BOOLEAN,

    -- Section 8: Declaration
    declaration_name            TEXT,
    declaration_position        TEXT,
    declaration_signature       TEXT,            -- typed name (canvas to follow)
    signature_method            TEXT DEFAULT 'typed',

    submitted_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_preq_installer_id
    ON public.prequalification_forms (installer_id);

-- Auto-update updated_at on every row change
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_preq_updated_at ON public.prequalification_forms;
CREATE TRIGGER trg_preq_updated_at
    BEFORE UPDATE ON public.prequalification_forms
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 3. RLS for prequalification_forms — service_role only
-- ---------------------------------------------------------------------------
ALTER TABLE public.prequalification_forms ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all_preq_forms" ON public.prequalification_forms;
CREATE POLICY "service_role_all_preq_forms"
    ON public.prequalification_forms FOR ALL
    USING (auth.role() = 'service_role');

-- ---------------------------------------------------------------------------
-- 4. Seed: NDA requirement for gate_0
-- ---------------------------------------------------------------------------
INSERT INTO public.document_requirements
    (stage, section, name, scope, requirement_level, installer_upload, has_expiry)
VALUES
    ('gate_0', 'Legal', 'Signed Non-Disclosure Agreement (NDA)', 'company', 'mandatory', TRUE, FALSE),
    ('gate_0', 'Legal', 'Pre-Qualification Form',                'company', 'mandatory', FALSE, FALSE)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 5. Storage bucket: gate-0-documents
--    Run this in the Supabase Storage section OR via the Management API.
--    The SQL below uses the storage schema helper (available in Supabase).
-- ---------------------------------------------------------------------------
-- INSERT INTO storage.buckets (id, name, public)
-- VALUES ('gate-0-documents', 'gate-0-documents', false)
-- ON CONFLICT (id) DO NOTHING;
--
-- Uncomment the INSERT above if your Supabase project exposes the storage schema.
-- Otherwise create the bucket manually:
--   Supabase Dashboard → Storage → New Bucket
--   Name: gate-0-documents  |  Public: OFF
