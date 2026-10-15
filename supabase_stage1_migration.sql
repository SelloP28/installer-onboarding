-- =============================================================================
-- HSE Installer Onboarding Portal — Stage 1 Migration
-- Run this in the Supabase SQL Editor.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Ensure unique constraint on document_submissions for upserts
--    Unified constraint handling both company and personnel documents cleanly.
-- ---------------------------------------------------------------------------
ALTER TABLE public.document_submissions 
DROP CONSTRAINT IF EXISTS doc_subs_unique;

ALTER TABLE public.document_submissions 
ADD CONSTRAINT doc_subs_unique 
UNIQUE NULLS NOT DISTINCT (installer_id, requirement_id, personnel_id);

-- ---------------------------------------------------------------------------
-- 2. Storage bucket: stage-1-compliance
--    Run this in the Supabase Storage section OR via the Management API.
-- ---------------------------------------------------------------------------
-- INSERT INTO storage.buckets (id, name, public)
-- VALUES ('stage-1-compliance', 'stage-1-compliance', false)
-- ON CONFLICT (id) DO NOTHING;
--
-- Manual bucket creation:
--   Supabase Dashboard → Storage → New Bucket
--   Name: stage-1-compliance  |  Public: OFF
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 3. Seed Stage 1 document requirements
-- ---------------------------------------------------------------------------
INSERT INTO public.document_requirements
    (stage, section, name, scope, requirement_level, installer_upload, has_expiry)
VALUES
    ('stage_1', 'Legal',      'CIPC (Company Registration)',            'company', 'mandatory', TRUE, FALSE),
    ('stage_1', 'Insurance',  'Public Liability Insurance',             'company', 'mandatory', TRUE, TRUE),
    ('stage_1', 'Insurance',  'Letter of Good Standing (COIDA)',        'company', 'mandatory', TRUE, TRUE),
    ('stage_1', 'Electrical', 'Wireman''s Licence',                     'company', 'mandatory', TRUE, TRUE),
    ('stage_1', 'Electrical', 'Electrical Contractor 6.4 Registration', 'company', 'mandatory', TRUE, TRUE),
    ('stage_1', 'HSE',        '37.2 Agreement between Wetility and Contractor', 'company', 'mandatory', TRUE, FALSE)
ON CONFLICT DO NOTHING;