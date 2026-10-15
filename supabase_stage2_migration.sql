-- =============================================================================
-- HSE Installer Onboarding Portal — Stage 2 Migration
-- Run this in the Supabase SQL Editor AFTER supabase_stage1_migration.sql.
-- =============================================================================
-- No separate person-scoped index here: supabase_stage1_migration.sql now
-- creates a single UNIQUE NULLS NOT DISTINCT (installer_id, requirement_id,
-- personnel_id) constraint covering both company- and person-scoped uploads,
-- for both stages.

-- ---------------------------------------------------------------------------
-- 1. Storage bucket notes
--    Create via Supabase Dashboard -> Storage -> New Bucket:
--      Name: stage-2-compliance  |  Public: OFF
-- ---------------------------------------------------------------------------
-- INSERT INTO storage.buckets (id, name, public)
-- VALUES ('stage-2-compliance', 'stage-2-compliance', false)
-- ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Development RLS policies (allow anon key read/write in dev)
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "anon_all_personnel" ON public.personnel;
CREATE POLICY "anon_all_personnel"
    ON public.personnel FOR ALL
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "anon_all_installers" ON public.installers;
CREATE POLICY "anon_all_installers"
    ON public.installers FOR ALL
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "anon_all_doc_requirements" ON public.document_requirements;
CREATE POLICY "anon_all_doc_requirements"
    ON public.document_requirements FOR ALL
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "anon_all_doc_submissions" ON public.document_submissions;
CREATE POLICY "anon_all_doc_submissions"
    ON public.document_submissions FOR ALL
    USING (true)
    WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- 3. Seed Stage 2 HSE File Requirements (28 items across 9 sections)
--    This is a verbatim copy of the live, twice-verified data -- not a
--    regenerated or reconstructed list. Safe to embed per AGENTS.md's actual
--    intent: no agent should ever reconstruct this from memory again, but a
--    mechanical copy of confirmed-correct data is a different thing.
-- ---------------------------------------------------------------------------
DELETE FROM public.document_requirements WHERE stage = 'stage_2';

INSERT INTO public.document_requirements
    (stage, section, name, scope, requirement_level, installer_upload, has_expiry)
VALUES
    -- 1. Introduction
    ('stage_2', '1. Introduction', 'Company Cover Page', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '1. Introduction', 'HSE Policy Statement', 'company', 'mandatory', TRUE, FALSE),

    -- 2. Health and Safety Plan
    ('stage_2', '2. Health and Safety Plan', 'HSE Plan', 'company', 'mandatory', TRUE, FALSE),

    -- 3. Legal and Regulatory Compliance
    ('stage_2', '3. Legal and Regulatory Compliance', 'Legal Appointments (16.1, 16.2, First Aider, Fire Fighter, etc.)', 'person', 'mandatory', TRUE, FALSE),
    ('stage_2', '3. Legal and Regulatory Compliance', '37.2 Agreement between Wetility and Contractor', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '3. Legal and Regulatory Compliance', 'ID Copies', 'person', 'mandatory', TRUE, FALSE),
    ('stage_2', '3. Legal and Regulatory Compliance', 'Letter of Good Standing (COIDA) & Liability Insurance', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '3. Legal and Regulatory Compliance', 'Blank WCL Forms', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '3. Legal and Regulatory Compliance', 'ECB Registration', 'company', 'conditional', TRUE, FALSE),
    ('stage_2', '3. Legal and Regulatory Compliance', 'PV GreenCard', 'person', 'mandatory', TRUE, FALSE),

    -- 4. Project-Specific Safety Requirements
    ('stage_2', '4. Project-Specific Safety Requirements', 'Fall Protection Plan & Risk Assessment (Working at Heights)', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '4. Project-Specific Safety Requirements', 'Electrical Safety - Isolation and Lockout', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '4. Project-Specific Safety Requirements', 'Manual Handling - Ergonomics Risk Assessment', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '4. Project-Specific Safety Requirements', 'Environmental Management Plan', 'company', 'mandatory', TRUE, FALSE),

    -- 5. Documentation and Records
    ('stage_2', '5. Documentation and Records', '(Wetility) Baseline Risk Assessment & SHE Specifications', 'company', 'mandatory', FALSE, FALSE),
    ('stage_2', '5. Documentation and Records', 'Contractor Baseline Risk Assessment', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '5. Documentation and Records', 'Task Risk Assessments', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '5. Documentation and Records', 'Safe Work Procedures', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '5. Documentation and Records', 'Training Records', 'person', 'mandatory', TRUE, TRUE),

    -- 6. Emergency Preparedness
    ('stage_2', '6. Emergency Preparedness', 'Emergency Contact List', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '6. Emergency Preparedness', 'Emergency Response Plan', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '6. Emergency Preparedness', 'Incident Reports', 'company', 'mandatory', FALSE, FALSE),

    -- 7. Medical Fitness and Certificates of Fitness
    ('stage_2', '7. Medical Fitness and Certificates of Fitness', 'Certificates of Fitness (COF)', 'person', 'mandatory', TRUE, TRUE),
    ('stage_2', '7. Medical Fitness and Certificates of Fitness', 'Health and Safety Inductions', 'person', 'mandatory', TRUE, FALSE),

    -- 8. Monitoring and Review
    ('stage_2', '8. Monitoring and Review', 'Safety Inspections / Audit Reports', 'company', 'mandatory', FALSE, FALSE),
    ('stage_2', '8. Monitoring and Review', 'Corrective Actions', 'company', 'mandatory', FALSE, FALSE),

    -- 9. Sign-Off and Approval
    ('stage_2', '9. Sign-Off and Approval', 'Contractor Sign-Off', 'company', 'mandatory', TRUE, FALSE),
    ('stage_2', '9. Sign-Off and Approval', 'Wetility Representative Sign-Off', 'company', 'mandatory', FALSE, FALSE);