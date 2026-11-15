"""Fail-closed firmware flashing orchestration.

Only engines explicitly registered as validated may ever receive a device-write
request. This module intentionally ships with no production write engine enabled.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any

from device_service import (
    _APPROVAL_LOCK, _APPROVED_TOKENS, _PENDING_CHALLENGES,
    _APPROVAL_TTL_SECONDS, _run, _tool_path, android_properties,
    audit, discover_android, inspect_firmware_zip,
)

# A production engine must be separately implemented, hardware-tested and
# registered with an exact supported model/board allow-list and signed package
# verifier. Never infer support from manufacturer name alone.
ENGINE_REGISTRY: dict[str, dict[str, Any]] = {
    "google_fastboot": {
        "label": "Google / Android Fastboot",
        "status": "not_validated",
        "supported_models": [],
        "write_enabled": False,
        "reason": "No model-specific signed-image verifier and partition procedure has passed physical-device validation.",
    },
    "samsung_download": {
        "label": "Samsung Download Mode",
        "status": "not_implemented",
        "supported_models": [],
        "write_enabled": False,
        "reason": "A validated, authorised Samsung service flashing adapter is not integrated.",
    },
    "qualcomm_edl": {
        "label": "Qualcomm EDL 9008",
        "status": "not_implemented",
        "supported_models": [],
        "write_enabled": False,
        "reason": "Exact SoC/board allow-lists and OEM-authorised signed programmer integration are not available.",
    },
    "mediatek_preloader": {
        "label": "MediaTek Preloader / BootROM",
        "status": "not_implemented",
        "supported_models": [],
        "write_enabled": False,
        "reason": "Exact SoC/board allow-lists and OEM-authorised signed Download Agent integration are not available.",
    },
}

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def flash_capabilities() -> dict[str, Any]:
    return {
        "ok": True,
        "approval_required": True,
        "execution_policy": "fail_closed",
        "engines": ENGINE_REGISTRY,
        "global_write_enabled": any(x["write_enabled"] for x in ENGINE_REGISTRY.values()),
        "required_gates": [
            "Exact device serial and live protocol identity",
            "Exact manufacturer, model, board and hardware revision",
            "Trusted OEM firmware provenance and cryptographic signature verification",
            "Exact partition map and anti-rollback / bootloader-state checks",
            "Required signed vendor programmer and compatible driver",
            "Model-specific physical-device validation",
            "Fresh single-use customer approval bound to device, package hash, engine and partition plan",
            "Live re-check immediately before the first write",
        ],
    }

def prepare_flash_plan(serial: str, firmware_path: str, engine_id: str) -> dict[str, Any]:
    if not serial or len(serial) > 128:
        raise ValueError("A valid selected device serial is required.")
    if engine_id not in ENGINE_REGISTRY:
        raise ValueError("Unknown flashing engine.")
    engine = ENGINE_REGISTRY[engine_id]
    if not engine["write_enabled"]:
        return {
            "ok": True, "plan_id": "", "flash_enabled": False,
            "approval_required": True, "serial": serial,
            "engine": engine, "firmware": {"verified": False},
            "partition_plan": [], "blockers": [engine["reason"]],
            "message": "No flash approval can be issued because this engine is not validated.",
        }

    identity = android_properties(serial)
    if not identity.get("ok"):
        raise ValueError(identity.get("error") or "Live device identity could not be verified.")
    props = identity.get("properties", {})
    package = Path(firmware_path).expanduser()
    if not package.is_file():
        raise ValueError("Firmware package does not exist.")
    inspection = inspect_firmware_zip(str(package))
    if not inspection.get("ok"):
        raise ValueError("Firmware archive failed integrity inspection.")
    # No engine may be activated by metadata string matches alone. A registered
    # engine must provide its own signature, board, rollback and partition verifier.
    blockers = [
        "The registered engine has not supplied an OEM signature-verification result.",
        "The registered engine has not supplied a verified exact-model partition plan.",
    ]
    return {
        "ok": True, "plan_id": "", "flash_enabled": False,
        "approval_required": True, "serial": serial,
        "device": props, "engine": engine,
        "firmware": {"file": package.name, "sha256": inspection["sha256"],
                     "size_bytes": inspection["size_bytes"],
                     "archive_integrity": True, "oem_signature_verified": False},
        "partition_plan": [], "blockers": blockers,
        "message": "Flash remains disabled until every engine-specific verification gate passes.",
    }

def create_flash_approval(serial: str, plan_id: str, package_sha256: str,
                          engine_id: str, partition_plan_sha256: str) -> dict[str, Any]:
    # No current engine is eligible. This prevents UI or API callers from
    # manufacturing an approval by submitting their own plan fields.
    engine = ENGINE_REGISTRY.get(engine_id)
    if not engine or not engine.get("write_enabled"):
        raise ValueError("Flash approval is unavailable: this engine is not validated.")
    raise ValueError("No verified flash plan exists for this engine.")

def execute_flash(serial: str, package_sha256: str, engine_id: str,
                  partition_plan_sha256: str, approval_token: str) -> dict[str, Any]:
    # Fail closed even if a client fabricates a request or reuses an old token.
    engine = ENGINE_REGISTRY.get(engine_id)
    if not engine or not engine.get("write_enabled"):
        audit("firmware_flash_blocked", {"serial": serial, "engine": engine_id,
              "reason": "engine_not_validated"})
        raise ValueError("Flashing blocked: no validated engine is enabled for this device family.")
    raise ValueError("Flashing blocked: no validated model-specific plan is registered.")
