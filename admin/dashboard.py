"""
admin/dashboard.py — Internal Compliance Admin Review Dashboard
=================================================================
Implements the compliance officer review interface (Prompt 5).

Requirements:
1. Queue 1 — Installers where current_status is 'needs_review' or 'needs_fixes':
   - Shows pre-qualification answers, NDA (signed URL), and which check(s) triggered the flag.
   - Admin action: Approve Gate 0 (advance to stage_1) or Request Fixes with feedback.
2. Queue 2 — Document submissions where status='pending_review' (Stage 1 onward):
   - Shows file (signed URL) and Approve / Reject-with-reason actions.
3. Audit Log:
   - On any decision, writes a row to audit_log table (installer_id, actor, action, timestamp)
     and updates the relevant record. Refresh so completed items drop off the queue.
4. Rejection Reason:
   - Stores reason on document_submissions.rejection_reason so the reminder engine can surface it.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import streamlit as st
from supabase import Client

logger = logging.getLogger("compliance.admin")


# =============================================================================
# Main Admin Dashboard Entry Point
# =============================================================================

def render_admin_dashboard(supabase: Client) -> None:
    """
    Render the main Compliance Admin dashboard with Queue 1, Queue 2,
    Installer Directory, Audit Trail, and OCR Calibration telemetry.
    """
    st.title("🛡️ Internal Compliance Admin Dashboard")
    st.caption("Manage applicant onboarding queues, review submissions, and inspect compliance audits.")

    # 1. Fetch queue counts for tabs
    q1_installers = _fetch_queue_1_installers(supabase)
    q2_submissions = _fetch_queue_2_submissions(supabase)

    q1_count = len(q1_installers)
    q2_count = len(q2_submissions)

    # 2. Render Tabs
    tab_q1, tab_q2, tab_directory, tab_audit, tab_telemetry = st.tabs([
        f"🚨 Queue 1: Gate 0 Reviews ({q1_count})",
        f"📋 Queue 2: Document Reviews ({q2_count})",
        "🏢 Installer Directory",
        "📜 Audit Trail",
        "🔬 Verification Telemetry",
    ])

    with tab_q1:
        render_queue_1_gate0(supabase, q1_installers)

    with tab_q2:
        render_queue_2_documents(supabase, q2_submissions)

    with tab_directory:
        _render_installer_directory(supabase)

    with tab_audit:
        _render_audit_log_tab(supabase)

    with tab_telemetry:
        _render_verification_telemetry_tab(supabase)


# =============================================================================
# Queue 1 — Gate 0 Pre-Qualification & Knock-out Reviews (Requirement 1)
# =============================================================================

def render_queue_1_gate0(supabase: Client, installers: list[dict]) -> None:
    """
    Queue 1: Installers where current_status is 'needs_review' or 'needs_fixes'.
    Displays pre-qualification answers, NDA signed URL, and triggered checks.
    """
    st.subheader("Queue 1 — Gate 0 Pre-Qualification Reviews")
    st.markdown(
        "Applicants flagged during Gate 0 automated checks (knock-outs, formatting issues, "
        "or NDA mismatches) requiring manual compliance officer review."
    )

    if not installers:
        st.success("🎉 **Queue 1 is clear!** No Gate 0 applications currently require review.", icon="✅")
        return

    # Filter selector within Queue 1
    filter_status = st.radio(
        "Filter by status:",
        ["All", "needs_review", "needs_fixes"],
        horizontal=True,
        key="q1_status_filter",
    )

    filtered = [
        inst for inst in installers
        if filter_status == "All" or inst.get("current_status") == filter_status
    ]

    for inst in filtered:
        installer_id = inst["id"]
        company_name = inst.get("company_name", "Unknown Company")
        status = inst.get("current_status", "needs_review")
        reason = inst.get("status_reason") or "Flagged during Gate 0 verification."
        email = inst.get("email", "")

        status_badge = "🔴 NEEDS REVIEW" if status == "needs_review" else "🟡 NEEDS FIXES"

        with st.expander(f"{status_badge} — **{company_name}** ({email})", expanded=True):
            col_flag, col_nda = st.columns([2, 1])

            # Fetch detailed verification telemetry to show exact check(s) triggered
            verif_entry = _fetch_latest_verification_log(supabase, installer_id)
            with col_flag:
                st.error(f"**Flag Trigger:** {reason}", icon="🚩")
                if verif_entry:
                    rr_raw = verif_entry.get("rules_result") or {}
                    vr_raw = verif_entry.get("vision_result") or {}
                    # Safely parse JSON strings back into Python dictionaries
                    rr = json.loads(rr_raw) if isinstance(rr_raw, str) else rr_raw
                    vr = json.loads(vr_raw) if isinstance(vr_raw, str) else vr_raw
                    knockouts = rr.get("knockouts") or []
                    rule_errs = rr.get("errors") or []
                    vision_errs = vr.get("errors") or []

                    if knockouts:
                        st.markdown("**🚨 Knock-Out Criteria Flagged:**")
                        for ko in knockouts:
                            st.markdown(f"- ⛔ `{ko}`")
                    if rule_errs:
                        st.markdown("**⚠️ Rules Validation Issues:**")
                        for re in rule_errs:
                            st.markdown(f"- 🔸 `{re}`")
                    if vision_errs:
                        st.markdown("**👁️ Vision & NDA Verification Flags:**")
                        for ve in vision_errs:
                            st.markdown(f"- 🔹 `{ve}`")

            with col_nda:
                # Resolve NDA file path from document_submissions or fallback
                nda_path = _get_nda_file_path(supabase, installer_id)
                nda_url = _get_signed_file_url(supabase, bucket="gate-0-documents", path=nda_path)
                if nda_url:
                    st.link_button("📄 Open Signed NDA (PDF)", nda_url, use_container_width=True)
                else:
                    st.caption(f"NDA file path: `{nda_path}` (storage link pending)")

            # Fetch structured prequalification answers
            preq_data = _fetch_prequalification_data(supabase, installer_id)
            if preq_data:
                st.markdown("#### Pre-Qualification Answers")
                t_comp, t_elec, t_track, t_decl = st.tabs([
                    "Company & Contact", "Electrical & CoC", "Track Record & Tools", "Declaration"
                ])

                with t_comp:
                    c1, c2 = st.columns(2)
                    c1.markdown(f"**CIPC Reg Number:** `{preq_data.get('cipc_reg_number', 'N/A')}`")
                    c1.markdown(f"**Tax Clearance:** `{preq_data.get('tax_clearance_number', 'N/A')}`")
                    c1.markdown(f"**B-BBEE Level:** `{preq_data.get('bbbee_level', 'N/A')}`")
                    c1.markdown(f"**Years in Business:** `{preq_data.get('years_in_business', 'N/A')}`")
                    c2.markdown(f"**Contact Person:** `{preq_data.get('contact_name', 'N/A')}`")
                    c2.markdown(f"**Position:** `{preq_data.get('contact_position', 'N/A')}`")
                    c2.markdown(f"**Phone:** `{preq_data.get('contact_phone', 'N/A')}`")
                    c2.markdown(f"**Physical Address:** `{preq_data.get('physical_address', 'N/A')}`")

                with t_elec:
                    c1, c2 = st.columns(2)
                    c1.markdown(f"**DoL Electrical Reg:** `{preq_data.get('dol_reg_number', 'BLANK / MISSING')}`")
                    c1.markdown(f"**Wireman's Licence:** `{preq_data.get('wiremans_licence_number', 'N/A')}`")
                    c1.markdown(f"**PV GreenCard:** `{'Yes' if preq_data.get('pv_greencard') else 'No'}`")

                    coc_raw = preq_data.get("coc_personnel")
                    coc_list = []
                    if isinstance(coc_raw, str):
                        try:
                            coc_list = json.loads(coc_raw)
                        except Exception:
                            pass
                    elif isinstance(coc_raw, list):
                        coc_list = coc_raw

                    c2.markdown("**CoC-Authorised Personnel:**")
                    if coc_list:
                        for idx, p in enumerate(coc_list):
                            c2.markdown(f"- **{p.get('name', 'Unnamed')}** (Reg: `{p.get('reg_number', 'None')}`)")
                    else:
                        c2.warning("⚠️ No CoC-authorised personnel listed!")

                with t_track:
                    c1, c2 = st.columns(2)
                    c1.markdown(f"**Prior Projects:** `{preq_data.get('prior_project_count', 0)}`")
                    c1.markdown(f"**Project Sizes:** `{preq_data.get('project_sizes', 'N/A')}`")
                    c1.markdown(f"**Areas:** `{', '.join(preq_data.get('geographic_areas') or [])}`")
                    c2.markdown(f"**Required Tools Available:** `{'Yes' if preq_data.get('tools_available') else 'NO (KNOCK-OUT)'}`")
                    c2.markdown(f"**Inspection Routine:** `{'Yes' if preq_data.get('tool_inspection_routine') else 'No'}`")
                    c2.markdown(f"**Letter of Good Standing:** `{'Yes' if preq_data.get('good_standing_attached') else 'No'}`")

                with t_decl:
                    c1, c2 = st.columns(2)
                    c1.markdown(f"**Declarant Name:** `{preq_data.get('declaration_name', 'N/A')}`")
                    c1.markdown(f"**Position:** `{preq_data.get('declaration_position', 'N/A')}`")
                    c2.markdown(f"**Typed Signature:** `{preq_data.get('declaration_signature', 'N/A')}`")
                    c2.markdown(f"**Submitted At:** `{preq_data.get('submitted_at', 'N/A')}`")
            else:
                st.info("Prequalification form data is being processed.")

            st.markdown("---")

            # ── Compliance Actions ────────────────────────────────────────────
            col_app, col_note, col_rej = st.columns([1, 2, 1])

            with col_app:
                st.write("")
                if st.button("✅ Approve Gate 0", key=f"q1_app_{installer_id}", type="primary", use_container_width=True):
                    _action_approve_gate_0(supabase, installer_id, company_name)
                    st.rerun()

            with col_note:
                q1_reason = st.text_input(
                    "Correction Feedback Note:",
                    value=reason,
                    key=f"q1_note_{installer_id}",
                    placeholder="Describe what installer must fix...",
                )

            with col_rej:
                st.write("")
                if st.button("⚠️ Request Fixes", key=f"q1_fix_{installer_id}", use_container_width=True):
                    _action_request_fixes_gate_0(supabase, installer_id, company_name, q1_reason)
                    st.rerun()


# =============================================================================
# Queue 2 — Stage 1+ Document Submissions (Requirement 2 & 4)
# =============================================================================

def render_queue_2_documents(supabase: Client, submissions: list[dict]) -> None:
    """
    Queue 2: Document submissions where status='pending_review' (Stage 1 onward).
    Displays the file (signed URL), metadata, and Approve / Reject-with-reason actions.
    """
    st.subheader("Queue 2 — Pending Document Submissions")
    st.markdown("Company and personnel compliance documents submitted by installers awaiting review.")

    if not submissions:
        st.success("🎉 **Queue 2 is clear!** No document submissions are currently pending review.", icon="✅")
        return

    for sub in submissions:
        sub_id = sub["id"]
        installer_id = sub.get("installer_id")
        inst = sub.get("installers") or {}
        req = sub.get("document_requirements") or {}

        if isinstance(inst, list):
            inst = inst[0] if inst else {}
        if isinstance(req, list):
            req = req[0] if req else {}

        if not inst and installer_id:
            inst = _fetch_installer_by_id(supabase, installer_id) or {}
        if not req and sub.get("requirement_id"):
            req = _fetch_requirement_by_id(supabase, sub["requirement_id"]) or {}

        company_name = inst.get("company_name", "Unknown Company")
        doc_name = req.get("name", "Compliance Document")
        stage = req.get("stage", "stage_1")
        section = req.get("section", "General")
        req_level = req.get("requirement_level", "mandatory")
        file_path = sub.get("file_path", "")
        expiry_date = sub.get("expiry_date")

        # Determine target bucket
        bucket = "stage-1-compliance" if stage == "stage_1" else "stage-2-compliance"
        signed_url = _get_signed_file_url(supabase, bucket=bucket, path=file_path)

        with st.expander(f"📄 **{company_name}** — {doc_name} (`{stage}` / `{section}`)", expanded=True):
            col_meta, col_file = st.columns([2, 1])

            with col_meta:
                m1, m2 = st.columns(2)
                m1.markdown(f"**Stage:** `{stage}` | **Section:** `{section}`")
                m1.markdown(f"**Requirement:** `{'🔴 Mandatory' if req_level == 'mandatory' else '⚪ Conditional'}`")
                m2.markdown(f"**Submitted Date:** `{sub.get('created_at', '')[:10]}`")
                if expiry_date:
                    m2.markdown(f"**Declared Expiry:** `📅 {expiry_date}`")

            with col_file:
                if signed_url:
                    st.link_button("📄 View / Download Document", signed_url, use_container_width=True)
                else:
                    st.caption(f"Storage path: `{file_path}`")

            st.markdown("---")

            # ── Approve / Reject Actions ─────────────────────────────────────
            col_btn_app, col_reason, col_btn_rej = st.columns([1, 2, 1])

            with col_btn_app:
                st.write("")
                if st.button("✅ Approve", key=f"q2_app_{sub_id}", type="primary", use_container_width=True):
                    _action_approve_document(supabase, sub_id, installer_id, company_name, doc_name, stage)
                    st.rerun()

            with col_reason:
                reject_reason = st.text_input(
                    "Rejection Reason *",
                    key=f"q2_rej_reason_{sub_id}",
                    placeholder="State reason document does not meet compliance...",
                )

            with col_btn_rej:
                st.write("")
                if st.button(
                    "❌ Reject",
                    key=f"q2_rej_btn_{sub_id}",
                    disabled=(not reject_reason.strip()),
                    use_container_width=True,
                ):
                    _action_reject_document(supabase, sub_id, installer_id, company_name, doc_name, reject_reason)
                    st.rerun()


# =============================================================================
# Audit Trail Tab (Requirement 3)
# =============================================================================

def _render_audit_log_tab(supabase: Client) -> None:
    """Render chronological audit log of all compliance staff decisions."""
    st.subheader("Compliance Decision Audit Trail")
    st.caption("Immutable record of all review decisions, approvals, and rejections.")

    try:
        res = (
            supabase.table("audit_log")
            .select("*, installers(company_name, email)")
            .order("timestamp", desc=True)
            .limit(100)
            .execute()
        )
        logs = res.data or []
        if not logs:
            st.info("No audit log events recorded yet.")
            return

        for entry in logs:
            ts = entry.get("timestamp", "")
            action = entry.get("action", "")
            actor = entry.get("actor", "compliance_admin")
            inst = entry.get("installers") or {}
            company = inst.get("company_name", entry.get("installer_id"))
            details = entry.get("details") or {}

            action_icon = "✅" if "approved" in action else "❌"
            with st.container():
                st.markdown(f"**{action_icon} `{ts[:19]}`** — **{actor}** performed `{action}` on **{company}**")
                if details:
                    st.caption(f"Details: {json.dumps(details)}")
                st.markdown("<hr style='margin: 4px 0; border: 0.5px solid #eee;'>", unsafe_allow_html=True)
    except Exception as exc:
        st.warning(f"Could not load audit log table: {exc}")


# =============================================================================
# Installer Directory & Telemetry Tabs
# =============================================================================

def _render_installer_directory(supabase: Client) -> None:
    """Render full table of all installers with their current stage, status, and tokens."""
    st.subheader("All Registered Installers")
    try:
        res = supabase.table("installers").select("*").order("created_at", desc=True).execute()
        installers = res.data or []
        if not installers:
            st.info("No installer records found.")
            return

        import pandas as pd
        df = pd.DataFrame(installers)

        # Build a clickable portal link from the same app_base_url secret
        # gate_0.py already uses -- keeps both in sync by construction.
        app_base = st.secrets.get("app_base_url", "http://localhost:8501")
        df["portal_url"] = df["access_token"].apply(
            lambda tok: f"{app_base}/?access_token={tok}" if tok else None
        )

        cols = [c for c in ["company_name", "email", "current_stage", "current_status",
                             "status_reason", "portal_url", "created_at"] if c in df.columns]
        st.dataframe(
            df[cols],
            use_container_width=True,
            column_config={
                "portal_url": st.column_config.LinkColumn(
                    "Portal Access Link", display_text="🔗 Open Portal"
                ),
            },
        )
    except Exception as exc:
        st.warning(f"Could not load installer directory: {exc}")


def _render_verification_telemetry_tab(supabase: Client) -> None:
    """Render raw extraction confidence and OCR telemetry for threshold calibration."""
    st.subheader("Verification Engine Calibration & Telemetry Logs")
    st.caption("Raw extraction confidence scores and rules telemetry for model calibration.")

    try:
        res = supabase.table("verification_logs").select("*").order("created_at", desc=True).limit(50).execute()
        logs = res.data or []
        if not logs:
            st.info("No verification logs recorded yet.")
            return

        for entry in logs:
            decision = str(entry.get("decision", "")).upper()
            status_color = "🟢" if decision == "STAGE_1" else ("🟡" if decision == "NEEDS_FIXES" else "🔵")
            with st.expander(f"{status_color} {entry.get('created_at', '')} — Decision: {decision}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Stage", entry.get("stage", ""))
                c2.metric("Rules Passed", "Yes" if entry.get("rules_passed") else "No")
                c3.metric("Decision", entry.get("decision", ""))
                st.markdown(f"**Reason:** `{entry.get('reason', '')}`")

                t_rules, t_vis, t_raw = st.tabs(["Rules Breakdown", "Vision Extraction", "Raw Confidence"])
                with t_rules:
                    st.json(entry.get("rules_result") or {})
                with t_vis:
                    st.json(entry.get("vision_result") or {})
                with t_raw:
                    st.json(entry.get("raw_confidence") or {})
    except Exception as exc:
        st.warning(f"Could not load verification telemetry: {exc}")


# =============================================================================
# Action Implementations & Audit Logging (Requirement 3 & 4)
# =============================================================================

def _action_approve_gate_0(supabase: Client, installer_id: str, company_name: str) -> None:
    """Approve Gate 0: advance installer to stage_1, approve Gate 0 documents, write audit log."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Update installer status
        supabase.table("installers").update({
            "current_stage": "stage_1",
            "current_status": "approved",
            "status_reason": "Gate 0 manually approved by compliance officer.",
        }).eq("id", installer_id).execute()

        # 2. Approve Gate 0 submissions specifically
        try:
            g0_reqs = (
                supabase.table("document_requirements")
                .select("id")
                .eq("stage", "gate_0")
                .execute()
                .data or []
            )
            g0_ids = [r["id"] for r in g0_reqs if "id" in r]
            if g0_ids:
                supabase.table("document_submissions").update({
                    "status": "approved",
                    "reviewed_by": "compliance_admin",
                    "reviewed_at": now_iso,
                    "rejection_reason": None,
                }).eq("installer_id", installer_id).in_("requirement_id", g0_ids).execute()
            else:
                supabase.table("document_submissions").update({
                    "status": "approved",
                    "reviewed_by": "compliance_admin",
                    "reviewed_at": now_iso,
                    "rejection_reason": None,
                }).eq("installer_id", installer_id).execute()
        except Exception:
            pass

        # 3. Log Audit Event
        log_audit_event(
            supabase=supabase,
            installer_id=installer_id,
            actor="compliance_admin",
            action="approved_gate_0",
            details={"company_name": company_name, "stage_advanced": "stage_1"},
        )
        st.toast(f"✅ Approved Gate 0 for {company_name}! Advanced to Stage 1.", icon="🎉")
    except Exception as exc:
        st.error(f"Failed to approve Gate 0: {exc}")


def _action_request_fixes_gate_0(
    supabase: Client, installer_id: str, company_name: str, reason: str
) -> None:
    """Request corrections on Gate 0: sets needs_fixes, rejection_reason on NDA, writes audit log."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Update installer status
        supabase.table("installers").update({
            "current_status": "needs_fixes",
            "status_reason": reason,
        }).eq("id", installer_id).execute()

        # 2. Update Gate 0 submissions with rejection reason
        try:
            g0_reqs = (
                supabase.table("document_requirements")
                .select("id")
                .eq("stage", "gate_0")
                .execute()
                .data or []
            )
            g0_ids = [r["id"] for r in g0_reqs if "id" in r]
            if g0_ids:
                supabase.table("document_submissions").update({
                    "status": "rejected",
                    "rejection_reason": reason,
                    "reviewed_by": "compliance_admin",
                    "reviewed_at": now_iso,
                }).eq("installer_id", installer_id).in_("requirement_id", g0_ids).execute()
            else:
                supabase.table("document_submissions").update({
                    "status": "rejected",
                    "rejection_reason": reason,
                    "reviewed_by": "compliance_admin",
                    "reviewed_at": now_iso,
                }).eq("installer_id", installer_id).execute()
        except Exception:
            pass

        # 3. Log Audit Event
        log_audit_event(
            supabase=supabase,
            installer_id=installer_id,
            actor="compliance_admin",
            action="requested_fixes_gate_0",
            details={"company_name": company_name, "reason": reason},
        )
        st.toast(f"⚠️ Requested corrections for {company_name}.", icon="📝")
    except Exception as exc:
        st.error(f"Failed to request fixes: {exc}")


def _action_approve_document(
    supabase: Client,
    submission_id: str,
    installer_id: str,
    company_name: str,
    doc_name: str,
    stage: str,
) -> None:
    """Approve submission, check if all mandatory stage docs pass, write audit log."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        # 1. Update submission status to approved
        supabase.table("document_submissions").update({
            "status": "approved",
            "reviewed_by": "compliance_admin",
            "reviewed_at": now_iso,
            "rejection_reason": None,
        }).eq("id", submission_id).execute()

        # 2. Check if all mandatory requirements for this stage are approved
        stage_completed = False
        if stage in ("stage_1", "stage_2"):
            reqs = (
                supabase.table("document_requirements")
                .select("id")
                .eq("stage", stage)
                .eq("installer_upload", True)
                .eq("requirement_level", "mandatory")
                .execute()
                .data or []
            )
            mandatory_ids = {r["id"] for r in reqs}

            subs = (
                supabase.table("document_submissions")
                .select("requirement_id, status")
                .eq("installer_id", installer_id)
                .execute()
                .data or []
            )
            approved_ids = {s["requirement_id"] for s in subs if s.get("status") == "approved"}

            if mandatory_ids and mandatory_ids.issubset(approved_ids):
                next_stage = "stage_2" if stage == "stage_1" else "complete"
                supabase.table("installers").update({
                    "current_stage": next_stage,
                    "current_status": "pending_review",
                }).eq("id", installer_id).execute()
                stage_completed = True

        # 3. Write Audit Log
        log_audit_event(
            supabase=supabase,
            installer_id=installer_id,
            actor="compliance_admin",
            action="approved_document",
            details={
                "submission_id": submission_id,
                "document_name": doc_name,
                "stage": stage,
                "stage_completed": stage_completed,
            },
        )
        if stage_completed:
            st.toast(f"🎉 Approved '{doc_name}'! All mandatory {stage} documents passed — advanced!", icon="🚀")
        else:
            st.toast(f"✅ Approved '{doc_name}' for {company_name}.", icon="✅")
    except Exception as exc:
        st.error(f"Approval action failed: {exc}")


def _action_reject_document(
    supabase: Client,
    submission_id: str,
    installer_id: str,
    company_name: str,
    doc_name: str,
    reason: str,
) -> None:
    """Reject submission, store rejection_reason on document_submissions, write audit log."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        # 1. Update document_submissions row (Requirement 4: store rejection_reason)
        supabase.table("document_submissions").update({
            "status": "rejected",
            "rejection_reason": reason,
            "reviewed_by": "compliance_admin",
            "reviewed_at": now_iso,
        }).eq("id", submission_id).execute()

        # 2. Update installer status to needs_fixes
        supabase.table("installers").update({
            "current_status": "needs_fixes",
            "status_reason": f"Document '{doc_name}' requires re-upload: {reason}",
        }).eq("id", installer_id).execute()

        # 3. Write Audit Log
        log_audit_event(
            supabase=supabase,
            installer_id=installer_id,
            actor="compliance_admin",
            action="rejected_document",
            details={
                "submission_id": submission_id,
                "document_name": doc_name,
                "reason": reason,
            },
        )
        st.toast(f"❌ Rejected '{doc_name}' for {company_name}.", icon="⚠️")
    except Exception as exc:
        st.error(f"Rejection action failed: {exc}")


def log_audit_event(
    supabase: Client,
    installer_id: str,
    actor: str,
    action: str,
    details: dict | None = None,
) -> None:
    """
    Insert a row into the audit_log table.
    Fails gracefully if the migration has not yet been executed.
    """
    payload = {
        "installer_id": installer_id,
        "actor": actor,
        "action": action,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        supabase.table("audit_log").insert(payload).execute()
    except Exception as exc:
        logger.warning("Could not write to audit_log table: %s", exc)


# =============================================================================
# Data Fetching Helpers
# =============================================================================

def _fetch_queue_1_installers(supabase: Client) -> list[dict]:
    """Fetch installers where current_status is 'needs_review' or 'needs_fixes'."""
    try:
        res = (
            supabase.table("installers")
            .select("*")
            .in_("current_status", ["needs_review", "needs_fixes"])
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.warning("Could not fetch Queue 1 installers: %s", exc)
        return []


def _fetch_queue_2_submissions(supabase: Client) -> list[dict]:
    """Fetch document_submissions where status='pending_review' (Stage 1 onward)."""
    try:
        res = (
            supabase.table("document_submissions")
            .select("*, document_requirements!inner(*), installers!inner(*)")
            .eq("status", "pending_review")
            .neq("document_requirements.stage", "gate_0")
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as exc:
        logger.warning("Could not fetch Queue 2 submissions: %s", exc)
        # Fallback without join filter if foreign keys differ
        try:
            fallback_res = (
                supabase.table("document_submissions")
                .select("*, document_requirements(*), installers(*)")
                .eq("status", "pending_review")
                .order("created_at", desc=True)
                .execute()
            )
            rows = fallback_res.data or []
            return [r for r in rows if (r.get("document_requirements") or {}).get("stage") != "gate_0"]
        except Exception:
            return []


def _fetch_prequalification_data(supabase: Client, installer_id: str) -> dict | None:
    """Fetch prequalification form row for installer."""
    try:
        res = (
            supabase.table("prequalification_forms")
            .select("*")
            .eq("installer_id", installer_id)
            .single()
            .execute()
        )
        return res.data
    except Exception:
        return None


def _fetch_latest_verification_log(supabase: Client, installer_id: str) -> dict | None:
    """Fetch the most recent verification evaluation log for this installer."""
    try:
        res = (
            supabase.table("verification_logs")
            .select("*")
            .eq("installer_id", installer_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return None


def _get_nda_file_path(supabase: Client, installer_id: str) -> str:
    """Resolve the storage path of the signed NDA PDF for an installer."""
    try:
        res = (
            supabase.table("document_submissions")
            .select("file_path, document_requirements(name)")
            .eq("installer_id", installer_id)
            .execute()
        )
        for r in res.data or []:
            fp = r.get("file_path", "")
            req = r.get("document_requirements") or {}
            if isinstance(req, list) and req:
                req = req[0]
            req_name = req.get("name", "") if isinstance(req, dict) else ""
            if "nda" in fp.lower() or "nda" in req_name.lower():
                return fp
    except Exception:
        pass
    return f"{installer_id}/gate_0_nda.pdf"


def _fetch_installer_by_id(supabase: Client, installer_id: str) -> dict | None:
    """Lookup installer by primary key."""
    try:
        res = supabase.table("installers").select("*").eq("id", installer_id).single().execute()
        return res.data
    except Exception:
        return None


def _fetch_requirement_by_id(supabase: Client, requirement_id: str) -> dict | None:
    """Lookup document requirement by ID."""
    try:
        res = (
            supabase.table("document_requirements")
            .select("*")
            .eq("id", requirement_id)
            .single()
            .execute()
        )
        return res.data
    except Exception:
        return None


def _get_signed_file_url(supabase: Client, bucket: str, path: str, expires_in: int = 3600) -> str | None:
    """Generate a signed download URL for a file in Supabase Storage with bucket fallbacks."""
    if not path:
        return None

    if path.startswith("http://") or path.startswith("https://"):
        return path

    candidate_buckets = [bucket]
    for b in ["gate-0-documents", "stage-1-compliance", "stage-2-compliance"]:
        if b not in candidate_buckets:
            candidate_buckets.append(b)

    for b in candidate_buckets:
        try:
            res = supabase.storage.from_(b).create_signed_url(path, expires_in)
            if hasattr(res, "signedURL") and res.signedURL:
                return res.signedURL
            if hasattr(res, "signedUrl") and res.signedUrl:
                return res.signedUrl
            if isinstance(res, dict):
                url = res.get("signedURL") or res.get("signedUrl")
                if url:
                    return url
        except Exception:
            continue
    return None
