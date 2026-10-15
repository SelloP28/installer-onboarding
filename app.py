"""
app.py — Compliance Installer Onboarding Portal
================================================
Entry point for the Streamlit application.

Architecture:
- Installer Portal  : accessed via ?access_token=<uuid> in the URL.
- Compliance Admin  : internal staff view for reviewing submissions.

Credentials are loaded exclusively from .streamlit/secrets.toml.
"""

import streamlit as st
from supabase import create_client, Client
from gates import gate_0 as gate_0_module
from gates import stage_1 as stage_1_module
from gates import stage_2 as stage_2_module
from admin import render_admin_dashboard

# ---------------------------------------------------------------------------
# Page configuration — must be the very first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="HSE Installer Onboarding Portal",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Supabase client (singleton cached for the session)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_supabase_client() -> Client:
    """
    Initialise and return a cached Supabase client.

    Credentials are sourced from .streamlit/secrets.toml:
        [supabase]
        url = "https://<project-id>.supabase.co"
        key = "<anon-or-service-role-key>"
    """
    url: str = st.secrets["supabase"]["url"]
    key: str = st.secrets["supabase"]["key"]
    return create_client(url, key)


supabase: Client = get_supabase_client()

# ---------------------------------------------------------------------------
# Session-state bootstrap
# ---------------------------------------------------------------------------

def _bootstrap_session_state() -> None:
    """
    Seed st.session_state from URL query params on first load.

    The installer is identified by a unique `access_token` query param, e.g.:
        https://your-app.streamlit.app/?access_token=<uuid>

    Never store or look up the installer by email address alone.
    """
    if "access_token" not in st.session_state:
        params = st.query_params
        st.session_state["access_token"] = params.get("access_token", None)

    # Default portal view
    if "active_view" not in st.session_state:
        st.session_state["active_view"] = "installer"


_bootstrap_session_state()

# ---------------------------------------------------------------------------
# Sidebar — view switcher
# ---------------------------------------------------------------------------

def render_sidebar() -> str:
    """
    Render the sidebar navigation and return the selected view name.

    Returns
    -------
    str
        Either ``"installer"`` or ``"admin"``.
    """
    with st.sidebar:
        st.image(
            "https://via.placeholder.com/200x60?text=HSE+Portal",
            use_container_width=True,
        )
        st.markdown("---")
        st.subheader("Navigation")

        view = st.radio(
            label="Select Portal",
            options=["installer", "admin"],
            format_func=lambda v: (
                "📋 Installer Portal" if v == "installer" else "🛡️ Compliance Admin"
            ),
            index=0 if st.session_state.get("active_view") == "installer" else 1,
            key="nav_radio",
        )

        st.session_state["active_view"] = view

        st.markdown("---")
        st.caption("HSE Compliance Portal v0.1.0")

    return view


# ---------------------------------------------------------------------------
# Installer Portal skeleton
# ---------------------------------------------------------------------------

def render_installer_portal() -> None:
    """
    Installer-facing portal.

    Flow:
        No token     → Gate 0 new-registration form (first-time visitor)
        gate_0       → Gate 0 status / re-submission (returning visitor)
        stage_1      → Company-level document uploads
        stage_2      → Personnel-level document uploads
        complete     → Completion screen

    The installer is identified by st.session_state["access_token"].
    A missing token is valid only at Gate 0 (new registration entry point).
    """
    access_token: str | None = st.session_state.get("access_token")

    # ── No token → new-registration entry point (Gate 0) ───────────────────
    if not access_token:
        gate_0_module.render(supabase, installer=None)
        return

    # ── Token present → resolve installer ──────────────────────────────────
    installer = _get_installer_by_token(access_token)

    if installer is None:
        st.error(
            "Invalid or expired access token. "
            "Please check your link or contact HSE."
        )
        st.stop()

    stage: str = installer.get("current_stage", "gate_0")

    # ── Route to the correct stage ──────────────────────────────────────────
    stage_renderers = {
        "gate_0":   render_gate_0,
        "stage_1":  render_stage_1,
        "stage_2":  render_stage_2,
        "complete": render_complete,
    }

    renderer = stage_renderers.get(stage)
    if renderer:
        renderer(installer)
    else:
        st.warning(f"Unknown stage: `{stage}`. Please contact HSE support.")


# ---------------------------------------------------------------------------
# Compliance Admin skeleton
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Compliance Admin skeleton
# ---------------------------------------------------------------------------
def render_admin_portal() -> None:
    """
    Internal Compliance Admin view (Prompt 5).
    Renders Queue 1 (Gate 0 reviews), Queue 2 (document submissions),
    Installer Directory, Audit Trail, and Verification Telemetry.
    """
    # 1. Check if the admin is already authenticated in this session
    if not st.session_state.get("admin_authenticated", False):
        
        st.title("🔒 Admin Login")
        st.info("Please enter the compliance admin password to access this portal.")
        
        # 2. Render the password input
        pwd = st.text_input("Password", type="password", key="admin_pwd_input")
        
        if st.button("Login", type="primary"):
            expected_password = st.secrets.get("admin", {}).get("password")
            
            # 3. Validate against secrets.toml
            if not expected_password:
                st.error("🚨 Admin password not configured in secrets.toml!")
            elif pwd == expected_password:
                st.session_state["admin_authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        
        # Stop execution here if not authenticated so the dashboard doesn't load
        return

    # 4. If authenticated, render the actual dashboard
    render_admin_dashboard(supabase)


# ---------------------------------------------------------------------------
# Stage renderers (Installer Portal) — stubs
# ---------------------------------------------------------------------------

def render_gate_0(installer: dict) -> None:
    """
    Gate 0 — Pre-qualification form & NDA.

    Delegates to gates.gate_0.render() which handles:
        - pending_review banner for submitted applications
        - needs_fixes re-submission flow
        - Full form + NDA upload for first-time or fix submissions
    """
    gate_0_module.render(supabase, installer=installer)


def render_stage_1(installer: dict) -> None:
    """
    Stage 1 — Company-level document uploads.

    Delegates to gates.stage_1.render() which dynamically queries
    document_requirements for stage='stage_1' and installer_upload=true,
    renders file uploaders, calculates progress, and advances to stage_2
    when all mandatory documents are approved.
    """
    stage_1_module.render(supabase, installer=installer)


def render_stage_2(installer: dict) -> None:
    """
    Stage 2 — Comprehensive HSE File & Personnel Roster.

    Delegates to gates.stage_2.render() which handles:
        - Company-scoped HSE file section documents (grouped by section)
        - Personnel roster CRUD (add/remove team members)
        - Per-person compliance document uploads
        - Combined progress tracking across company + all personnel
        - Advancement to 'complete' when all mandatory items are approved
    """
    stage_2_module.render(supabase, installer=installer)


def render_complete(installer: dict) -> None:
    """
    Completion screen shown when all stages are approved.
    Delegates to stage_2's completion renderer so the same cleared-for-
    allocation screen is shown whether the user is re-visiting or just
    completed Stage 2.
    """
    from gates.stage_2 import _render_completion_screen
    _render_completion_screen(installer)


# ---------------------------------------------------------------------------
# Supabase helper functions — stubs
# ---------------------------------------------------------------------------

def _get_installer_by_token(access_token: str) -> dict | None:
    """
    Fetch a single installer record by their unique access_token.

    Parameters
    ----------
    access_token : str
        The UUID token passed via the ``?access_token=`` query param.

    Returns
    -------
    dict | None
        The installer row as a dict, or ``None`` if not found.
    """
    try:
        response = (
            supabase.table("installers")
            .select("*")
            .eq("access_token", access_token)
            .single()
            .execute()
        )
        return response.data
    except Exception:
        return None


def _advance_installer_stage(installer_id: str, next_stage: str) -> bool:
    """
    Update the installer's ``current_stage`` in Supabase.

    Parameters
    ----------
    installer_id : str
        The installer's UUID primary key.
    next_stage : str
        One of ``'stage_1'``, ``'stage_2'``, or ``'complete'``.

    Returns
    -------
    bool
        ``True`` on success, ``False`` on failure.
    """
    try:
        supabase.table("installers").update(
            {"current_stage": next_stage, "current_status": "pending_review"}
        ).eq("id", installer_id).execute()
        return True
    except Exception:
        return False


def _get_document_requirements(stage: str, scope: str | None = None) -> list[dict]:
    """
    Fetch document requirement rows for a given stage, optionally filtered
    by scope (``'company'`` or ``'person'``).

    Parameters
    ----------
    stage : str
        One of ``'stage_1'``, ``'stage_2'``.
    scope : str | None
        If provided, filters by ``scope`` column.

    Returns
    -------
    list[dict]
        List of document_requirement rows.
    """
    try:
        query = (
            supabase.table("document_requirements")
            .select("*")
            .eq("stage", stage)
            .eq("installer_upload", True)
        )
        if scope:
            query = query.eq("scope", scope)
        return query.execute().data or []
    except Exception:
        return []


def _submit_document(
    installer_id: str,
    requirement_id: str,
    file_path: str,
    personnel_id: str | None = None,
    expiry_date: str | None = None,
) -> bool:
    """
    Insert or upsert a document_submission record.

    Parameters
    ----------
    installer_id : str
        FK to ``installers.id``.
    requirement_id : str
        FK to ``document_requirements.id``.
    file_path : str
        Supabase Storage path for the uploaded file.
    personnel_id : str | None
        FK to ``personnel.id`` — only required for person-scoped documents.
    expiry_date : str | None
        ISO date string (``YYYY-MM-DD``) if the document has an expiry.

    Returns
    -------
    bool
        ``True`` on success, ``False`` on failure.
    """
    payload = {
        "installer_id": installer_id,
        "requirement_id": requirement_id,
        "file_path": file_path,
        "status": "pending_review",
        "personnel_id": personnel_id,
        "expiry_date": expiry_date,
    }
    try:
        supabase.table("document_submissions").upsert(payload).execute()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------

def main() -> None:
    """Application entry point — renders the selected portal view."""
    view = render_sidebar()

    if view == "installer":
        render_installer_portal()
    else:
        render_admin_portal()


if __name__ == "__main__" or True:
    # Streamlit runs the module directly, so the guard is always True.
    main()
