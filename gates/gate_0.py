"""
gates/gate_0.py — Pre-Qualification Form & NDA Upload
======================================================
Implements the Gate 0 installer experience:

  New visitor (no token):
    → Full pre-qualification form + NDA upload
    → On submit: create installer row, upload NDA, return access link

  Returning visitor (gate_0 + pending_review):
    → "Under review" banner — no edits allowed

  Returning visitor (gate_0 + needs_fixes):
    → Form pre-filled from saved data, feedback shown, re-submission allowed

Public surface
--------------
    render(supabase, installer)   ← called from app.py
"""

from __future__ import annotations

import uuid
import json
import streamlit as st
from supabase import Client
from verification import evaluate_gate_0

# ---------------------------------------------------------------------------
# SA provinces for the geographic-areas multiselect
# ---------------------------------------------------------------------------
_SA_PROVINCES = [
    "Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal",
    "Limpopo", "Mpumalanga", "North West", "Northern Cape", "Western Cape",
]

_BBBEE_OPTIONS = [
    "", "Level 1", "Level 2", "Level 3", "Level 4",
    "Level 5", "Level 6", "Level 7", "Level 8", "Non-Compliant / Exempt",
]

# ===========================================================================
# Public entry point
# ===========================================================================

def render(supabase: Client, installer: dict | None = None) -> None:
    """
    Main Gate 0 renderer.

    Parameters
    ----------
    supabase : Client
        Initialised Supabase client (from app.py).
    installer : dict | None
        Existing installer row when a returning visitor holds a token.
        ``None`` for first-time visitors with no token.
    """
    _render_header(installer)

    # ── Status gates ────────────────────────────────────────────────────────
    if installer:
        status = installer.get("current_status", "pending_review")
        stage = installer.get("current_stage", "gate_0")

        if stage == "stage_1":
            st.success(
                f"🎉 **Gate 0 Approved!** **{installer.get('company_name', '')}** has passed "
                "pre-qualification and advanced to **Stage 1 (Company Documents)**.",
                icon="✅",
            )
            if st.button("➡️ Continue to Stage 1", type="primary", key="btn_gate0_goto_s1"):
                st.session_state["access_token"] = installer.get("access_token")
                st.rerun()
            return

        if status in ("pending_review", "needs_review"):
            _render_pending_banner(installer)
            return

        if status == "needs_fixes":
            reason = installer.get("status_reason", "")
            st.warning(
                "⚠️ **Your submission requires corrections.** "
                "Please review the feedback below, update the relevant sections, "
                "and resubmit.",
                icon="⚠️",
            )
            if reason:
                st.info(f"📋 **Action Required:** {reason}", icon="ℹ️")

    # ── Load existing preq data for pre-fill (needs_fixes case) ─────────────
    preq_data: dict = {}
    if installer:
        preq_data = _fetch_preq_data(supabase, installer["id"]) or {}

    # ── Initialize CoC personnel state ───────────────────────────────────────
    _init_coc_state(preq_data.get("coc_personnel") or [])

    # ── Main form (Sections 1–8, including Section 5c CoC list) ──────────────
    st.markdown("---")
    form_values = _render_main_form(preq_data)

    # ── Section 9: NDA upload ────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("9. NDA Upload")
    st.caption("Upload the **signed** Non-Disclosure Agreement (PDF only, max 10 MB).")
    nda_file = st.file_uploader(
        "Signed NDA Document *", type=["pdf"], key="gate0_nda_file",
        help="The NDA must be signed by an authorised company representative.",
    )

    # ── Submit button ────────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("✅  Submit Pre-Qualification", type="primary", use_container_width=True, key="btn_gate0_submit"):
        _handle_submit(supabase, installer, form_values, nda_file)



# ===========================================================================
# Header
# ===========================================================================

def _render_header(installer: dict | None) -> None:
    st.title("Gate 0 — Pre-Qualification & NDA")
    if installer:
        st.markdown(
            f"Welcome back, **{installer.get('company_name', '')}**. "
            "Your current Gate 0 status is shown below."
        )
    else:
        st.markdown(
            "Complete this form to begin the **Wetility HSE Compliance Onboarding** process. "
            "All fields marked **\\*** are mandatory. "
            "You will receive a unique access link after submission — bookmark it."
        )


# ===========================================================================
# Status banner
# ===========================================================================

def _render_pending_banner(installer: dict) -> None:
    company = installer.get("company_name", "Your application")
    token = installer.get("access_token", "")
    status = installer.get("current_status", "pending_review")
    reason = installer.get("status_reason", "")

    if status == "needs_review":
        st.info(
            f"**{company}** has been submitted and is currently routed for "
            "**Compliance Officer Review**. The Wetility compliance team is reviewing your documentation.",
            icon="📋",
        )
        if reason:
            st.caption(f"Review Notes: {reason}")
    else:
        st.success(
            f"**{company}** has been submitted "
            "and is currently under review by the Wetility compliance team. "
            "You will be notified once Gate 0 is approved.",
            icon="⏳",
        )

    st.info(
        "**Your Access Link** — bookmark this URL to track your progress:\n\n"
        f"```\n?access_token={token}\n```",
        icon="🔗",
    )


# ===========================================================================
# CoC personnel dynamic list (outside st.form)
# ===========================================================================

def _init_coc_state(existing: list[dict]) -> None:
    """Seed session_state CoC list from saved data or an empty starter row."""
    if "coc_personnel" not in st.session_state:
        if existing:
            st.session_state["coc_personnel"] = [
                {"name": p.get("name", ""), "reg_number": p.get("reg_number", "")}
                for p in existing
            ]
        else:
            st.session_state["coc_personnel"] = [{"name": "", "reg_number": ""}]


def _render_coc_section() -> None:
    """
    Render a dynamic add / remove list for CoC-authorised personnel.
    Uses st.session_state so buttons can re-render without a form submit.
    """
    st.markdown("#### 5c. CoC-Authorised Personnel")
    st.caption(
        "List every person authorised to issue Certificates of Compliance (CoC) "
        "on behalf of your company."
    )

    personnel = st.session_state.get("coc_personnel", [])
    to_remove: int | None = None

    for i, person in enumerate(personnel):
        col_name, col_reg, col_del = st.columns([3, 3, 1])
        with col_name:
            val_name = st.text_input(
                f"Full Name #{i + 1}", value=person.get("name", ""),
                key=f"coc_name_{i}", label_visibility="collapsed",
                placeholder=f"Full Name #{i + 1}",
            )
            personnel[i]["name"] = val_name
        with col_reg:
            val_reg = st.text_input(
                f"Registration # {i + 1}", value=person.get("reg_number", ""),
                key=f"coc_reg_{i}", label_visibility="collapsed",
                placeholder=f"Registration Number #{i + 1}",
            )
            personnel[i]["reg_number"] = val_reg
        with col_del:
            if len(personnel) > 1:
                if st.button("🗑️", key=f"coc_del_{i}", help="Remove this person"):
                    to_remove = i

    if to_remove is not None:
        st.session_state["coc_personnel"].pop(to_remove)
        for k in list(st.session_state.keys()):
            if k.startswith("coc_name_") or k.startswith("coc_reg_"):
                del st.session_state[k]
        st.rerun()

    if st.button("➕ Add Another Person", key="coc_add"):
        st.session_state["coc_personnel"].append({"name": "", "reg_number": ""})
        st.rerun()



# ===========================================================================
# Main form (all other sections)
# ===========================================================================

def _render_main_form(preq: dict) -> dict:
    """
    Render sections 1–8 with dynamic CoC personnel included in Section 5.

    Returns
    -------
    dict
        All collected field values.
    """
    # ── Section 1: Company Information ───────────────────────────────────
    st.subheader("1. Company Information")
    col1, col2 = st.columns(2)
    with col1:
        company_name = st.text_input(
            "Company Name *",
            value=preq.get("company_name", ""),
            key="f_company_name",
        )
        cipc_reg = st.text_input(
            "CIPC Registration Number *",
            value=preq.get("cipc_reg_number", ""),
            key="f_cipc_reg",
        )
        tax_clearance = st.text_input(
            "Tax Clearance Number *",
            value=preq.get("tax_clearance_number", ""),
            key="f_tax_clearance",
        )
        bbbee_idx = (
            _BBBEE_OPTIONS.index(preq["bbbee_level"])
            if preq.get("bbbee_level") in _BBBEE_OPTIONS else 0
        )
        bbbee_level = st.selectbox(
            "B-BBEE Level *",
            options=_BBBEE_OPTIONS,
            index=bbbee_idx,
            key="f_bbbee",
        )
    with col2:
        physical_address = st.text_area(
            "Physical Address *",
            value=preq.get("physical_address", ""),
            height=120,
            key="f_address",
        )
        years_in_business = st.number_input(
            "Years in Business *",
            min_value=0, max_value=100, step=1,
            value=int(preq.get("years_in_business") or 0),
            key="f_years",
        )

    st.divider()

    # ── Section 2: Contact Person ─────────────────────────────────────────
    st.subheader("2. Contact Person")
    col1, col2 = st.columns(2)
    with col1:
        contact_name = st.text_input(
            "Full Name *", value=preq.get("contact_name", ""), key="f_c_name"
        )
        contact_position = st.text_input(
            "Position / Title *", value=preq.get("contact_position", ""), key="f_c_pos"
        )
    with col2:
        contact_phone = st.text_input(
            "Phone Number *", value=preq.get("contact_phone", ""), key="f_c_phone"
        )
        contact_email = st.text_input(
            "Email Address *", value=preq.get("contact_email", ""), key="f_c_email"
        )

    st.divider()

    # ── Section 3: Track Record ───────────────────────────────────────────
    st.subheader("3. Track Record & Experience")
    col1, col2 = st.columns(2)
    with col1:
        prior_count = st.number_input(
            "Number of Prior PV Projects Completed *",
            min_value=0, step=1,
            value=int(preq.get("prior_project_count") or 0),
            key="f_proj_count",
        )
        project_sizes = st.text_area(
            "Typical Project Sizes (kWp) *",
            value=preq.get("project_sizes", ""),
            placeholder="e.g. 5–50 kWp residential; 100–500 kWp C&I",
            height=80,
            key="f_proj_sizes",
        )
    with col2:
        saved_provinces = preq.get("geographic_areas") or []
        geo_areas = st.multiselect(
            "Geographic Areas of Operation *",
            options=_SA_PROVINCES,
            default=[p for p in saved_provinces if p in _SA_PROVINCES],
            key="f_geo",
        )

    st.divider()

    # ── Section 4: Technical Capability ──────────────────────────────────
    st.subheader("4. Technical Capability")
    col1, col2 = st.columns(2)
    with col1:
        bop_idx = 0 if preq.get("bop_capability") is not False else 1
        bop_cap = st.radio(
            "Balance of Plant (BoP) capability? *",
            options=["Yes", "No"], index=bop_idx, horizontal=True, key="f_bop",
        )
    with col2:
        maint_idx = 0 if preq.get("maintenance_capability") is not False else 1
        maint_cap = st.radio(
            "O&M / Maintenance services offered? *",
            options=["Yes", "No"], index=maint_idx, horizontal=True, key="f_maint",
        )

    st.divider()

    # ── Section 5: Electrical Compliance ─────────────────────────────────
    st.subheader("5. Electrical Compliance")
    col1, col2 = st.columns(2)
    with col1:
        dol_reg = st.text_input(
            "DoL Electrical Contractor Registration Number *",
            value=preq.get("dol_reg_number", ""), key="f_dol",
        )
        wiremans = st.text_input(
            "Wireman's Licence Number *",
            value=preq.get("wiremans_licence_number", ""), key="f_wiremans",
        )
    with col2:
        gc_idx = 0 if preq.get("pv_greencard") is not False else 1
        pv_greencard = st.radio(
            "Company holds a PV GreenCard? *",
            options=["Yes", "No"], index=gc_idx, horizontal=True, key="f_gc",
        )

    # ── Section 5c: CoC-Authorised Personnel ─────────────────────────────
    st.markdown("---")
    _render_coc_section()

    st.divider()

    # ── Section 6: Compliance Documentation ──────────────────────────────
    st.subheader("6. Compliance Documentation")
    col1, col2 = st.columns(2)
    with col1:
        gs_idx = 0 if preq.get("good_standing_attached") is not False else 1
        good_standing = st.radio(
            "Letter of Good Standing attached? *",
            options=["Yes", "No"], index=gs_idx, horizontal=True, key="f_gs",
        )
        li_idx = 0 if preq.get("liability_insurance_attached") is not False else 1
        liability_ins = st.radio(
            "Public Liability Insurance attached? *",
            options=["Yes", "No"], index=li_idx, horizontal=True, key="f_li",
        )
    with col2:
        hp_idx = 0 if preq.get("hse_policy_attached") is not False else 1
        hse_policy = st.radio(
            "HSE Policy attached? *",
            options=["Yes", "No"], index=hp_idx, horizontal=True, key="f_hp",
        )
        hd_idx = 0 if preq.get("hse_documentation_available") is not False else 1
        hse_docs = st.radio(
            "HSE Documentation available? *",
            options=["Yes", "No"], index=hd_idx, horizontal=True, key="f_hd",
        )

    st.divider()

    # ── Section 7: Tools & Equipment ─────────────────────────────────────
    st.subheader("7. Tools & Equipment")
    col1, col2 = st.columns(2)
    with col1:
        ta_idx = 0 if preq.get("tools_available") is not False else 1
        tools_avail = st.radio(
            "All required installation tools available? *",
            options=["Yes", "No"], index=ta_idx, horizontal=True, key="f_ta",
        )
    with col2:
        ti_idx = 0 if preq.get("tool_inspection_routine") is not False else 1
        tool_inspect = st.radio(
            "Documented tool inspection routine in place? *",
            options=["Yes", "No"], index=ti_idx, horizontal=True, key="f_ti",
        )

    st.divider()

    # ── Section 8: Declaration ────────────────────────────────────────────
    st.subheader("8. Declaration")
    st.caption(
        "I, the undersigned, declare that all information provided is true and correct "
        "to the best of my knowledge and that I am duly authorised to submit this form "
        "on behalf of the company."
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        decl_name = st.text_input(
            "Full Name *",
            value=preq.get("declaration_name", ""), key="f_decl_name",
        )
    with col2:
        decl_pos = st.text_input(
            "Position *",
            value=preq.get("declaration_position", ""), key="f_decl_pos",
        )
    with col3:
        decl_sig = st.text_input(
            "Type Full Name as Signature *",
            value=preq.get("declaration_signature", ""),
            key="f_decl_sig",
            help="An e-signature canvas option will replace this once confirmed with legal.",
        )

    coc_cleaned = [
        {"name": p.get("name", "").strip(), "reg_number": p.get("reg_number", "").strip()}
        for p in st.session_state.get("coc_personnel", [])
        if p.get("name", "").strip()
    ]

    return {
        "company_name":               (st.session_state.get("f_company_name") or company_name or "").strip(),
        "cipc_reg_number":            (st.session_state.get("f_cipc_reg") or cipc_reg or "").strip(),
        "tax_clearance_number":       (st.session_state.get("f_tax_clearance") or tax_clearance or "").strip(),
        "bbbee_level":                st.session_state.get("f_bbbee") or bbbee_level,
        "physical_address":           (st.session_state.get("f_address") or physical_address or "").strip(),
        "years_in_business":          int(st.session_state.get("f_years", years_in_business) or 0),
        "contact_name":               (st.session_state.get("f_c_name") or contact_name or "").strip(),
        "contact_position":           (st.session_state.get("f_c_pos") or contact_position or "").strip(),
        "contact_phone":              (st.session_state.get("f_c_phone") or contact_phone or "").strip(),
        "contact_email":              (st.session_state.get("f_c_email") or contact_email or "").strip(),
        "prior_project_count":        int(st.session_state.get("f_proj_count", prior_count) or 0),
        "project_sizes":              (st.session_state.get("f_proj_sizes") or project_sizes or "").strip(),
        "geographic_areas":           st.session_state.get("f_geo", geo_areas) or [],
        "bop_capability":             (st.session_state.get("f_bop", bop_cap) == "Yes"),
        "maintenance_capability":     (st.session_state.get("f_maint", maint_cap) == "Yes"),
        "dol_reg_number":             (st.session_state.get("f_dol") or dol_reg or "").strip(),
        "wiremans_licence_number":    (st.session_state.get("f_wiremans") or wiremans or "").strip(),
        "coc_personnel":              coc_cleaned,
        "pv_greencard":               (st.session_state.get("f_gc", pv_greencard) == "Yes"),
        "good_standing_attached":     (st.session_state.get("f_gs", good_standing) == "Yes"),
        "liability_insurance_attached": (st.session_state.get("f_li", liability_ins) == "Yes"),
        "hse_policy_attached":        (st.session_state.get("f_hp", hse_policy) == "Yes"),
        "hse_documentation_available": (st.session_state.get("f_hd", hse_docs) == "Yes"),
        "tools_available":            (st.session_state.get("f_ta", tools_avail) == "Yes"),
        "tool_inspection_routine":    (st.session_state.get("f_ti", tool_inspect) == "Yes"),
        "declaration_name":           (st.session_state.get("f_decl_name") or decl_name or "").strip(),
        "declaration_position":       (st.session_state.get("f_decl_pos") or decl_pos or "").strip(),
        "declaration_signature":      (st.session_state.get("f_decl_sig") or decl_sig or "").strip(),
        "signature_method":           "typed",
    }



# ===========================================================================
# Submission handler
# ===========================================================================

def _handle_submit(
    supabase: Client,
    installer: dict | None,
    form_values: dict,
    nda_file,
) -> None:
    """Validate initial requirements, persist, evaluate rules & vision, and display result."""

    # ── Basic Client Validation ───────────────────────────────────────────────
    errors = _validate(form_values, nda_file)
    if errors:
        for err in errors:
            st.error(err, icon="❌")
        return

    nda_bytes = nda_file.getvalue() if hasattr(nda_file, "getvalue") else nda_file.read()

    # ── Persist ──────────────────────────────────────────────────────────────
    with st.spinner("Submitting your pre-qualification — please wait…"):
        try:
            installer_id, access_token = _persist(supabase, installer, form_values, nda_bytes)
        except Exception as exc:
            st.error(f"Submission failed: {exc}", icon="🚨")
            return

    # ── Automated Verification Engine (Rules first, then Vision) ─────────────
    with st.spinner("Evaluating compliance submission (rules & NDA verification)…"):
        try:
            verif_result = evaluate_gate_0(
                supabase=supabase,
                installer_id=installer_id,
                form_values=form_values,
                nda_bytes=nda_bytes,
            )
        except Exception as exc:
            verif_result = None

    app_base = st.secrets.get("app_base_url", "http://localhost:8501")
    access_url = f"{app_base}/?access_token={access_token}"

    # ── Outcome Display ──────────────────────────────────────────────────────
    if verif_result and verif_result.passed_to_stage_1:
        st.success(
            "🎉 **Gate 0 Verification Passed!** "
            "All compliance rules and NDA verification checks were successful. "
            "You have advanced to **Stage 1 (Company Documents)**!",
            icon="🚀",
        )
        st.balloons()
        st.info(
            "**📎 Your personalised access link — bookmark this now:**\n\n"
            f"```\n{access_url}\n```\n\n"
            "You will need this link to return to the portal and upload Stage 1 documents.",
            icon="🔗",
        )
        if st.button("➡️ Proceed to Stage 1", type="primary", key="btn_proceed_to_stage1"):
            st.session_state["access_token"] = access_token
            st.rerun()

    elif verif_result and verif_result.requires_fixes:
        st.warning(
            "⚠️ **Pre-Qualification Submitted — Correction Required**\n\n"
            f"**Action Required:** {verif_result.reason}\n\n"
            "Please review the feedback above, update the field or re-upload your document, "
            "and resubmit.",
            icon="⚠️",
        )
        st.info(
            "**📎 Your personalised access link:**\n\n"
            f"```\n{access_url}\n```\n\n"
            "Bookmark this link so you can return at any time to submit your corrections.",
            icon="🔗",
        )

    else:
        # Knockouts, multiple failures, or under review
        st.info(
            "📋 **Pre-Qualification Submitted — Under Compliance Officer Review**\n\n"
            "Your pre-qualification application and NDA have been submitted and are "
            "currently undergoing manual review by the Wetility HSE compliance team.",
            icon="⏳",
        )
        if verif_result and verif_result.rules_result.has_knockouts:
            st.warning(
                f"**Compliance Review Notes:** {'; '.join(verif_result.rules_result.knockouts)}",
                icon="⚠️",
            )
        elif verif_result and verif_result.reason:
            st.caption(f"Review Notes: {verif_result.reason}")

        st.info(
            "**📎 Your personalised access link — bookmark this now:**\n\n"
            f"```\n{access_url}\n```\n\n"
            "Use this link to check the status of your review.",
            icon="🔗",
        )


# ===========================================================================
# Validation
# ===========================================================================

_MANDATORY_TEXT_FIELDS: list[tuple[str, str]] = [
    ("company_name",            "Company Name"),
    ("cipc_reg_number",         "CIPC Registration Number"),
    ("tax_clearance_number",    "Tax Clearance Number"),
    ("bbbee_level",             "B-BBEE Level"),
    ("physical_address",        "Physical Address"),
    ("contact_name",            "Contact Person — Full Name"),
    ("contact_position",        "Contact Person — Position"),
    ("contact_phone",           "Contact Person — Phone"),
    ("contact_email",           "Contact Person — Email"),
    ("dol_reg_number",          "DoL Electrical Contractor Registration Number"),
    ("wiremans_licence_number", "Wireman's Licence Number"),
    ("declaration_name",        "Declaration — Full Name"),
    ("declaration_position",    "Declaration — Position"),
    ("declaration_signature",   "Declaration — Signature"),
]


def _validate(form_values: dict, nda_file) -> list[str]:
    errors: list[str] = []

    # Essential registration fields required to establish installer account
    company_name = str(form_values.get("company_name") or "").strip()
    if not company_name:
        errors.append("**Company Name** is required.")

    contact_email = str(form_values.get("contact_email") or "").strip()
    if not contact_email:
        errors.append("**Contact Person — Email** is required to receive your access link.")

    if nda_file is None:
        errors.append("**Signed NDA** — please upload the signed NDA document (PDF).")

    if nda_file and nda_file.size > 10 * 1024 * 1024:
        errors.append("**NDA file** exceeds the 10 MB size limit.")

    return errors


# ===========================================================================
# Database & Storage persistence
# ===========================================================================

def _persist(
    supabase: Client,
    installer: dict | None,
    form_values: dict,
    nda_bytes: bytes,
) -> tuple[str, str]:
    """
    Write all data to Supabase and upload the NDA.

    Returns
    -------
    (installer_id, access_token)
    """
    # 1. Upsert installer row
    if installer:
        installer_id = installer["id"]
        access_token = installer["access_token"]
        supabase.table("installers").update({
            "company_name":   form_values["company_name"],
            "email":          form_values["contact_email"],
            "current_status": "pending_review",
        }).eq("id", installer_id).execute()
    else:
        # Check if installer with this email already exists
        existing = (
            supabase.table("installers")
            .select("*")
            .eq("email", form_values["contact_email"])
            .execute()
        )
        if existing.data:
            installer_id = existing.data[0]["id"]
            access_token = existing.data[0]["access_token"]
            supabase.table("installers").update({
                "company_name":   form_values["company_name"],
                "current_status": "pending_review",
            }).eq("id", installer_id).execute()
        else:
            access_token = str(uuid.uuid4())
            res = supabase.table("installers").insert({
                "company_name":   form_values["company_name"],
                "email":          form_values["contact_email"],
                "access_token":   access_token,
                "current_stage":  "gate_0",
                "current_status": "pending_review",
            }).execute()
            installer_id = res.data[0]["id"]


    # 2. Upsert prequalification_forms row
    preq_payload = {k: v for k, v in form_values.items()
                    if k not in ("company_name", "contact_email")}
    preq_payload["installer_id"] = installer_id
    # Serialise JSONB-bound fields
    preq_payload["coc_personnel"] = json.dumps(form_values.get("coc_personnel", []))
    # geographic_areas must be a Python list (supabase-py sends it as JSON array → text[])
    preq_payload["geographic_areas"] = form_values.get("geographic_areas", [])

    supabase.table("prequalification_forms").upsert(
        preq_payload, on_conflict="installer_id"
    ).execute()

    # 3. Upload NDA to Supabase Storage
    storage_path = f"{installer_id}/gate_0_nda.pdf"
    supabase.storage.from_("gate-0-documents").upload(
        path=storage_path,
        file=nda_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )

    # 4. Resolve document_requirement IDs
    nda_req = _get_requirement(supabase, "gate_0", "Signed Non-Disclosure Agreement (NDA)")
    preq_req = _get_requirement(supabase, "gate_0", "Pre-Qualification Form")

    # 5. Upsert document_submissions for NDA
    if nda_req:
        supabase.table("document_submissions").upsert(
            {
                "installer_id":     installer_id,
                "requirement_id":   nda_req["id"],
                "file_path":        storage_path,
                "status":           "pending_review",
                "signature_method": "uploaded",
                "personnel_id":     None,
            },
            on_conflict="installer_id,requirement_id,personnel_id",
        ).execute()

    # 6. Upsert document_submissions for the preq form (no file — internal record)
    if preq_req:
        supabase.table("document_submissions").upsert(
            {
                "installer_id":     installer_id,
                "requirement_id":   preq_req["id"],
                "file_path":        f"{installer_id}/prequalification_form",
                "status":           "pending_review",
                "signature_method": "typed",
                "personnel_id":     None,
            },
            on_conflict="installer_id,requirement_id,personnel_id",
        ).execute()

    return installer_id, access_token


# ===========================================================================
# Helpers
# ===========================================================================

def _fetch_preq_data(supabase: Client, installer_id: str) -> dict | None:
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


def _get_requirement(supabase: Client, stage: str, name: str) -> dict | None:
    try:
        res = (
            supabase.table("document_requirements")
            .select("id")
            .eq("stage", stage)
            .ilike("name", f"%{name}%")
            .limit(1)
            .execute()
        )
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception:
        return None

