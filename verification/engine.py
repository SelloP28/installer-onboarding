"""
verification/engine.py — Gate 0 Verification Engine Orchestrator
================================================================
Orchestrates:
1. Rules engine on structured form data first (deterministic checks).
2. Vision analysis on the uploaded NDA PDF (Google Cloud Vision).
3. Final decision logic:
   - All rules pass AND NDA extracts cleanly/matches → current_stage='stage_1'
   - Single specific fixable gap → current_status='needs_fixes' with clear reason
   - Knockouts or multiple failures → current_status='needs_review' (never auto-reject)
4. Persists complete telemetry, rules output, vision output, and raw confidence scores
   to the verification_logs table for future threshold calibration.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from supabase import Client

from verification.rules import RulesResult, evaluate_rules
from verification.vision import VisionResult, analyze_nda_document


logger = logging.getLogger("compliance.verification")


@dataclass
class VerificationResult:
    """Consolidated outcome of the Gate 0 verification process."""
    installer_id: str
    decision: str                     # 'stage_1' | 'needs_fixes' | 'needs_review'
    current_stage: str                # 'gate_0' | 'stage_1'
    current_status: str               # 'approved' | 'needs_fixes' | 'needs_review'
    reason: str
    rules_result: RulesResult
    vision_result: VisionResult
    raw_confidence: dict[str, Any] = field(default_factory=dict)

    @property
    def passed_to_stage_1(self) -> bool:
        return self.decision == "stage_1"

    @property
    def requires_fixes(self) -> bool:
        return self.decision == "needs_fixes"

    @property
    def requires_review(self) -> bool:
        return self.decision == "needs_review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "installer_id": self.installer_id,
            "decision": self.decision,
            "current_stage": self.current_stage,
            "current_status": self.current_status,
            "reason": self.reason,
            "rules_result": self.rules_result.to_dict(),
            "vision_result": self.vision_result.to_dict(),
            "raw_confidence": self.raw_confidence,
        }


def evaluate_gate_0(
    supabase: Client,
    installer_id: str,
    form_values: dict[str, Any],
    nda_bytes: bytes,
    gcp_credentials_info: dict | str | None = None,
) -> VerificationResult:
    """
    Evaluate Gate 0 submission: rules first, then vision.

    Parameters
    ----------
    supabase : Client
        Supabase client for updating status and persisting verification logs.
    installer_id : str
        The UUID of the installer record.
    form_values : dict
        Structured pre-qualification form data.
    nda_bytes : bytes
        Raw bytes of the uploaded NDA PDF.
    gcp_credentials_info : dict | str | None
        Optional explicit GCP credentials.

    Returns
    -------
    VerificationResult
        Consolidated decision, status updates, and raw extraction telemetry.
    """
    company_name = str(form_values.get("company_name", "")).strip()
    cipc_number = str(form_values.get("cipc_reg_number", "")).strip()

    # =========================================================================
    # Step 1: Rules Engine (Deterministic check on structured data)
    # =========================================================================
    rules_res = evaluate_rules(form_values)

    # =========================================================================
    # Step 2: Vision Analysis on NDA (Google Cloud Vision)
    # =========================================================================
    vision_res = analyze_nda_document(
        nda_bytes=nda_bytes,
        expected_company_name=company_name,
        expected_cipc=cipc_number,
        gcp_credentials_info=gcp_credentials_info,
    )

    # Raw confidence payload captured without thresholding
    raw_confidence = {
        "rules_telemetry": {
            "knockouts_count": len(rules_res.knockouts),
            "missing_fields_count": len(rules_res.missing_fields),
            "format_errors_count": len(rules_res.format_errors),
        },
        "vision_telemetry": vision_res.raw_confidence,
    }

    # =========================================================================
    # Step 3: Decision Logic
    # =========================================================================
    decision: str
    current_stage: str
    current_status: str
    reason: str

    # Branch A: Any Knock-Out present -> ALWAYS needs_review (Never auto-reject)
    if rules_res.has_knockouts:
        decision = "needs_review"
        current_stage = "gate_0"
        current_status = "needs_review"
        ko_summary = "; ".join(rules_res.knockouts)
        reason = f"Knock-out criteria flagged: {ko_summary}. Submission routed to compliance officer for review."

    else:
        # Collect all non-knockout gaps across rules and vision
        all_gaps: list[str] = list(rules_res.errors) + list(vision_res.errors)

        # Branch B: All rules pass AND NDA cleanly extracts & matches -> Stage 1
        if len(all_gaps) == 0:
            decision = "stage_1"
            current_stage = "stage_1"
            current_status = "approved"
            reason = "All Gate 0 pre-qualification rules and NDA verification checks passed successfully."

        # Branch C: Exactly ONE single, specific, fixable gap -> needs_fixes
        elif len(all_gaps) == 1:
            decision = "needs_fixes"
            current_stage = "gate_0"
            current_status = "needs_fixes"
            single_gap = all_gaps[0]
            reason = f"Please correct the following item to proceed: {single_gap}"

        # Branch D: Multiple failures or other uncertainty -> needs_review
        else:
            decision = "needs_review"
            current_stage = "gate_0"
            current_status = "needs_review"
            issues_summary = "; ".join(all_gaps)
            reason = (
                f"Multiple compliance issues require manual verification ({len(all_gaps)} items): "
                f"{issues_summary}. Routed to compliance officer."
            )

    result = VerificationResult(
        installer_id=installer_id,
        decision=decision,
        current_stage=current_stage,
        current_status=current_status,
        reason=reason,
        rules_result=rules_res,
        vision_result=vision_res,
        raw_confidence=raw_confidence,
    )

    # =========================================================================
    # Step 4: Persist Results to Supabase
    # =========================================================================
    _persist_verification(supabase, result)

    return result


def _persist_verification(supabase: Client, result: VerificationResult) -> None:
    """Update installer state and log telemetry to verification_logs."""
    installer_id = result.installer_id

    # 1. Update installer table
    # Fallback to 'pending_review' if the database has not yet executed the
    # updated CHECK constraint for 'needs_review'.
    status_to_write = result.current_status
    installer_payload = {
        "current_stage": result.current_stage,
        "current_status": status_to_write,
        "status_reason": result.reason,
    }

    try:
        supabase.table("installers").update(installer_payload).eq("id", installer_id).execute()
    except Exception as exc:
        # If check constraint fails on 'needs_review', fall back to 'pending_review'
        if status_to_write == "needs_review":
            installer_payload["current_status"] = "pending_review"
            try:
                supabase.table("installers").update(installer_payload).eq("id", installer_id).execute()
            except Exception as inner_exc:
                logger.error("Failed to update installer status: %s", inner_exc)
        else:
            logger.error("Failed to update installer status: %s", exc)

    # 2. Insert into verification_logs table
    log_payload = {
        "installer_id": installer_id,
        "stage": "gate_0",
        "rules_passed": result.rules_result.passed,
        "rules_result": json.dumps(result.rules_result.to_dict()),
        "vision_result": json.dumps(result.vision_result.to_dict()),
        "raw_confidence": json.dumps(result.raw_confidence),
        "decision": result.decision,
        "reason": result.reason,
    }

    try:
        supabase.table("verification_logs").insert(log_payload).execute()
    except Exception as exc:
        # verification_logs table may not exist if user hasn't run the migration yet;
        # log warning without breaking the user flow.
        logger.warning("Could not persist to verification_logs: %s", exc)

    # 3. Update document_submissions statuses
    try:
        nda_status = "approved" if result.decision == "stage_1" else (
            "rejected" if result.decision == "needs_fixes" else "pending_review"
        )
        supabase.table("document_submissions").update({
            "status": nda_status,
            "rejection_reason": result.reason if nda_status == "rejected" else None,
        }).eq("installer_id", installer_id).execute()
    except Exception as exc:
        logger.debug("Could not update document_submissions status: %s", exc)
