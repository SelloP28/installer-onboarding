## Database & Migrations Rule
- **Live data is authoritative, project-wide**:
  The Supabase schema and the `document_requirements` table (Stage 1 and Stage 2)
  already reflect correct, human-confirmed project state.
  - **Do NOT** generate, invent, or insert mock/seed data into any table that
    already holds real requirement, bucket, or schema data -- for
    `document_requirements` specifically, or any other established table.
  - **Always** query the live table directly (`supabase.table(...).select("*")...`)
    rather than assuming or re-deriving its contents.
  - Future SQL migrations focus strictly on schema structures (tables, columns,
    indexes, constraints, triggers, RLS policies) and storage configuration --
    never on repopulating data that should already exist.
  - This does not apply to isolated unit test fixtures, which may legitimately
    use mock data as long as they don't write to the live Supabase tables.