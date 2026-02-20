"""
AR-003 Phase 2: Feature Operations Module

Extracted from modeling/__init__.py for maintainability.
Contains feature error handling, TNP failure tracking, and safe operation wrappers.

This module provides:
- TNP failure recording and consumption
- Error code classification
- Safe operation wrapper with fallback support
- Operation error details builder
"""

from typing import Optional, Any, Callable, Tuple
from loguru import logger
from dataclasses import asdict

from config.feature_flags import is_enabled


# ==============================================================================
# TNP FAILURE TRACKING
# ==============================================================================

def record_tnp_failure(
    pending_tnp_failure: dict,
    *,
    feature,
    category: str,
    reference_kind: str,
    reason: str,
    expected: Optional[int] = None,
    resolved: Optional[int] = None,
    strict: bool = False,
) -> dict:
    """
    Records a TNP failure for later consumption by _safe_operation.
    
    Args:
        pending_tnp_failure: Current pending failure dict (from Body._pending_tnp_failure)
        feature: The feature that caused the failure
        category: Failure category ("missing_ref", "mismatch", "drift")
        reference_kind: Kind of reference ("face", "edge", etc.)
        reason: Human-readable reason
        expected: Expected number of references
        resolved: Number of successfully resolved references
        strict: Whether this is a strict failure
    
    Returns:
        Updated pending_tnp_failure dict
    """
    if feature is None:
        return None

    category_norm = str(category or "").strip().lower() or "missing_ref"
    if category_norm not in {"missing_ref", "mismatch", "drift"}:
        category_norm = "missing_ref"

    kind_norm = str(reference_kind or "").strip().lower() or "reference"
    next_action_map = {
        "missing_ref": f"{kind_norm.capitalize()}-Referenz neu waehlen und Feature erneut ausfuehren.",
        "mismatch": f"{kind_norm.capitalize()}-ShapeID und Index stimmen nicht ueberein. Referenz neu waehlen.",
        "drift": "Referenzierte Geometrie ist gedriftet. Feature mit kleineren Werten erneut anwenden.",
    }

    payload = {
        "category": category_norm,
        "reference_kind": kind_norm,
        "reason": str(reason or "").strip() or "unspecified",
        "strict": bool(strict),
        "next_action": next_action_map.get(
            category_norm,
            "Referenzen pruefen und Feature erneut ausfuehren.",
        ),
        "feature_id": getattr(feature, "id", ""),
        "feature_name": getattr(feature, "name", ""),
        "feature_class": feature.__class__.__name__,
    }
    if expected is not None:
        try:
            payload["expected"] = max(0, int(expected))
        except Exception:
            pass
    if resolved is not None:
        try:
            payload["resolved"] = max(0, int(resolved))
        except Exception:
            pass
    return payload


def consume_tnp_failure(
    pending_tnp_failure: dict,
    feature=None
) -> Tuple[Optional[dict], dict]:
    """
    Returns and clears the last TNP failure category.
    
    Args:
        pending_tnp_failure: Current pending failure dict
        feature: Optional feature to match against
    
    Returns:
        Tuple of (consumed failure dict or None, updated pending dict which is now None)
    """
    pending = pending_tnp_failure
    if not pending:
        return None, None
    if feature is None:
        return dict(pending), None

    pending_feature_id = str(pending.get("feature_id") or "")
    feature_id = str(getattr(feature, "id", "") or "")
    if pending_feature_id and feature_id and pending_feature_id != feature_id:
        return None, pending
    return dict(pending), None


# ==============================================================================
# ERROR CODE CLASSIFICATION
# ==============================================================================

def classify_error_code(error_code: str) -> Tuple[str, str]:
    """
    Maps error code to stable envelope classes for UI/QA.
    
    Args:
        error_code: The error code string
    
    Returns:
        Tuple of (status_class, severity)
    """
    code_norm = str(error_code or "").strip().lower()
    warning_codes = {
        "fallback_used",
        "tnp_ref_drift",
    }
    blocked_codes = {
        "blocked_by_upstream_error",
        "fallback_blocked_strict",
    }
    critical_codes = {
        "rebuild_finalize_failed",
    }
    if code_norm in critical_codes:
        return "CRITICAL", "critical"
    if code_norm in warning_codes:
        return "WARNING_RECOVERABLE", "warning"
    if code_norm in blocked_codes:
        return "BLOCKED", "blocked"
    return "ERROR", "error"


def default_next_action_for_code(error_code: str) -> str:
    """
    Returns the default next action for an error code.
    
    Args:
        error_code: The error code string
    
    Returns:
        Human-readable next action string
    """
    defaults = {
        "operation_failed": "Parameter pruefen oder Referenz neu auswaehlen und erneut ausfuehren.",
        "fallback_used": "Ergebnis wurde via Fallback erzeugt. Geometrie pruefen und Parameter/Referenz ggf. nachziehen.",
        "fallback_failed": "Feature vereinfachen und mit kleineren Werten erneut versuchen.",
        "fallback_blocked_strict": "Feature neu referenzieren oder self_heal_strict deaktivieren.",
        "blocked_by_upstream_error": "Zuerst das vorherige fehlgeschlagene Feature beheben.",
        "no_result_solid": "Eingaben/Referenzen pruefen, da kein Ergebnis-Solid erzeugt wurde.",
        "self_heal_rollback_invalid_result": "Featureparameter reduzieren oder Referenzflaeche anpassen.",
        "self_heal_rollback_geometry_drift": "Lokalen Modifier mit kleineren Werten erneut anwenden.",
        "self_heal_blocked_topology_warning": "Topologie-Referenzen pruefen und Feature neu auswaehlen.",
        "tnp_ref_missing": "Topologie-Referenz neu waehlen und Rebuild erneut ausfuehren.",
        "tnp_ref_mismatch": "ShapeID/Index-Referenz stimmt nicht ueberein. Referenz neu waehlen.",
        "tnp_ref_drift": "Referenzierte Geometrie ist gedriftet. Feature mit kleineren Werten erneut anwenden.",
        "rebuild_finalize_failed": "Rebuild erneut ausfuehren oder letzte stabile Aenderung rueckgaengig machen.",
        "ocp_api_unavailable": "OCP-Build pruefen oder alternative Operation verwenden.",
    }
    return defaults.get(
        error_code,
        "Fehlerdetails pruefen und den letzten gueltigen Bearbeitungsschritt wiederholen.",
    )


# ==============================================================================
# OPERATION ERROR DETAILS BUILDER
# ==============================================================================

def build_operation_error_details(
    *,
    op_name: str,
    code: str,
    message: str,
    feature=None,
    hint: str = "",
    fallback_error: str = "",
    collect_feature_reference_payload_func: Callable = None,
) -> dict:
    """
    Builds a standardized operation error details dict.
    
    Args:
        op_name: Operation name
        code: Error code
        message: Error message
        feature: Optional feature that caused the error
        hint: Optional hint for the user
        fallback_error: Optional fallback error message
        collect_feature_reference_payload_func: Optional function to collect feature refs
    
    Returns:
        Standardized error details dict
    """
    status_class, severity = classify_error_code(code)
    details = {
        "schema": "error_envelope_v1",
        "code": code,
        "operation": op_name,
        "message": message,
        "status_class": status_class,
        "severity": severity,
    }
    if feature is not None:
        details["feature"] = {
            "id": getattr(feature, "id", ""),
            "name": getattr(feature, "name", ""),
            "class": feature.__class__.__name__,
        }
    
    # Collect feature references if function provided
    if collect_feature_reference_payload_func and feature is not None:
        try:
            refs = collect_feature_reference_payload_func(feature)
            if refs:
                details["refs"] = refs
        except Exception:
            pass
    
    next_action = hint or default_next_action_for_code(code)
    if next_action:
        details["hint"] = next_action
        details["next_action"] = next_action
    if fallback_error:
        details["fallback_error"] = fallback_error
    return details


# ==============================================================================
# STATUS DETAILS NORMALIZATION
# ==============================================================================

def normalize_status_details_for_load(status_details: Any) -> dict:
    """
    Backward compatibility for persisted status_details.
    
    Legacy files can contain `code` without `status_class`/`severity`.
    When loading, these fields are deterministically filled in.
    
    Args:
        status_details: The status_details dict or any value
    
    Returns:
        Normalized status_details dict
    """
    if not isinstance(status_details, dict):
        return {}

    normalized = dict(status_details)
    code = str(normalized.get("code", "") or "").strip()
    if code:
        normalized.setdefault("schema", "error_envelope_v1")
    has_status_class = bool(str(normalized.get("status_class", "") or "").strip())
    has_severity = bool(str(normalized.get("severity", "") or "").strip())
    if code and (not has_status_class or not has_severity):
        status_class, severity = classify_error_code(code)
        normalized.setdefault("status_class", status_class)
        normalized.setdefault("severity", severity)

    hint = str(normalized.get("hint", "") or "").strip()
    next_action = str(normalized.get("next_action", "") or "").strip()
    if hint and not next_action:
        normalized["next_action"] = hint
        next_action = hint
    if next_action and not hint:
        normalized["hint"] = next_action
        hint = next_action
    if code and not hint and not next_action:
        action = default_next_action_for_code(code)
        if action:
            normalized["hint"] = action
            normalized["next_action"] = action
    return normalized


# ==============================================================================
# SAFE OPERATION WRAPPER
# ==============================================================================

def safe_operation(
    op_name: str,
    op_func: Callable,
    fallback_func: Optional[Callable] = None,
    feature=None,
    pending_tnp_failure: dict = None,
    collect_feature_reference_diagnostics_func: Callable = None,
    collect_feature_reference_payload_func: Callable = None,
    feature_has_topological_references_func: Callable = None,
) -> Tuple[Any, str, dict, dict]:
    """
    Wrapper for critical CAD operations.
    Catches crashes and allows fallbacks.
    
    Args:
        op_name: Operation name for logging
        op_func: Primary operation function
        fallback_func: Optional fallback function
        feature: The feature being processed
        pending_tnp_failure: Current pending TNP failure dict
        collect_feature_reference_diagnostics_func: Function to collect feature ref diagnostics
        collect_feature_reference_payload_func: Function to collect feature ref payload
        feature_has_topological_references_func: Function to check if feature has topo refs
    
    Returns:
        Tuple of (result, status, last_operation_error, last_operation_error_details, updated_pending)
        - result: The operation result or None on failure
        - status: "SUCCESS", "WARNING", or "ERROR"
        - last_operation_error: Error message string
        - last_operation_error_details: Detailed error dict
        - updated_pending: Updated pending_tnp_failure dict
    """
    last_operation_error = ""
    last_operation_error_details = {}
    
    try:
        result = op_func()
        
        if result is None:
            raise ValueError("Operation returned None")
        
        if hasattr(result, 'is_valid') and not result.is_valid():
            raise ValueError("Result geometry is invalid")

        # Consume any pending TNP failure
        tnp_notice, updated_pending = consume_tnp_failure(pending_tnp_failure, feature)
        notice_category = (
            str((tnp_notice or {}).get("category") or "").strip().lower()
            if isinstance(tnp_notice, dict)
            else ""
        )
        if notice_category == "drift":
            notice_reason = str(tnp_notice.get("reason") or "").strip()
            notice_msg = "TNP-Referenzdrift erkannt; Geometric-Fallback wurde verwendet."
            if notice_reason:
                notice_msg = f"{notice_msg} reason={notice_reason}"
            last_operation_error = notice_msg
            drift_hint = str(tnp_notice.get("next_action") or "").strip()
            last_operation_error_details = build_operation_error_details(
                op_name=op_name,
                code="tnp_ref_drift",
                message=notice_msg,
                feature=feature,
                hint=drift_hint,
                collect_feature_reference_payload_func=collect_feature_reference_payload_func,
            )
            last_operation_error_details["tnp_failure"] = tnp_notice
            return result, "WARNING", last_operation_error, last_operation_error_details, updated_pending

        return result, "SUCCESS", last_operation_error, last_operation_error_details, updated_pending
        
    except Exception as e:
        err_msg = str(e).strip() or e.__class__.__name__
        
        # Collect feature reference diagnostics if available
        if collect_feature_reference_diagnostics_func and feature is not None:
            try:
                ref_diag = collect_feature_reference_diagnostics_func(feature)
                if ref_diag and "refs:" not in err_msg:
                    err_msg = f"{err_msg} | refs: {ref_diag}"
            except Exception:
                pass
        
        last_operation_error = err_msg
        
        # Consume TNP failure
        tnp_failure, updated_pending = consume_tnp_failure(pending_tnp_failure, feature)
        tnp_code_by_category = {
            "missing_ref": "tnp_ref_missing",
            "mismatch": "tnp_ref_mismatch",
            "drift": "tnp_ref_drift",
        }
        tnp_category = (
            str((tnp_failure or {}).get("category") or "").strip().lower()
            if isinstance(tnp_failure, dict)
            else ""
        )
        error_code = tnp_code_by_category.get(tnp_category, "operation_failed")
        
        # Check for dependency errors
        dependency_error = None
        if error_code == "operation_failed":
            dep_msg = str(e).strip() or e.__class__.__name__
            dep_msg_lower = dep_msg.lower()
            is_direct_dep_error = isinstance(e, (ImportError, ModuleNotFoundError, AttributeError))
            ocp_markers = (
                "ocp",
                "no module named 'ocp",
                "cannot import name",
                "has no attribute",
            )
            is_ocp_dependency_error = is_direct_dep_error and any(marker in dep_msg_lower for marker in ocp_markers)
            if (not is_ocp_dependency_error) and any(marker in dep_msg_lower for marker in ("cannot import name", "no module named", "has no attribute")):
                is_ocp_dependency_error = "ocp" in dep_msg_lower
            if is_ocp_dependency_error:
                error_code = "ocp_api_unavailable"
                dependency_error = {
                    "kind": "ocp_api",
                    "exception": e.__class__.__name__,
                    "detail": dep_msg,
                }
        
        tnp_hint = ""
        if isinstance(tnp_failure, dict):
            tnp_hint = str(tnp_failure.get("next_action") or "").strip()
        
        last_operation_error_details = build_operation_error_details(
            op_name=op_name,
            code=error_code,
            message=err_msg,
            feature=feature,
            hint=tnp_hint,
            collect_feature_reference_payload_func=collect_feature_reference_payload_func,
        )
        
        if isinstance(tnp_failure, dict):
            last_operation_error_details["tnp_failure"] = tnp_failure
        if dependency_error:
            last_operation_error_details["runtime_dependency"] = dependency_error
        
        logger.warning(f"Feature '{op_name}' fehlgeschlagen: {err_msg}")
        
        # Try fallback if available
        if fallback_func:
            strict_self_heal = is_enabled("self_heal_strict")
            strict_topology_policy = is_enabled("strict_topology_fallback_policy")
            
            has_topology_refs = False
            if feature_has_topological_references_func and feature is not None:
                try:
                    has_topology_refs = feature_has_topological_references_func(feature)
                except Exception:
                    pass
            
            if has_topology_refs and (strict_self_heal or strict_topology_policy):
                policy_reason = (
                    "Strict Self-Heal"
                    if strict_self_heal
                    else "strict_topology_fallback_policy"
                )
                last_operation_error = (
                    f"Primaerpfad fehlgeschlagen: {err_msg}; "
                    f"{policy_reason} blockiert Fallback bei Topologie-Referenzen"
                )
                last_operation_error_details = build_operation_error_details(
                    op_name=op_name,
                    code="fallback_blocked_strict",
                    message=last_operation_error,
                    feature=feature,
                    hint="Feature neu referenzieren oder Parameter reduzieren.",
                    collect_feature_reference_payload_func=collect_feature_reference_payload_func,
                )
                if isinstance(tnp_failure, dict):
                    last_operation_error_details["tnp_failure"] = tnp_failure
                logger.error(
                    f"{policy_reason}: Fallback fuer '{op_name}' blockiert "
                    "(Topologie-Referenzen aktiv)."
                )
                return None, "ERROR", last_operation_error, last_operation_error_details, updated_pending
            
            logger.debug(f"→ Versuche Fallback fuer '{op_name}'...")
            try:
                res_fallback = fallback_func()
                if res_fallback:
                    last_operation_error = f"Primaerpfad fehlgeschlagen: {err_msg}; Fallback wurde verwendet"
                    last_operation_error_details = build_operation_error_details(
                        op_name=op_name,
                        code="fallback_used",
                        message=last_operation_error,
                        feature=feature,
                        collect_feature_reference_payload_func=collect_feature_reference_payload_func,
                    )
                    logger.debug(f"✓ Fallback fuer '{op_name}' erfolgreich.")
                    return res_fallback, "WARNING", last_operation_error, last_operation_error_details, updated_pending
            except Exception as e2:
                fallback_msg = str(e2).strip() or e2.__class__.__name__
                last_operation_error = (
                    f"Primaerpfad fehlgeschlagen: {err_msg}; Fallback fehlgeschlagen: {fallback_msg}"
                )
                last_operation_error_details = build_operation_error_details(
                    op_name=op_name,
                    code="fallback_failed",
                    message=last_operation_error,
                    feature=feature,
                    fallback_error=fallback_msg,
                    collect_feature_reference_payload_func=collect_feature_reference_payload_func,
                )
                logger.error(f"✗ Auch Fallback fehlgeschlagen: {fallback_msg}")
        
        return None, "ERROR", last_operation_error, last_operation_error_details, updated_pending


# ==============================================================================
# LEGACY ALIASES FOR BACKWARD COMPATIBILITY
# ==============================================================================

# These aliases allow existing code to import from this module
# using the original function names from Body class

_record_tnp_failure = record_tnp_failure
_consume_tnp_failure = consume_tnp_failure
_classify_error_code = classify_error_code
_default_next_action_for_code = default_next_action_for_code
_build_operation_error_details = build_operation_error_details
_normalize_status_details_for_load = normalize_status_details_for_load
_safe_operation = safe_operation
