"""
gates/stage_2.py — Stage 2: Comprehensive HSE File & Personnel Roster
======================================================================
Implements the Stage 2 installer experience.

Flow
----
1. Company-scoped section documents (HSE Plan, Method Statement etc.) — grouped
   by ``section`` label — rendered via the shared ``render_document_checklist``
   engine from stage_1.py.
2. Personnel Roster — add / view team members stored in the ``personnel`` table.
3. Per-person document uploads — for each roster member, render the person-scoped
   requirements via ``render_document_checklist`` with their ``personnel_id``.
4. Combined progress bar — approved mandatory installer-upload rows across BOTH
   company and every registered team member, divided by total such rows.
5. On 100 % approval → advance installer to ``current_stage='complete'`` and
   display the final cleared-for-allocation confirmation screen.

Architecture note
-----------------
Progress counting deliberately filters on ``installer_upload = TRUE`` (matching
what is rendered). Several Stage 2 rows are ``installer_upload = FALSE``
(Wetility-issued baseline documents, Wetility sign-off, and post-onboarding
items). Those rows are invisible to the installer and are excluded from both
the rendered checklists and the progress calculation.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

import streamlit as st
from supabase import Client

from gates.stage_1 import (
    render_document_checklist,
    _fetch_requirements,
    _fetch_submissions,
    _advance_stage,
)


# =============================================================================
# Public Stage 2 Renderer
# =============================================================================

def render(supabase: Client, installer: dict) -> None:
    """
    Render Stage 2: Comprehensive HSE File & Personnel Documents.

    Parameters
    ----------
    supabase : Client
        Initialised Supabase client.
    installer : dict
        Installer row from the database (current_stage='stage_2').
    """
    installer_id: str = installer["id"]
    company_name: str = installer.get("company_name", "Installer")

    st.header("Stage 2 — Comprehensive HSE File & Personnel Roster")
    st.markdown(
        "Complete your company's HSE documentation file and register all site "
        "personnel with their individual compliance documents. All items marked "
        "**🔴 Mandatory** and flagged as installer-upload must be submitted before "
        "final clearance."
    )
    st.caption(f"Applicant: **{company_name}** | Stage: `stage_2`")
    st.markdown("---")

    # ── Section tabs ──────────────────────────────────────────────────────────
    tab_overview, tab_company, tab_personnel = st.tabs([
        "📊 Overall Progress",
        "🏢 Company HSE Documents",
        "👷 Personnel Roster & Documents",
    ])

    with tab_overview:
        _render_overall_progress(supabase, installer)

    with tab_company:
        _render_company_documents(supabase, installer)

    with tab_personnel:
        _render_personnel_section(supabase, installer)


# =============================================================================
# Section 1 — Overall Combined Progress (Requirement 6 & 7)
# =============================================================================

def _render_overall_progress(supabase: Client, installer: dict) -> None:
    """
    Calculate and display combined progress across ALL company-scoped
    and person-scoped mandatory installer-upload Stage 2 documents.

    Advancement to 'complete' fires here when the denominator > 0 and
    all items are approved.
    """
    installer_id: str = installer["id"]

    st.subheader("📊 Stage 2 — Overall Compliance Progress")
    st.markdown(
        "Progress counts only rows where **requirement_level = 'mandatory'** "
        "**AND installer_upload = TRUE**. Wetility-issued, Wetility sign-off, "
        "and post-onboarding items are excluded from both the progress bar and "
        "the rendered checklists."
    )

    # ── Company-scoped mandatory installer-upload requirements ────────────────
    company_reqs = _fetch_requirements(supabase, "stage_2", scope="company")
    mandatory_company = [r for r in company_reqs if r.get("requirement_level") == "mandatory"]

    # Company submissions (no personnel_id filter)
    company_subs = _fetch_submissions(supabase, installer_id=installer_id, personnel_id=None)
    approved_company = sum(
        1 for r in mandatory_company
        if company_subs.get(r["id"], {}).get("status") == "approved"
    )

    # ── Person-scoped mandatory installer-upload requirements ─────────────────
    person_reqs = _fetch_requirements(supabase, "stage_2", scope="person")
    mandatory_person_per_member = [r for r in person_reqs if r.get("requirement_level") == "mandatory"]

    # Roster members
    roster = _fetch_personnel(supabase, installer_id)

    total_person_mandatory = len(mandatory_person_per_member) * len(roster)
    approved_person = 0
    for person in roster:
        person_subs = _fetch_submissions(
            supabase, installer_id=installer_id, personnel_id=person["id"]
        )
        approved_person += sum(
            1 for r in mandatory_person_per_member
            if person_subs.get(r["id"], {}).get("status") == "approved"
        )

    # ── Totals ────────────────────────────────────────────────────────────────
    total_mandatory = len(mandatory_company) + total_person_mandatory
    total_approved = approved_company + approved_person
    progress_pct = (total_approved / total_mandatory) if total_mandatory > 0 else 0.0

    # ── Metrics display ───────────────────────────────────────────────────────
    col_bar, col_m1, col_m2, col_m3 = st.columns([3, 1, 1, 1])

    with col_bar:
        st.markdown(
            f"#### **{total_approved} / {total_mandatory}** mandatory items approved "
            f"({progress_pct * 100:.0f}%)"
        )
        st.progress(progress_pct)

    col_m1.metric("Company Docs", f"{approved_company}/{len(mandatory_company)}")
    col_m2.metric("Personnel Docs", f"{approved_person}/{total_person_mandatory}")
    col_m3.metric("Team Members", len(roster))

    if roster:
        st.markdown("##### Per-Person Breakdown")
        for person in roster:
            person_subs = _fetch_submissions(
                supabase, installer_id=installer_id, personnel_id=person["id"]
            )
            p_approved = sum(
                1 for r in mandatory_person_per_member
                if person_subs.get(r["id"], {}).get("status") == "approved"
            )
            p_total = len(mandatory_person_per_member)
            p_pct = (p_approved / p_total) if p_total > 0 else 0.0
            icon = "✅" if p_approved == p_total and p_total > 0 else "⏳"
            st.markdown(
                f"{icon} **{person.get('full_name', 'Unknown')}** "
                f"({person.get('role', '')}) — "
                f"`{p_approved}/{p_total}` docs approved"
            )
    elif total_mandatory == 0:
        st.info(
            "No mandatory installer-upload documents are seeded for Stage 2 yet. "
            "Run `supabase_stage2_migration.sql` to populate the requirements.",
            icon="⚠️",
        )

    st.markdown("---")

    # ── Advancement to 'complete' ─────────────────────────────────────────────
    # Guard: only advance if there is at least one mandatory item and all are done
    all_complete = total_mandatory > 0 and total_approved == total_mandatory

    if all_complete and installer.get("current_stage") == "stage_2":
        _advance_stage(supabase, installer_id, "complete")
        installer["current_stage"] = "complete"

    if installer.get("current_stage") == "complete":
        _render_completion_screen(installer)
    elif all_complete:
        # Stage was already 'complete' in DB but session dict is stale
        _render_completion_screen(installer)


# =============================================================================
# Section 2 — Company-Scoped HSE Documents (Requirements 1 & 2)
# =============================================================================

def _render_company_documents(supabase: Client, installer: dict) -> None:
    """
    Render company-scoped Stage 2 document requirements, grouped by section,
    reusing the ``render_document_checklist`` engine from stage_1.py.
    The sections here map to the HSE file structure (Introduction, H&S Plan, etc.).
    """
    st.subheader("🏢 Company HSE File Documents")
    st.markdown(
        "Upload company-level documents that form the body of the HSE file. "
        "Documents are grouped by their HSE file section. "
        "Items issued by Wetility or completed post-onboarding are not shown here."
    )

    company_reqs = _fetch_requirements(supabase, "stage_2", scope="company")
    if not company_reqs:
        st.info(
            "No company-scoped Stage 2 requirements are currently seeded. "
            "Run `supabase_stage2_migration.sql` to populate them.",
            icon="ℹ️",
        )
        return

    installer_id: str = installer["id"]
    company_subs = _fetch_submissions(supabase, installer_id=installer_id, personnel_id=None)

    # Group requirements by section (preserving natural order from DB)
    sections: dict[str, list[dict]] = {}
    for req in company_reqs:
        sec = req.get("section", "General")
        sections.setdefault(sec, []).append(req)

    for section_name, sec_reqs in sections.items():
        # Count status within this section for the expander badge
        approved = sum(
            1 for r in sec_reqs
            if company_subs.get(r["id"], {}).get("status") == "approved"
        )
        pending = sum(
            1 for r in sec_reqs
            if company_subs.get(r["id"], {}).get("status") == "pending_review"
        )
        rejected = sum(
            1 for r in sec_reqs
            if company_subs.get(r["id"], {}).get("status") == "rejected"
        )
        total = len(sec_reqs)

        if approved == total:
            badge = f"✅ {approved}/{total}"
        elif rejected > 0:
            badge = f"❌ {rejected} need attention"
        elif pending > 0:
            badge = f"⏳ {pending} under review"
        else:
            badge = f"📤 {total} to upload"

        with st.expander(
            f"📁 {section_name}  —  {badge}",
            expanded=(rejected > 0 or (pending == 0 and approved < total)),
        ):
            for req in sec_reqs:
                _render_requirement_card_inline(
                    supabase=supabase,
                    installer=installer,
                    req=req,
                    submission=company_subs.get(req["id"]),
                    bucket_name="stage-2-compliance",
                    personnel_id=None,
                )


# =============================================================================
# Section 3 — Personnel Roster & Per-Person Documents (Requirements 3–5)
# =============================================================================

def _render_personnel_section(supabase: Client, installer: dict) -> None:
    """
    Render the personnel roster and per-person document upload interface.

    Sub-sections
    ------------
    A. Add team member form.
    B. Current roster list.
    C. Per-person document checklists.
    """
    installer_id: str = installer["id"]

    st.subheader("👷 Personnel Roster")
    st.markdown(
        "Register every individual who will work on Wetility solar installations. "
        "Each team member requires their own set of identity, qualification, and "
        "safety compliance documents."
    )

    # ── A. Add Team Member Form ───────────────────────────────────────────────
    with st.expander("➕ Add New Team Member", expanded=False):
        with st.form("add_personnel_form", clear_on_submit=True):
            st.markdown("#### Register Team Member")
            col_name, col_id = st.columns(2)
            full_name = col_name.text_input(
                "Full Name *",
                placeholder="e.g. Sipho Dlamini",
                key="new_person_name",
            )
            id_number = col_id.text_input(
                "SA ID Number *",
                placeholder="13-digit SA ID",
                key="new_person_id",
                max_chars=13,
            )
            role = st.selectbox(
                "Role *",
                options=[
                    "Electrician (CoC)",
                    "PV Installer",
                    "Roofer",
                    "Project Manager",
                    "HSE Officer",
                    "General Worker",
                    "Other",
                ],
                key="new_person_role",
            )

            submitted = st.form_submit_button("✅ Add Team Member", type="primary")
            if submitted:
                errors = []
                if not full_name.strip():
                    errors.append("Full Name is required.")
                if not id_number.strip():
                    errors.append("ID Number is required.")
                if not re.fullmatch(r"\d{13}", id_number.strip()):
                    errors.append("ID Number must be exactly 13 digits.")

                if errors:
                    for err in errors:
                        st.error(err, icon="❌")
                else:
                    _insert_personnel(
                        supabase=supabase,
                        installer_id=installer_id,
                        full_name=full_name.strip(),
                        id_number=id_number.strip(),
                        role=role,
                    )

    st.markdown("---")

    # ── B. Current Roster ─────────────────────────────────────────────────────
    roster = _fetch_personnel(supabase, installer_id)

    if not roster:
        st.info(
            "No team members registered yet. Use the form above to add the personnel "
            "who will be working on Wetility installations.",
            icon="👷",
        )
        return

    st.markdown(f"**{len(roster)} team member(s) registered**")

    # ── C. Per-Person Document Checklists ──────────────────────────────────────
    person_reqs = _fetch_requirements(supabase, "stage_2", scope="person")
    mandatory_per_person = [r for r in person_reqs if r.get("requirement_level") == "mandatory"]

    for person in roster:
        person_id = person["id"]
        person_name = person.get("full_name", "Unknown")
        person_role = person.get("role", "")
        person_id_no = person.get("id_number", "")

        # Count per-person progress for the expander badge
        person_subs = _fetch_submissions(
            supabase, installer_id=installer_id, personnel_id=person_id
        )
        p_approved = sum(
            1 for r in mandatory_per_person
            if person_subs.get(r["id"], {}).get("status") == "approved"
        )
        p_total = len(mandatory_per_person)
        p_rejected = sum(
            1 for r in mandatory_per_person
            if person_subs.get(r["id"], {}).get("status") == "rejected"
        )

        if p_approved == p_total and p_total > 0:
            progress_badge = f"✅ All {p_total} mandatory docs approved"
            is_expanded = False
        elif p_rejected > 0:
            progress_badge = f"❌ {p_rejected} doc(s) need correction"
            is_expanded = True
        else:
            progress_badge = f"📤 {p_approved}/{p_total} approved"
            is_expanded = True

        with st.expander(
            f"👤 **{person_name}** | {person_role}  —  {progress_badge}",
            expanded=is_expanded,
        ):
            # Person metadata header
            meta_col1, meta_col2, meta_col3 = st.columns(3)
            meta_col1.markdown(f"**Full Name:** {person_name}")
            meta_col2.markdown(f"**SA ID:** `{person_id_no}`")
            meta_col3.markdown(f"**Role:** {person_role}")

            # Delete button
            if st.button(
                f"🗑️ Remove {person_name} from roster",
                key=f"del_person_{person_id}",
                type="secondary",
                help="This will remove the team member and unlink their document submissions.",
            ):
                _delete_personnel(supabase, person_id)
                st.rerun()

            st.markdown("---")

            if not person_reqs:
                st.info("No person-scoped requirements seeded. Run the migration SQL.", icon="⚠️")
                continue

            # Per-person mini progress bar
            p_pct = (p_approved / p_total) if p_total > 0 else 0.0
            st.progress(p_pct, text=f"{p_approved}/{p_total} mandatory documents approved")

            st.markdown("##### Required Documents")

            # Group person requirements by section too
            p_sections: dict[str, list[dict]] = {}
            for req in person_reqs:
                sec = req.get("section", "General")
                p_sections.setdefault(sec, []).append(req)

            for sec_name, sec_reqs in p_sections.items():
                st.markdown(f"**{sec_name}**")
                for req in sec_reqs:
                    _render_requirement_card_inline(
                        supabase=supabase,
                        installer=installer,
                        req=req,
                        submission=person_subs.get(req["id"]),
                        bucket_name="stage-2-compliance",
                        personnel_id=person_id,
                    )

            st.markdown("")  # spacing


# =============================================================================
# Reusable requirement card — wraps stage_1's logic with Stage 2 bucket
# =============================================================================

def _render_requirement_card_inline(
    supabase: Client,
    installer: dict,
    req: dict,
    submission: dict | None,
    bucket_name: str,
    personnel_id: str | None,
) -> None:
    """
    Render a single Stage 2 requirement upload card.
    Mirrors ``_render_requirement_card`` from stage_1.py but inlined here
    so Stage 2 can evolve independently.
    """
    req_id = req["id"]
    req_name = req["name"]
    is_mandatory = req.get("requirement_level") == "mandatory"
    has_expiry = bool(req.get("has_expiry", False))

    status = submission.get("status") if submission else "not_uploaded"
    rejection_reason = submission.get("rejection_reason") if submission else None
    expiry_date_val = submission.get("expiry_date") if submission else None

    with st.container():
        col_info, col_status = st.columns([3, 1])

        with col_info:
            mand_badge = "🔴 **Mandatory**" if is_mandatory else "⚪ *Conditional*"
            expiry_note = " | 📅 *Requires Expiry Date*" if has_expiry else ""
            st.markdown(f"##### {req_name}")
            st.caption(f"{mand_badge}{expiry_note}")

        with col_status:
            if status == "approved":
                st.success("✅ Approved", icon="✅")
            elif status == "pending_review":
                st.warning("⏳ Under Review", icon="⏳")
            elif status == "rejected":
                st.error("❌ Rejected", icon="❌")
            else:
                st.info("📄 Not Uploaded", icon="📄")

        if status == "rejected" and rejection_reason:
            st.error(f"**Correction Required:** {rejection_reason}", icon="⚠️")

        if status == "approved":
            st.caption(f"Stored at: `{submission.get('file_path', '')}`")
            if expiry_date_val:
                st.caption(f"Expiry: **{expiry_date_val}**")
            st.markdown(
                "<hr style='margin: 6px 0; border: 0.5px solid #eee;'>",
                unsafe_allow_html=True,
            )
            return

        # Upload row
        widget_key_suffix = f"{req_id}_{personnel_id or 'co'}"
        col_file, col_exp, col_btn = st.columns([3, 2, 1])

        with col_file:
            uploaded_file = st.file_uploader(
                label=f"Upload {req_name}",
                type=["pdf", "png", "jpg", "jpeg"],
                key=f"file2_{widget_key_suffix}",
                label_visibility="collapsed",
                help=f"{req_name} (PDF, JPG, PNG — max 10 MB)",
            )

        doc_expiry: date | None = None
        with col_exp:
            if has_expiry:
                default_date = date.today()
                if expiry_date_val:
                    try:
                        default_date = date.fromisoformat(expiry_date_val)
                    except Exception:
                        pass
                doc_expiry = st.date_input(
                    label="Expiry Date",
                    value=default_date,
                    key=f"exp2_{widget_key_suffix}",
                    help="Document valid-until date",
                )
            else:
                st.write("")

        with col_btn:
            st.write("")
            upload_btn = st.button(
                "Upload",
                key=f"btn2_{widget_key_suffix}",
                type="secondary",
                use_container_width=True,
                disabled=(uploaded_file is None),
            )

        if upload_btn and uploaded_file is not None:
            _handle_document_upload(
                supabase=supabase,
                installer_id=installer["id"],
                requirement_id=req_id,
                uploaded_file=uploaded_file,
                bucket_name=bucket_name,
                personnel_id=personnel_id,
                expiry_date=doc_expiry,
            )

        st.markdown(
            "<hr style='margin: 6px 0; border: 0.5px solid #eee;'>",
            unsafe_allow_html=True,
        )


# =============================================================================
# Completion / Cleared-for-Allocation Screen (Requirement 7)
# =============================================================================

def _render_completion_screen(installer: dict) -> None:
    """Display the final confirmation screen when Stage 2 is complete."""
    company_name = installer.get("company_name", "Your Company")

    st.balloons()
    st.success(
        f"🎉 **{company_name} — Cleared for Allocation!**\n\n"
        "All mandatory Stage 2 HSE file documents and personnel compliance records "
        "have been submitted and approved by the Wetility compliance team. "
        "Your company is now cleared for project allocation.",
        icon="🚀",
    )

    col1, col2 = st.columns(2)
    col1.markdown(
        """
        #### ✅ What happens next?
        - The Wetility team will contact you regarding your first project allocation.
        - You will receive a confirmation email at the address on file.
        - Your compliance file will be reviewed annually — you will be notified when
          renewal is due.
        """
    )
    col2.markdown(
        """
        #### 📋 Your Compliance Summary
        - **Gate 0:** Pre-qualification & NDA ✅
        - **Stage 1:** Company legal & insurance documents ✅
        - **Stage 2:** HSE file & personnel documents ✅
        - **Status:** 🟢 Active — Cleared for Allocation
        """
    )

    st.info(
        "💾 **Keep your access link safe.** You can return at any time to view your "
        "submission status or update documents approaching their expiry dates.",
        icon="🔗",
    )


# =============================================================================
# Database Helpers — Personnel CRUD
# =============================================================================

def _fetch_personnel(supabase: Client, installer_id: str) -> list[dict]:
    """Fetch all personnel registered under this installer."""
    try:
        res = (
            supabase.table("personnel")
            .select("*")
            .eq("installer_id", installer_id)
            .order("created_at")
            .execute()
        )
        return res.data or []
    except Exception as exc:
        st.warning(f"Could not load personnel roster: {exc}")
        return []


def _insert_personnel(
    supabase: Client,
    installer_id: str,
    full_name: str,
    id_number: str,
    role: str,
) -> None:
    """Insert a new personnel record and trigger a page reload."""
    try:
        supabase.table("personnel").insert({
            "installer_id": installer_id,
            "full_name": full_name,
            "id_number": id_number,
            "role": role,
        }).execute()
        st.success(f"✅ **{full_name}** added to the roster.")
        st.rerun()
    except Exception as exc:
        st.error(f"Could not add team member: {exc}", icon="🚨")


def _delete_personnel(supabase: Client, person_id: str) -> None:
    """Remove a personnel record (cascades to their document_submissions)."""
    try:
        supabase.table("personnel").delete().eq("id", person_id).execute()
        st.toast("Team member removed from roster.", icon="🗑️")
    except Exception as exc:
        st.error(f"Could not remove team member: {exc}", icon="🚨")


# =============================================================================
# Document Upload Helper
# =============================================================================

def _handle_document_upload(
    supabase: Client,
    installer_id: str,
    requirement_id: str,
    uploaded_file,
    bucket_name: str,
    personnel_id: str | None,
    expiry_date: date | None,
) -> None:
    """Upload file to Supabase Storage and upsert document_submissions row."""
    if uploaded_file.size > 10 * 1024 * 1024:
        st.error(f"File '{uploaded_file.name}' exceeds the 10 MB size limit.", icon="❌")
        return

    clean_name = re.sub(r"[^a-zA-Z0-9_\.\-]", "_", uploaded_file.name)
    person_prefix = f"person_{personnel_id}/" if personnel_id else ""
    storage_path = f"{installer_id}/{person_prefix}{requirement_id}_{clean_name}"

    file_bytes = (
        uploaded_file.getvalue()
        if hasattr(uploaded_file, "getvalue")
        else uploaded_file.read()
    )
    content_type = uploaded_file.type or "application/octet-stream"

    with st.spinner(f"Uploading '{uploaded_file.name}' to compliance vault…"):
        try:
            supabase.storage.from_(bucket_name).upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": content_type, "upsert": "true"},
            )
        except Exception as storage_exc:
            st.error(f"Storage upload error: {storage_exc}", icon="🚨")
            return

        sub_payload = {
            "installer_id": installer_id,
            "requirement_id": requirement_id,
            "file_path": storage_path,
            "status": "pending_review",
            "rejection_reason": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "personnel_id": personnel_id,
            "expiry_date": expiry_date.isoformat() if expiry_date else None,
        }

        # For person-scoped documents the unique constraint must include personnel_id,
        # so we use a different conflict target.
        try:
            supabase.table("document_submissions").upsert(
                sub_payload,
                on_conflict="installer_id,requirement_id,personnel_id",
            ).execute()
        except Exception as db_exc:
            st.error(f"Database submission record error: {db_exc}", icon="🚨")
            return

    st.success(f"✅ '{uploaded_file.name}' uploaded. Status: Under Review.")
    st.rerun()
