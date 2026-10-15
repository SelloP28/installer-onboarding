"""
verification/rules.py — Deterministic Rules Engine for Gate 0
==============================================================
Evaluates Gate 0 structured form data without requiring AI or OCR.

Requirements enforced:
1. Three Knock-Out criteria (ALWAYS route to needs_review, never auto-reject):
   - Blank DoL Electrical Contractor Registration Number
   - Empty CoC-authorised personnel list
   - "No" to required tools and equipment
2. Mandatory fields validation:
   - All required fields must be non-empty.
3. Format validation:
   - CIPC registration number must match standard South African format
     (e.g., YYYY/NNNNNN/NN or registered variants).
   - Valid contact email format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# Standard CIPC format: YYYY/NNNNNN/NN (e.g. 2021/123456/07)
# Also allows:
# - CK prefix (e.g. CK1998/012345/23 or CK98/12345/23)
# - Variations with spaces around slashes
# - Enterprise number format starting with letter + 9-10 digits
CIPC_REGEX = re.compile(
    r"^(?:(?:CK\s*)?(?:19\d{2}|20\d{2}|\d{2})\s*/\s*\d{5,7}\s*/\s*\d{2}|[A-Z]\d{9,10})$",
    re.IGNORECASE,
)

# Email address basic syntax
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class RulesResult:
    """Encapsulates the outcome of evaluating structured form rules."""
    passed: bool
    knockouts: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    format_errors: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    all_issues: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def has_knockouts(self) -> bool:
        return len(self.knockouts) > 0

    @property
    def total_issue_count(self) -> int:
        return len(self.all_issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "has_knockouts": self.has_knockouts,
            "knockouts": self.knockouts,
            "missing_fields": self.missing_fields,
            "format_errors": self.format_errors,
            "errors": self.errors,
            "all_issues": self.all_issues,
            "total_issue_count": self.total_issue_count,
            "details": self.details,
        }


_MANDATORY_FIELD_SPECS: list[tuple[str, str]] = [
    ("company_name", "Company Name"),
    ("cipc_reg_number", "CIPC Registration Number"),
    ("tax_clearance_number", "Tax Clearance Number"),
    ("bbbee_level", "B-BBEE Level"),
    ("physical_address", "Physical Address"),
    ("contact_name", "Contact Person Full Name"),
    ("contact_position", "Contact Person Position"),
    ("contact_phone", "Contact Person Phone"),
    ("contact_email", "Contact Person Email"),
    ("dol_reg_number", "DoL Electrical Contractor Registration Number"),
    ("wiremans_licence_number", "Wireman's Licence Number"),
    ("declaration_name", "Declaration Full Name"),
    ("declaration_position", "Declaration Position"),
    ("declaration_signature", "Declaration Signature"),
]


def evaluate_rules(form_values: dict[str, Any]) -> RulesResult:
    """
    Evaluate Gate 0 submission data against deterministic compliance rules.

    Parameters
    ----------
    form_values : dict
        Dictionary of submitted prequalification form values.

    Returns
    -------
    RulesResult
        Detailed rule evaluation containing pass/fail flags, knockouts,
        missing fields, and format errors.
    """
    knockouts: list[str] = []
    missing_fields: list[str] = []
    format_errors: list[str] = []
    details: dict[str, Any] = {}

    # =========================================================================
    # 1. Knock-Out Criteria
    # =========================================================================

    # KO 1: Blank DoL Electrical Contractor Registration Number
    dol_reg = str(form_values.get("dol_reg_number") or "").strip()
    if not dol_reg:
        knockouts.append(
            "Knock-out: Blank Department of Labour (DoL) Electrical Contractor Registration Number"
        )
        details["dol_reg_number"] = "missing"
    else:
        details["dol_reg_number"] = "provided"

    # KO 2: Empty CoC-authorised personnel list
    coc_list = form_values.get("coc_personnel") or []
    valid_coc_personnel = [
        p for p in coc_list
        if isinstance(p, dict) and p.get("name", "").strip() and p.get("reg_number", "").strip()
    ]
    if len(valid_coc_personnel) == 0:
        knockouts.append(
            "Knock-out: Empty CoC-authorised personnel roster (at least one registered person with valid number required)"
        )
        details["coc_personnel_count"] = 0
    else:
        details["coc_personnel_count"] = len(valid_coc_personnel)

    # KO 3: "No" to required tools
    tools_available = form_values.get("tools_available")
    if tools_available is not True:
        knockouts.append(
            "Knock-out: Applicant declared 'No' to having required tools and equipment available"
        )
        details["tools_available"] = False
    else:
        details["tools_available"] = True

    # =========================================================================
    # 2. Mandatory Fields Validation
    # =========================================================================
    for field_key, field_label in _MANDATORY_FIELD_SPECS:
        val = form_values.get(field_key)
        val_str = str(val or "").strip()
        if not val_str:
            # Avoid duplicate reporting if dol_reg_number was already flagged as a knockout
            if field_key == "dol_reg_number":
                continue
            missing_fields.append(f"Missing mandatory field: {field_label}")
            details[f"{field_key}_status"] = "missing"
        else:
            details[f"{field_key}_status"] = "present"

    # Geographic areas check
    geo_areas = form_values.get("geographic_areas")
    if not geo_areas or not isinstance(geo_areas, list) or len(geo_areas) == 0:
        missing_fields.append("Missing mandatory field: Geographic Areas of Operation (at least one province required)")
        details["geographic_areas_status"] = "missing"
    else:
        details["geographic_areas_status"] = "present"

    # =========================================================================
    # 3. Format Validation
    # =========================================================================

    # CIPC Registration Number Format
    cipc_raw = str(form_values.get("cipc_reg_number") or "").strip()
    if cipc_raw:
        if not is_valid_cipc(cipc_raw):
            format_errors.append(
                f"Invalid CIPC registration number format: '{cipc_raw}'. "
                "Expected standard format YYYY/NNNNNN/NN (e.g., 2021/123456/07)."
            )
            details["cipc_valid"] = False
        else:
            details["cipc_valid"] = True

    # Contact Email Format
    contact_email = str(form_values.get("contact_email") or "").strip()
    if contact_email:
        if not EMAIL_REGEX.match(contact_email):
            format_errors.append(f"Invalid contact email address: '{contact_email}'")
            details["email_valid"] = False
        else:
            details["email_valid"] = True

    # Combine regular errors (non-knockout issues)
    errors = missing_fields + format_errors
    all_issues = knockouts + errors
    passed = (len(all_issues) == 0)

    return RulesResult(
        passed=passed,
        knockouts=knockouts,
        missing_fields=missing_fields,
        format_errors=format_errors,
        errors=errors,
        all_issues=all_issues,
        details=details,
    )


def is_valid_cipc(value: str) -> bool:
    """
    Validate South African CIPC company registration number format.

    Examples of valid formats:
    - 2021/123456/07
    - 1998/012345/23
    - CK 1995/123456/23
    - 2020 / 654321 / 07
    """
    cleaned = value.strip()
    return bool(CIPC_REGEX.match(cleaned))
