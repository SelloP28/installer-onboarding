"""
verification package — Rules and Vision Evaluation Engine
==========================================================
Exports:
    evaluate_gate_0       - Orchestrates rules + vision and updates Supabase
    evaluate_rules        - Deterministic rules evaluation
    analyze_nda_document  - Google Cloud Vision extraction & signature detection
    RulesResult           - Dataclass for rules evaluation
    VisionResult          - Dataclass for vision extraction
    VerificationResult    - Consolidated decision and telemetry
"""

from verification.rules import RulesResult, evaluate_rules, is_valid_cipc
from verification.vision import VisionResult, analyze_nda_document
from verification.engine import VerificationResult, evaluate_gate_0

__all__ = [
    "evaluate_gate_0",
    "evaluate_rules",
    "is_valid_cipc",
    "analyze_nda_document",
    "RulesResult",
    "VisionResult",
    "VerificationResult",
]
