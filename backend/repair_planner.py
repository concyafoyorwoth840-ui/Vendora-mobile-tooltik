"""Read-only automatic repair preparation and compatibility preflight.

This module deliberately does not execute flashing, unlock, erase, or reset commands.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any

from device_service import (
    _run, _tool_path, android_properties, classify_android, discover_android,
    inspect_firmware_zip, windows_usb_inventory, audit,
)

def _safe_text(value: Any) -> str:
    return str(value or "").strip()

def _read_archive_metadata(path: str) -> dict[str, Any]:
    p = Path(path).expanduser()
    inspected = inspect_firmware_zip(str(p))
    if not inspected.get("ok"):
        return {"ok": False, "reason": "Archive integrity check failed.", "inspection": inspected}
    metadata: list[dict[str, str]] = []
    try:
        with zipfile.ZipFile(p) as archive:
            candidates = [n for n in archive.namelist()
                          if Path(n).name.lower() in {
                              "android-info.txt", "metadata", "scatter.txt",
                              "manifest.xml", "flash-all.bat", "payload_properties.txt"
                          }]
            for name in candidates[:20]:
                info = archive.getinfo(name)
                if info.file_size > 1024 * 1024:
                    continue
                raw = archive.read(name)
                text = raw.decode("utf-8", errors="replace")
                metadata.append({"name": name, "text": text[:50000]})
    except (OSError, zipfile.BadZipFile) as exc:
        return {"ok": False, "reason": str(exc), "inspection": inspected}
    return {"ok": True, "inspection": inspected, "metadata": metadata}

def _driver_assessment(inventory: dict[str, Any], serial: str = "") -> dict[str, Any]:
    rows = inventory.get("devices", []) if isinstance(inventory, dict) else []
    problem = [x for x in rows if str(x.get("Status", "")).lower() not in {"ok", "started"}]
    relevant = [x for x in rows if any(k in json.dumps(x).lower()
                for k in ("android", "samsung", "qualcomm", "mediatek", "mtk", "adb", "fastboot", "9008"))]
    return {
        "inventory_supported": bool(inventory.get("supported")),
        "usb_device_count": len(rows),
        "relevant_interfaces": relevant[:30],
        "devices_reporting_problem_status": problem[:30],
        "status": ("driver_problem_reported" if problem else
                   "usb_inventory_available" if inventory.get("supported") else "windows_only"),
        "note": "Windows PnP status is a diagnostic clue, not proof that the correct vendor service driver or protocol is installed."
    }

def build_repair_plan(serial: str = "", symptom: str = "stuck_logo",
                      firmware_path: str = "", programmer_path: str = "") -> dict[str, Any]:
    allowed = {"stuck_logo", "boot_loop", "failed_update", "recovery_mode", "black_screen"}
    if symptom not in allowed:
        raise ValueError("Unsupported repair symptom")
    if serial and not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", serial):
        raise ValueError("Invalid device serial")

    found = discover_android()
    adb = next((x for x in found.get("adb", []) if x.get("serial") == serial), None) if serial else None
    fastboot = next((x for x in found.get("fastboot", []) if x.get("serial") == serial), None) if serial else None
    if not serial:
        candidates = found.get("adb", []) + found.get("fastboot", [])
        if len(candidates) == 1:
            selected = candidates[0]
            serial = selected.get("serial", "")
            adb = selected if selected in found.get("adb", []) else None
            fastboot = selected if selected in found.get("fastboot", []) else None

    identity: dict[str, Any] = {}
    props: dict[str, str] = {}
    mode = "not_detected"
    if adb:
        mode = "android_adb_" + _safe_text(adb.get("state"))
        if adb.get("state") == "device":
            result = android_properties(serial)
            if result.get("ok"):
                props = result.get("properties", {})
                identity = props.copy()
    elif fastboot:
        mode = "fastboot"
        for key in ("product", "variant", "version", "bootloader-version", "current-slot", "slot-count", "unlocked", "secure", "is-userspace"):
            result = _run([_tool_path("fastboot"), "-s", serial, "getvar", key], timeout=8)
            identity[key] = (result.get("stderr") or result.get("stdout") or "").strip()

    manufacturer = _safe_text(props.get("ro.product.manufacturer"))
    model = _safe_text(props.get("ro.product.model"))
    product = _safe_text(props.get("ro.product.device")) or _safe_text(identity.get("product"))
    fingerprint = _safe_text(props.get("ro.build.fingerprint"))
    chipset = next((_safe_text(props.get(k)) for k in (
        "ro.board.platform", "ro.hardware", "ro.boot.hardware", "ro.soc.model"
    ) if _safe_text(props.get(k))), "")
    profile = classify_android(manufacturer, model, product, fingerprint) if props else None
    if not chipset and profile and profile.get("protocol_profile") in {"qualcomm", "mediatek"}:
        chipset = "reported-family-only; exact SoC not confirmed"

    inventory = windows_usb_inventory()
    drivers = _driver_assessment(inventory, serial)
    family = profile.get("protocol_profile") if profile else "unknown"
    engine = {
        "samsung": {"name": "Samsung Download Mode", "status": "framework_only",
                    "requirements": ["Exact Samsung model/CSC firmware", "Samsung USB driver", "Validated Odin-compatible service workflow"]},
        "qualcomm": {"name": "Qualcomm EDL 9008", "status": "not_implemented",
                     "requirements": ["Exact Qualcomm SoC and board variant", "OEM-authorised signed programmer/firehose", "Matching signed firmware and authorised service procedure"]},
        "mediatek": {"name": "MediaTek Preloader / BootROM", "status": "not_implemented",
                     "requirements": ["Exact MediaTek SoC and board variant", "OEM-authorised Download Agent", "Matching scatter/package and authorised service procedure"]},
        "google": {"name": "Android ADB / Fastboot", "status": "partial_detection",
                   "requirements": ["Exact product/build confirmation", "Official matching factory image", "Model-specific validated procedure"]},
        "generic_android": {"name": "Android ADB / Fastboot", "status": "partial_detection",
                            "requirements": ["Exact manufacturer/model/board confirmation", "Official matching firmware", "Model-specific validated procedure"]},
    }.get(family, {"name": "Unknown service protocol", "status": "not_implemented",
                   "requirements": ["Identify exact manufacturer, model, board and service protocol before selecting an engine"]})

    firmware = {"provided": bool(firmware_path), "status": "not_provided",
                "compatible": False, "reason": "No firmware archive was supplied for preflight."}
    if firmware_path:
        archive = _read_archive_metadata(firmware_path)
        if not archive.get("ok"):
            firmware = {"provided": True, "status": "invalid_or_unreadable", "compatible": False,
                        "reason": archive.get("reason", "Firmware archive could not be inspected.")}
        else:
            metadata_text = "\n".join(x["text"] for x in archive["metadata"]).lower()
            identity_tokens = [x.lower() for x in (model, product) if x]
            matches = [token for token in identity_tokens if token in metadata_text]
            # Do not infer compatibility from filename, brand, or an empty manifest.
            confirmed = bool(identity_tokens) and bool(matches)
            firmware = {
                "provided": True, "status": "model_token_found_but_not_authenticated" if confirmed else "compatibility_unconfirmed",
                "compatible": False,
                "matched_identity_tokens": matches,
                "inspection": archive["inspection"],
                "reason": ("A device identity token appears in package metadata, but signature, region, hardware revision and build compatibility are not authenticated."
                           if confirmed else "Package metadata does not prove an exact model/product match. A matching filename or brand is insufficient.")
            }

    programmer = {"provided": bool(programmer_path), "status": "not_verified"}
    if programmer_path:
        p = Path(programmer_path).expanduser()
        if p.is_file() and p.stat().st_size <= 512 * 1024 * 1024:
            digest_obj = hashlib.sha256()
            with p.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest_obj.update(chunk)
            digest = digest_obj.hexdigest()
            programmer = {"provided": True, "status": "file_present_untrusted", "file": p.name,
                          "size_bytes": p.stat().st_size, "sha256": digest,
                          "note": "File presence and hash do not establish OEM authorisation, signature validity or chipset compatibility."}
        else:
            programmer = {"provided": True, "status": "missing_or_too_large"}

    ready = bool(serial and identity and engine["status"] not in {"not_implemented"} and
                 firmware.get("compatible") is True)
    blockers = []
    if not serial: blockers.append("No unique supported service-protocol device was selected or detected.")
    if not identity: blockers.append("Exact device identity could not be read through the current protocol.")
    if not chipset: blockers.append("Exact chipset is not confirmed.")
    if not firmware_path: blockers.append("No firmware package was supplied for compatibility preflight.")
    elif firmware.get("compatible") is not True: blockers.append("Firmware compatibility and authenticity are not verified.")
    if engine["status"] in {"framework_only", "not_implemented"}:
        blockers.append("The selected manufacturer flashing engine is not implemented and validated.")
    if family in {"qualcomm", "mediatek"} and programmer.get("status") != "file_present_untrusted":
        blockers.append("Required authorised chipset programmer/Download Agent is not supplied.")
    plan = {
        "ok": True, "read_only": True, "execution_enabled": False,
        "symptom": symptom, "serial": serial, "device_mode": mode,
        "device": {"manufacturer": manufacturer or "Unknown", "model": model or "Unknown",
                   "product_or_board": product or "Unknown", "chipset": chipset or "Unknown",
                   "build_fingerprint": fingerprint or "Unknown", "protocol_family": family},
        "protocol_engine": engine, "driver_check": drivers,
        "firmware_check": firmware, "programmer_check": programmer,
        "repair_ready": ready, "blockers": blockers,
        "recommended_pipeline": [
            "Detect the connected service interface and capture its status.",
            "Read exact model, product/board, chipset and software build where the protocol permits.",
            "Check Windows driver status and identify missing vendor components.",
            "Inspect firmware archive integrity and metadata; require exact model/board/region and trusted OEM provenance.",
            "Verify any required programmer/Download Agent against the OEM-authorised package and exact chipset.",
            "Select only a manufacturer-specific engine that has passed physical-device validation.",
            "Show a complete operation preview and require fresh owner approval before any device-changing command.",
            "Run post-operation verification and save a service report."
        ],
        "limitations": [
            "This is automated repair preparation only. It does not flash, erase, unlock, reset or write to the device.",
            "A file hash proves file identity, not OEM signature or authenticity.",
            "Qualcomm EDL and MediaTek Preloader require exact authorised programmer files; a file being present does not make it safe.",
            "Samsung Download Mode, Qualcomm EDL and MediaTek Preloader flashing engines remain unavailable until separately implemented and tested."
        ]
    }
    audit("automatic_repair_preflight", {"serial": serial, "mode": mode, "family": family,
          "firmware_provided": bool(firmware_path), "execution_enabled": False})
    return plan
