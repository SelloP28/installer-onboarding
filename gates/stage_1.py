"""
gates/stage_1.py — Stage 1: Company-Level Compliance Document Uploads
=====================================================================
Implements the Stage 1 installer document checklist.

Requirements:
1. Query document_requirements where stage='stage_1' and installer_upload=true,
   and render one st.file_uploader per row returned. (Reusable rendering logic
   designed so Stage 2 can reuse it).
2. Each upload inserts a document_submissions row (status='pending_review')
   against its requirement_id in a 'stage-1-compliance' storage bucket.
3. Progress indicator: approved submissions vs. total mandatory Stage 1 rows.
4. When every mandatory Stage 1 row is 'approved', update current_stage='stage_2'.
"""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Any

import streamlit as st
from supabase import Client


# =============================================================================
# Public Stage 1 Renderer
# =============================================================================

def render(supabase: Client, installer: dict) -> None:
    """
    Render Stage 1: Company Documents onboarding interface.

    Parameters
    ----------
    supabase : Client
        Initialised Supabase client.
    installer : dict
        Installer row from the database (current_stage='stage_1').
    """
    render_document_checklist(
        supabase=supabase,
        installer=installer,
        stage="stage_1",
        bucket_name="stage-1-compliance",
        next_stage="stage_2",
        scope="company",
        stage_title="Stage 1 — Company Compliance Documents",
        stage_subtitle=(
            "Upload company-level legal, safety, and operational documentation. "
            "All mandatory documents must be approved by the compliance team "
            "to advance to Stage 2."
        ),
    )


# =============================================================================
# Reusable Document Checklist Engine (Reused across Stage 1 & Stage 2)
# =============================================================================

def render_document_checklist(
    supabase: Client,
    installer: dict,
    stage: str,
    bucket_name: str,
    next_stage: str,
    scope: str = "company",
    personnel_id: str | None = None,
    stage_title: str = "Compliance Documents",
    stage_subtitle: str = "",
) -> None:
    """
    Generic, requirements-driven document checklist renderer.
    Dynamically renders upload widgets for every requirement returned by Supabase.

    Parameters
    ----------
    supabase : Client
        Supabase client.
    installer : dict
        Installer record dictionary.
    stage : str
        'stage_1' or 'stage_2'.
    bucket_name : str
        Target storage bucket (e.g. 'stage-1-compliance').
    next_stage : str
        Next stage when all mandatory requirements are approved ('stage_2' or 'complete').
    scope : str
        'company' or 'person'.
    personnel_id : str | None
        Optional personnel ID when rendering for a specific team member in Stage 2.
    stage_title : str
        Header title to display.
    stage_subtitle : str
        Description caption.
    """
    installer_id: str = installer["id"]
    company_name: str = installer.get("company_name", "Installer")

    # ── Page Header ──────────────────────────────────────────────────────────
    st.header(stage_title)
    if stage_subtitle:
        st.markdown(stage_subtitle)

    st.caption(f"Applicant: **{company_name}** | Stage: `{stage}`")
    st.markdown("---")

    # ── 1. Dynamic Query for Document Requirements ───────────────────────────
    requirements = _fetch_requirements(supabase, stage=stage, scope=scope)
    if not requirements:
        st.warning(
            f"No document requirements found for `{stage}` in the database. "
            "Please ensure `supabase_schema.sql` seed rows have been executed.",
            icon="⚠️",
        )
        return

    # ── 2. Fetch Existing Submissions for Installer ───────────────────────────
    submissions = _fetch_submissions(supabase, installer_id=installer_id, personnel_id=personnel_id)

    # ── 3. Calculate Progress & Check Advancement ─────────────────────────────
    mandatory_reqs = [r for r in requirements if r.get("requirement_level") == "mandatory"]
    total_mandatory = len(mandatory_reqs)

    approved_mandatory = [
        r for r in mandatory_reqs
        if submissions.get(r["id"], {}).get("status") == "approved"
    ]
    approved_count = len(approved_mandatory)

    pending_count = sum(
        1 for r in requirements
        if submissions.get(r["id"], {}).get("status") == "pending_review"
    )

    rejected_count = sum(
        1 for r in requirements
        if submissions.get(r["id"], {}).get("status") == "rejected"
    )

    # ── 4. Stage Advancement Guard (Requirement 4) ────────────────────────────
    # When every mandatory row is 'approved', update current_stage to next_stage
    all_mandatory_approved = (total_mandatory > 0 and approved_count == total_mandatory)

    if all_mandatory_approved:
        if installer.get("current_stage") == stage:
            _advance_stage(supabase, installer_id, next_stage)
            installer["current_stage"] = next_stage

        st.success(
            f"🎉 **Congratulations! All {total_mandatory} mandatory {stage.replace('_', ' ').title()} "
            f"documents have been approved.** You have advanced to **{next_stage.replace('_', ' ').title()}**!",
            icon="🚀",
        )
        st.balloons()
        if st.button(f"➡️ Proceed to {next_stage.replace('_', ' ').title()}", type="primary", key=f"btn_next_{stage}"):
            st.rerun()
        st.markdown("---")

    # ── 5. Progress Indicator (Requirement 3) ─────────────────────────────────
    progress_val = (approved_count / total_mandatory) if total_mandatory > 0 else 1.0

    col_prog, col_stats = st.columns([3, 2])
    with col_prog:
        st.markdown(f"#### Mandatory Compliance Progress: **{approved_count} / {total_mandatory} Approved**")
        st.progress(progress_val)
    with col_stats:
        m1, m2, m3 = st.columns(3)
        m1.metric("Approved", f"{approved_count}/{total_mandatory}", delta=None)
        m2.metric("Under Review", pending_count)
        m3.metric("Action Required", rejected_count)

    st.markdown("---")

    # ── 6. Group by Section and Render Dynamic Upload Widgets ────────────────
    # Group requirements by logical section (e.g. Legal, Insurance, HSE, Banking)
    sections: dict[str, list[dict]] = {}
    for req in requirements:
        sec = req.get("section", "General")
        sections.setdefault(sec, []).append(req)

    for section_name, sec_reqs in sections.items():
        with st.expander(f"📁 {section_name} ({len(sec_reqs)} documents)", expanded=True):
            for req in sec_reqs:
                _render_requirement_card(
                    supabase=supabase,
                    installer=installer,
                    req=req,
                    submission=submissions.get(req["id"]),
                    bucket_name=bucket_name,
                    personnel_id=personnel_id,
                )


# =============================================================================
# Helper: Individual Requirement Upload Card
# =============================================================================

def _render_requirement_card(
    supabase: Client,
    installer: dict,
    req: dict,
    submission: dict | None,
    bucket_name: str,
    personnel_id: str | None,
) -> None:
    """Render a single requirement row with status badge, uploader, and expiry input."""
    req_id = req["id"]
    req_name = req["name"]
    is_mandatory = req.get("requirement_level") == "mandatory"
    has_expiry = bool(req.get("has_expiry", False))

    status = submission.get("status") if submission else "not_uploaded"
    rejection_reason = submission.get("rejection_reason") if submission else None
    expiry_date_val = submission.get("expiry_date") if submission else None

    # Card container
    with st.container():
        col_info, col_status = st.columns([3, 1])

        with col_info:
            mand_badge = "🔴 **Mandatory**" if is_mandatory else "⚪ *Conditional / Optional*"
            expiry_badge = "📅 *Requires Expiry Date*" if has_expiry else ""
            st.markdown(f"##### {req_name}")
            st.caption(f"{mand_badge} | Section: `{req.get('section', 'General')}` {('| ' + expiry_badge) if expiry_badge else ''}")

        with col_status:
            if status == "approved":
                st.success("✅ **Approved**", icon="✅")
            elif status == "pending_review":
                st.warning("⏳ **Under Review**", icon="⏳")
            elif status == "rejected":
                st.error("❌ **Rejected**", icon="❌")
            else:
                st.info("⚪ **Not Uploaded**", icon="📄")

        # Rejection feedback alert
        if status == "rejected" and rejection_reason:
            st.error(f"**Correction Required:** {rejection_reason}", icon="⚠️")

        # If already approved, show details without upload widget (unless user wants to replace)
        if status == "approved":
            st.caption(f"File stored at: `{submission.get('file_path', '')}`")
            if expiry_date_val:
                st.caption(f"Recorded Expiry Date: **{expiry_date_val}**")
            st.markdown("<hr style='margin: 8px 0; border: 0.5px solid #eee;'>", unsafe_allow_html=True)
            return

        # Upload inputs for pending_review, rejected, or unsubmitted
        col_file, col_exp, col_btn = st.columns([3, 2, 1])

        widget_key_suffix = f"{req_id}_{personnel_id or 'co'}"

        with col_file:
            uploaded_file = st.file_uploader(
                label=f"Upload {req_name}",
                type=["pdf", "png", "jpg", "jpeg"],
                key=f"file_{widget_key_suffix}",
                label_visibility="collapsed",
                help=f"Select document file for {req_name} (PDF, JPG, PNG up to 10 MB)",
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
                    key=f"exp_{widget_key_suffix}",
                    help="Document valid until date",
                )
            else:
                st.write("")  # Spacing alignment

        with col_btn:
            st.write("")  # Vertical alignment padding
            upload_btn = st.button(
                "Upload",
                key=f"btn_up_{widget_key_suffix}",
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

        st.markdown("<hr style='margin: 8px 0; border: 0.5px solid #eee;'>", unsafe_allow_html=True)


# =============================================================================
# Upload & Persistence Logic (Requirement 2)
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
    """Upload document to Supabase Storage bucket and upsert document_submissions row."""
    # Validate file size (10 MB limit)
    if uploaded_file.size > 10 * 1024 * 1024:
        st.error(f"File '{uploaded_file.name}' exceeds the 10 MB size limit.", icon="❌")
        return

    # Clean filename
    clean_name = re.sub(r"[^a-zA-Z0-9_\.-]", "_", uploaded_file.name)
    person_prefix = f"person_{personnel_id}/" if personnel_id else ""
    storage_path = f"{installer_id}/{person_prefix}{requirement_id}_{clean_name}"

    file_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
    content_type = uploaded_file.type or "application/octet-stream"

    with st.spinner(f"Uploading '{uploaded_file.name}' to compliance vault…"):
        # 1. Upload to Supabase Storage bucket
        try:
            # Ensure bucket exists or upload directly
            supabase.storage.from_(bucket_name).upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": content_type, "upsert": "true"},
            )
        except Exception as storage_exc:
            st.error(f"Storage upload error: {storage_exc}", icon="🚨")
            return

        # 2. Insert or upsert document_submissions row (status='pending_review')
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
        
        try:
            supabase.table("document_submissions").upsert(
                sub_payload, on_conflict="installer_id,requirement_id,personnel_id"
            ).execute()
        except Exception as db_exc:
            st.error(f"Database submission record error: {db_exc}", icon="🚨")
            return

    st.success(f"✅ '{uploaded_file.name}' uploaded successfully! Status: Under Review.")
    st.rerun()


# =============================================================================
# Database Helpers
# =============================================================================

def _fetch_requirements(supabase: Client, stage: str, scope: str | None = None) -> list[dict]:
    """Fetch all active installer_upload requirements for the given stage."""
    try:
        q = (
            supabase.table("document_requirements")
            .select("*")
            .eq("stage", stage)
            .eq("installer_upload", True)
            .order("section")
            .order("created_at")
        )
        if scope:
            q = q.eq("scope", scope)
        res = q.execute()
        return res.data or []
    except Exception as exc:
        st.error(f"Failed to fetch document requirements: {exc}")
        return []


def _fetch_submissions(
    supabase: Client,
    installer_id: str,
    personnel_id: str | None = None,
) -> dict[str, dict]:
    """Fetch existing submissions for the installer mapped by requirement_id."""
    try:
        q = (
            supabase.table("document_submissions")
            .select("*")
            .eq("installer_id", installer_id)
        )
        if personnel_id:
            q = q.eq("personnel_id", personnel_id)
        res = q.execute()
        rows = res.data or []
        return {r["requirement_id"]: r for r in rows}
    except Exception as exc:
        st.warning(f"Could not load previous document submissions: {exc}")
        return {}


def _advance_stage(supabase: Client, installer_id: str, next_stage: str) -> None:
    """Update installer current_stage in Supabase when all mandatory items are approved."""
    try:
        supabase.table("installers").update({
            "current_stage": next_stage,
            "current_status": "pending_review",
        }).eq("id", installer_id).execute()
    except Exception as exc:
        st.error(f"Could not update stage in database: {exc}")
