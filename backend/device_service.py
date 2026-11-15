from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess, zipfile, secrets, threading, time, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_PATH = Path(os.environ.get("VENDORA_AUDIT_PATH", Path.home() / ".vendora_mobile_toolkit" / "audit.jsonl"))
SAFE_REBOOT_TARGETS = {"system", "recovery", "bootloader"}
MANUFACTURER_PROTOCOLS = {
    "samsung": {"families": ["Download Mode / Odin-compatible workflows"], "tooling": ["Samsung USB driver", "Odin-compatible service workflow"], "status": "framework_only"},
    "google": {"families": ["ADB", "Fastboot"], "tooling": ["Android Platform Tools"], "status": "partial_detection"},
    "qualcomm": {"families": ["EDL (9008)"], "tooling": ["Exact chipset/firehose programmer", "signed vendor package"], "status": "not_implemented"},
    "mediatek": {"families": ["Preloader / BootROM"], "tooling": ["Exact chipset scatter/package", "vendor-authorized DA"], "status": "not_implemented"},
    "apple": {"families": ["Recovery", "DFU"], "tooling": ["Apple Devices / iTunes components", "pymobiledevice3 (optional)"], "status": "discovery_experimental"},
    "generic_android": {"families": ["ADB", "Fastboot"], "tooling": ["Android Platform Tools"], "status": "partial_detection"},
}

def _run(command: list[str], timeout: int = 12) -> dict[str, Any]:
    try:
        p = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        return {"ok": p.returncode == 0, "returncode": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}
    except FileNotFoundError:
        return {"ok": False, "error": f"{command[0]} was not found on PATH"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"{command[0]} timed out after {timeout} seconds"}
    except OSError as error:
        return {"ok": False, "error": f"Could not start {command[0]}: {error}"}

def audit(action: str, details: dict[str, Any]) -> None:
    """Append a durable audit record without allowing disk errors to crash a device operation."""
    record = (json.dumps({
        "at": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "details": details
    }, separators=(",", ":")) + "\n").encode("utf-8")
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_PATH.open("ab") as stream:
            stream.write(record)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        # A full disk, removed drive or sudden storage failure must not crash the UI/API.
        # The operation result remains available; the audit failure is intentionally non-fatal.
        return

def _tool_path(name: str) -> str:
    """Prefer platform-tools shipped with the installer; fall back to the user's PATH."""
    bundled_dir = os.environ.get("VENDORA_PLATFORM_TOOLS", "").strip()
    if bundled_dir:
        candidate = Path(bundled_dir) / (f"{name}.exe" if os.name == "nt" else name)
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name) or name


def tool_status() -> dict[str, bool]:
    return {name: Path(_tool_path(name)).is_file() if Path(_tool_path(name)).is_absolute() else shutil.which(name) is not None
            for name in ("adb", "fastboot")}

def _parse_adb_devices(output: str) -> list[dict[str, str]]:
    devices = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] in {"device", "unauthorized", "offline", "recovery", "sideload"}:
            devices.append({"serial": parts[0], "state": parts[1]})
    return devices

def _parse_fastboot_devices(output: str) -> list[dict[str, str]]:
    devices = []
    for line in output.splitlines():
        if "\t" in line:
            serial, state = line.split("\t", 1)
            if serial.strip(): devices.append({"serial": serial.strip(), "state": state.strip() or "fastboot"})
    return devices

def discover_android() -> dict[str, Any]:
    adb, fastboot = _run([_tool_path("adb"), "devices"]), _run([_tool_path("fastboot"), "devices"])
    return {"adb_available": tool_status()["adb"], "fastboot_available": tool_status()["fastboot"],
        "adb": _parse_adb_devices(adb.get("stdout", "")) if adb["ok"] else [],
        "fastboot": _parse_fastboot_devices(fastboot.get("stdout", "")) if fastboot["ok"] else [],
        "warnings": [message for result in (adb, fastboot) if not result["ok"]
            for message in (result.get("error") or result.get("stderr") or "Command failed without diagnostic output",)]}

def _valid_serial(serial: str) -> bool:
    return bool(serial and len(serial) <= 128 and re.fullmatch(r"[A-Za-z0-9._:-]+", serial))

def android_properties(serial: str) -> dict[str, Any]:
    if not _valid_serial(serial): raise ValueError("Invalid device serial")
    result = _run([_tool_path("adb"), "-s", serial, "shell", "getprop"])
    if not result["ok"]: return result
    props = {}
    for line in result["stdout"].splitlines():
        m = re.match(r"\[([^]]+)\]: \[(.*)\]", line)
        if m: props[m.group(1)] = m.group(2)
    keys = ("ro.product.manufacturer", "ro.product.model", "ro.product.device", "ro.build.version.release",
        "ro.build.version.sdk", "ro.build.fingerprint", "ro.boot.verifiedbootstate", "ro.boot.flash.locked",
        "ro.board.platform", "ro.hardware", "ro.boot.hardware", "ro.soc.model")
    return {"ok": True, "serial": serial, "properties": {k: props.get(k, "") for k in keys}}

def classify_android(manufacturer: str = "", model: str = "", device: str = "", fingerprint: str = "") -> dict[str, Any]:
    text = " ".join((manufacturer, model, device, fingerprint)).lower()
    if "samsung" in text or re.search(r"\b(sm-[a-z0-9]+|samsung)\b", text): key, label = "samsung", "Samsung"
    elif "google" in text or "pixel" in text: key, label = "google", "Google Pixel"
    elif any(x in text for x in ("qualcomm", "qcom", "snapdragon")): key, label = "qualcomm", "Qualcomm-based Android (unconfirmed manufacturer)"
    elif any(x in text for x in ("mediatek", "mtk", "mt67", "mt68", "dimensity", "helio")): key, label = "mediatek", "MediaTek-based Android (unconfirmed manufacturer)"
    elif any(x in text for x in ("xiaomi", "redmi", "poco")): key, label = "generic_android", "Xiaomi / Redmi / POCO"
    else: key, label = "generic_android", manufacturer.strip() or "Unknown Android manufacturer"
    return {"manufacturer_family": label, "protocol_profile": key, "protocols": MANUFACTURER_PROTOCOLS[key],
        "identification_confidence": "reported_properties" if text else "unknown"}

def _parse_battery_diagnostics(output: str) -> dict[str, Any]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        match = re.match(r"\s*([A-Za-z ]+):\s*(-?\d+)\s*$", line)
        if match:
            values[match.group(1).strip().lower().replace(" ", "_")] = match.group(2)
    status_names = {1: "unknown", 2: "charging", 3: "discharging", 4: "not_charging", 5: "full"}
    health_names = {1: "unknown", 2: "good", 3: "overheat", 4: "dead", 5: "over_voltage", 6: "unspecified_failure", 7: "cold"}
    parsed: dict[str, Any] = {}
    for source, target in (("level", "level_percent"), ("status", "status_code"), ("health", "health_code"), ("temperature", "temperature_tenths_c"), ("voltage", "voltage_mv"), ("plugged", "plugged_code")):
        if source in values:
            parsed[target] = int(values[source])
    if "status_code" in parsed:
        parsed["status"] = status_names.get(parsed["status_code"], "unrecognised")
    if "health_code" in parsed:
        parsed["health"] = health_names.get(parsed["health_code"], "unrecognised")
    if "temperature_tenths_c" in parsed:
        parsed["temperature_c"] = round(parsed["temperature_tenths_c"] / 10, 1)
    return parsed


def _parse_data_storage(output: str) -> dict[str, str]:
    lines = [line.split() for line in output.splitlines() if line.strip()]
    for parts in reversed(lines):
        if len(parts) >= 6 and parts[-1] == "/data":
            return {"filesystem": parts[0], "size": parts[1], "used": parts[2], "available": parts[3], "use_percent": parts[4], "mount": parts[5]}
    return {}


def backup_accessible_media(serial: str, destination: str) -> dict[str, Any]:
    """Copy user-accessible shared media from an authorised Android device.
    This is a logical media export, not deleted-file recovery or a full device image.
    Only common shared-storage folders are copied.
    """
    if not _valid_serial(serial):
        raise ValueError("A valid device serial is required.")
    if not destination or len(destination) > 2048:
        raise ValueError("Choose a valid destination folder on this computer.")
    target = Path(destination).expanduser().resolve()
    if target == Path(target.anchor):
        raise ValueError("The drive root cannot be used as the backup destination.")
    state = _run([_tool_path("adb"), "-s", serial, "get-state"])
    if not state["ok"] or state.get("stdout", "").strip() != "device":
        raise ValueError("The selected device is not authorised and online in ADB. Unlock it and approve this computer.")
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ValueError(f"Cannot create backup destination: {error}") from error
    if not target.is_dir():
        raise ValueError("The backup destination must be a folder.")
    folders = ("DCIM", "Pictures", "Movies", "Music", "Download")
    copied, skipped, failures = [], [], []
    for folder in folders:
        remote = "/sdcard/" + folder
        exists = _run([_tool_path("adb"), "-s", serial, "shell", "test", "-d", remote], timeout=15)
        if not exists["ok"]:
            skipped.append(folder)
            continue
        local = target / folder
        result = _run([_tool_path("adb"), "-s", serial, "pull", remote, str(local)], timeout=300)
        if result["ok"]:
            copied.append({"folder": folder, "destination": str(local), "output": result.get("stdout", "")})
        else:
            failures.append({"folder": folder, "error": result.get("stderr") or result.get("error") or "ADB pull failed"})
    audit("accessible_media_export", {"serial": serial, "destination": str(target),
          "copied_folders": [x["folder"] for x in copied], "skipped_folders": skipped,
          "failed_folders": [x["folder"] for x in failures]})
    return {"ok": bool(copied) and not failures, "operation": "accessible_shared_media_export",
            "serial": serial, "destination": str(target), "copied": copied,
            "skipped": skipped, "failures": failures,
            "limitations": ["Copies only accessible shared-storage folders; it is not a full-device backup.",
                "Does not recover deleted files, private app data, messages or protected content.",
                "Keep the phone unlocked and do not disconnect it until the export finishes."]}

def restore_accessible_media(serial: str, source_folder: str) -> dict[str, Any]:
    """Restore selected common media folders from a local backup into a new phone folder."""
    if not _valid_serial(serial):
        raise ValueError("A valid Android device serial is required.")
    if not source_folder or len(source_folder) > 2048:
        raise ValueError("Choose a valid backup folder on this computer.")
    source = Path(source_folder).expanduser().resolve()
    if not source.is_dir() or source == Path(source.anchor):
        raise ValueError("Choose an existing backup folder, not a drive root.")
    folders = ("DCIM", "Pictures", "Movies", "Music", "Download")
    available = [name for name in folders if (source / name).is_dir()]
    if not available:
        raise ValueError("The selected folder contains no supported Vendora media folders.")
    adb = _tool_path("adb")
    state = _run([adb, "-s", serial, "get-state"])
    if not state["ok"] or state.get("stdout", "").strip() != "device":
        raise ValueError("The selected phone is not authorised and online in ADB. Unlock it and approve this computer.")
    restore_root = "/sdcard/Vendora_Restore_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    restored, failures = [], []
    made = _run([adb, "-s", serial, "shell", "mkdir", "-p", restore_root], timeout=15)
    if not made["ok"]:
        raise ValueError("Could not create a new restore folder on the phone.")
    for folder in available:
        result = _run([adb, "-s", serial, "push", str(source / folder), restore_root + "/" + folder], timeout=600)
        if result["ok"]:
            restored.append({"folder": folder, "destination": restore_root + "/" + folder})
        else:
            failures.append({"folder": folder, "error": result.get("stderr") or result.get("error") or "ADB push failed"})
    audit("accessible_media_restore", {"serial": serial, "source": str(source), "destination": restore_root,
          "restored_folders": restored, "failed_folders": failures})
    return {"ok": bool(restored) and not failures, "operation": "accessible_shared_media_restore",
            "serial": serial, "source": str(source), "destination_folder": restore_root,
            "restored": restored, "failures": failures,
            "limitations": ["Restores only DCIM, Pictures, Movies, Music and Download folders found in the selected backup.",
                "Files are placed in a new Vendora_Restore folder; existing phone folders are not overwritten.",
                "This does not restore apps, messages, WhatsApp chats, accounts, settings or private app data."]}


def transfer_shared_media(source_serial: str, destination_serial: str) -> dict[str, Any]:
    """Copy accessible shared media between two authorised ADB Android devices via this PC."""
    if not _valid_serial(source_serial) or not _valid_serial(destination_serial):
        raise ValueError("Select two valid Android device serials.")
    if source_serial == destination_serial:
        raise ValueError("Choose two different phones for transfer.")
    adb = _tool_path("adb")
    for serial, role in ((source_serial, "source"), (destination_serial, "destination")):
        state = _run([adb, "-s", serial, "get-state"])
        if not state["ok"] or state.get("stdout", "").strip() != "device":
            raise ValueError(f"The {role} phone is not authorised and online in ADB. Unlock it and approve this computer.")
    folders = ("DCIM", "Pictures", "Movies", "Music", "Download")
    transferred, skipped, failures = [], [], []
    transfer_root = "/sdcard/Vendora_Transfer_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        with tempfile.TemporaryDirectory(prefix="vendora-transfer-") as staging:
            for folder in folders:
                remote_source = "/sdcard/" + folder
                exists = _run([adb, "-s", source_serial, "shell", "test", "-d", remote_source], timeout=15)
                if not exists["ok"]:
                    skipped.append(folder)
                    continue
                local = Path(staging) / folder
                pulled = _run([adb, "-s", source_serial, "pull", remote_source, str(local)], timeout=600)
                if not pulled["ok"]:
                    failures.append({"folder": folder, "stage": "read_source", "error": pulled.get("stderr") or pulled.get("error") or "ADB pull failed"})
                    continue
                remote_target = transfer_root + "/" + folder
                made = _run([adb, "-s", destination_serial, "shell", "mkdir", "-p", remote_target], timeout=15)
                if not made["ok"]:
                    failures.append({"folder": folder, "stage": "prepare_destination", "error": made.get("stderr") or made.get("error") or "Could not create destination folder"})
                    continue
                pushed = _run([adb, "-s", destination_serial, "push", str(local), remote_target], timeout=600)
                if pushed["ok"]:
                    transferred.append({"folder": folder, "destination": remote_target})
                else:
                    failures.append({"folder": folder, "stage": "write_destination", "error": pushed.get("stderr") or pushed.get("error") or "ADB push failed"})
    except OSError as error:
        raise ValueError(f"Could not create temporary transfer workspace: {error}") from error
    audit("shared_media_phone_transfer", {"source_serial": source_serial, "destination_serial": destination_serial,
          "destination": transfer_root, "transferred_folders": [x["folder"] for x in transferred],
          "skipped_folders": skipped, "failed_folders": [x["folder"] for x in failures]})
    return {"ok": bool(transferred) and not failures, "operation": "shared_media_phone_to_phone_transfer",
            "source_serial": source_serial, "destination_serial": destination_serial,
            "destination_folder": transfer_root, "transferred": transferred, "skipped": skipped, "failures": failures,
            "limitations": ["Transfers accessible shared-storage folders only; it does not migrate app-private data, WhatsApp databases, messages, settings or accounts.",
                "Both phones must remain connected, unlocked and authorised in ADB.",
                "Files are copied into a new Vendora_Transfer folder on the destination phone; existing folders and files are not overwritten."]}


def android_diagnostics(serial: str) -> dict[str, Any]:
    if not _valid_serial(serial): raise ValueError("Invalid device serial")
    commands = {"battery": [_tool_path("adb"), "-s", serial, "shell", "dumpsys", "battery"],
        "storage": [_tool_path("adb"), "-s", serial, "shell", "df", "-h", "/data"], "uptime": [_tool_path("adb"), "-s", serial, "shell", "uptime"]}
    results = {name: _run(cmd) for name, cmd in commands.items()}
    summary: dict[str, Any] = {}
    if results["battery"]["ok"]:
        summary["battery"] = _parse_battery_diagnostics(results["battery"].get("stdout", ""))
    if results["storage"]["ok"]:
        summary["data_storage"] = _parse_data_storage(results["storage"].get("stdout", ""))
    if results["uptime"]["ok"]:
        summary["uptime"] = results["uptime"].get("stdout", "")
    audit("android_diagnostics", {"serial": serial})
    return {"serial": serial, "summary": summary, "checks": results}

def reboot_android(serial: str, target: str, approval_token: str = "") -> dict[str, Any]:
    """Device-changing reboot; a backend-issued, one-time approval is mandatory."""
    return execute_approved_reboot(serial, target, approval_token)

def inspect_firmware_zip(path: str) -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.is_file() or p.suffix.lower() != ".zip": raise ValueError("Select an existing .zip firmware/archive file")
    if p.stat().st_size > 8 * 1024**3: raise ValueError("Archive exceeds the 8 GB inspection limit")
    digest = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""): digest.update(chunk)
    try:
        with zipfile.ZipFile(p) as z:
            bad, names = z.testzip(), z.namelist()
            manifests = [n for n in names if Path(n).name.lower() in {"android-info.txt", "metadata", "manifest.xml", "payload_properties.txt", "scatter.txt", "flash-all.bat"}]
            return {"ok": bad is None, "file": p.name, "size_bytes": p.stat().st_size, "sha256": digest.hexdigest(),
                "entries": len(names), "integrity_error": bad, "possible_manifests": manifests[:30],
                "note": "Archive inspection only; compatibility and authenticity are not verified."}
    except zipfile.BadZipFile: raise ValueError("The selected file is not a valid ZIP archive")

def iphone_status() -> dict[str, Any]:
    """Discover iOS devices through the optional pymobiledevice3 CLI without pairing."""
    executable = shutil.which("pymobiledevice3")
    if not executable:
        return {
            "supported_library_installed": False,
            "devices": [],
            "count": 0,
            "message": "pymobiledevice3 CLI not found. Install it and the Apple Mobile Device support service to enable iPhone discovery.",
        }
    result = _run([executable, "usbmux", "list"], timeout=20)
    if not result["ok"]:
        return {
            "supported_library_installed": True,
            "devices": [],
            "count": 0,
            "message": result.get("stderr") or result.get("error") or "iPhone discovery failed. Check Apple Mobile Device Service and USB connection.",
        }
    try:
        raw_devices = json.loads(result.get("stdout") or "[]")
        if not isinstance(raw_devices, list):
            raise ValueError("Unexpected device-list format")
        devices = []
        for item in raw_devices:
            if not isinstance(item, dict):
                continue
            devices.append({
                "udid": str(item.get("Identifier") or item.get("UniqueDeviceID") or ""),
                "name": str(item.get("DeviceName") or "Apple device"),
                "device_class": str(item.get("DeviceClass") or ""),
                "model": str(item.get("ProductType") or ""),
                "ios_version": str(item.get("ProductVersion") or ""),
                "connection": str(item.get("ConnectionType") or ""),
            })
        return {
            "supported_library_installed": True,
            "devices": devices,
            "count": len(devices),
            "message": "Device discovery completed. No pairing or device changes were requested.",
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "supported_library_installed": True,
            "devices": [],
            "count": 0,
            "message": "pymobiledevice3 returned an unexpected device-list format.",
        }
def recovery_guidance(platform: str) -> list[str]:
    if platform == "android": return ["Confirm the owner can unlock the device and has backed up important data.", "Record the exact manufacturer, model number, region and build before choosing firmware.", "Try the manufacturer's documented restart and recovery procedure first.", "Use only signed firmware intended for the exact model and region.", "If Factory Reset Protection appears, recover the previously synced Google account; do not bypass it."]
    if platform == "ios": return ["Confirm ownership and check that a current backup exists.", "Use Apple's official recovery-mode update/restore instructions for the exact device.", "A restore can erase data; explain this before proceeding.", "Activation Lock requires the linked Apple Account or Apple's ownership-support process."]
    raise ValueError("Unknown platform")


def unlock_workflow_guidance(workflow: str) -> dict[str, Any]:
    """Return safe, official owner-recovery steps; never claims to unlock a device."""
    workflows = {
        "frp_recovery": {
            "title": "Android Factory Reset Protection (FRP) owner recovery",
            "status": "OWNER_VERIFICATION_AND_OFFICIAL_ACCOUNT_RECOVERY",
            "steps": [
                "Confirm the customer is the device owner or has documented authority to service it. Record the service case and the exact make/model; do not collect or store Google passwords or one-time codes.",
                "Explain that FRP is an anti-theft protection that can appear after a protected Android device is reset. It is not the same as a SIM/network lock or screen lock.",
                "Ask the owner to complete setup using a Google Account that was previously added and synced on this device, following the on-screen prompts.",
                "If the owner cannot sign in, help them use Google's official account-recovery process on a trusted device. If the password was recently changed, follow Google's on-screen security waiting period rather than repeatedly resetting the phone.",
                "If the owner cannot recover the account, refer them to the device manufacturer or an authorised service centre with the original proof of purchase and ownership documents.",
                "After the owner completes the official verification process, continue normal device setup. Record the service outcome without recording account credentials."
            ],
            "limitations": [
                "Vendora does not bypass, disable, exploit or remove FRP, Google account verification or any anti-theft protection.",
                "This release provides an owner-verification checklist and official recovery guidance only; no manufacturer FRP-removal integration is connected.",
                "Never ask a customer to disclose their Google password, recovery codes or one-time verification codes to the technician."
            ]
        },
        "screen_lock": {
            "title": "Forgotten Android screen-lock recovery",
            "status": "OFFICIAL_RECOVERY_GUIDANCE",
            "steps": [
                "Confirm the person requesting help is the device owner or is authorised by the owner. Record the exact model and Android version.",
                "Try the device manufacturer's documented account/device-recovery options first. Availability differs by model and Android version.",
                "If the device offers an official on-device recovery route, follow the manufacturer's instructions. Do not use third-party lock-removal utilities.",
                "If recovery is not possible, explain that an official factory reset may erase local data. Confirm backups and ownership before the owner chooses any reset.",
                "After a reset, the device may require the Google Account previously synced to it. The owner must recover that account through Google's official account-recovery process.",
                "If the owner cannot prove account ownership or activation eligibility, stop and refer them to the manufacturer or authorised service provider."
            ],
            "limitations": [
                "Vendora does not remove PINs, patterns, passwords or biometrics, and does not bypass FRP or other anti-theft protections.",
                "A reset is not a data-recovery method and can permanently erase data that is not backed up."
            ]
        },
        "carrier_unlock": {
            "title": "SIM / network carrier unlock",
            "status": "CARRIER_AUTHORISED_PROCESS",
            "steps": [
                "Identify the original selling/network carrier, country, exact phone model and whether the device is paid off or under contract.",
                "Ask the original carrier to check the device's network-lock status and eligibility. Only the carrier or its authorised unlock provider can confirm eligibility against its records.",
                "Resolve any outstanding contract, instalment, blacklist, lost/stolen or account requirements directly with the carrier.",
                "Submit the carrier's official unlock request. Keep its case/reference number and follow its instructions; some carriers process the unlock remotely and others provide a code.",
                "When the carrier confirms completion, insert a SIM from another supported network and follow the carrier's activation instructions.",
                "If the phone remains locked, return to the original carrier with the case number. Do not use unofficial code generators or IMEI alteration services."
            ],
            "limitations": [
                "Vendora cannot query carrier eligibility or generate a network unlock code without an authorised carrier integration.",
                "Do not share an IMEI, account password or identity document with unofficial services. Provide sensitive details only through the carrier's verified channel."
            ]
        },
        "bootloader_unlock": {
            "title": "Manufacturer-supported bootloader unlocking",
            "status": "OEM_COMPATIBILITY_CHECK_REQUIRED",
            "steps": [
                "Identify the exact manufacturer, model/variant, region and current software build. Bootloader unlock support varies by model, carrier and region.",
                "Check the manufacturer's official developer documentation and eligibility page for that exact model. Some models cannot be officially unlocked.",
                "Explain that unlocking commonly triggers a complete factory data wipe and may affect warranty, security features, DRM or payment applications.",
                "Back up owner data and confirm the owner understands the consequences before proceeding.",
                "Follow only the exact manufacturer's documented unlock process. Complete any OEM account, waiting-period or unlock-token requirements through the official portal.",
                "If the OEM procedure requires on-device confirmation, the owner must review and confirm that prompt on the phone. Stop if the model or instructions do not match."
            ],
            "limitations": [
                "Vendora does not force-unlock bootloaders, bypass OEM eligibility, defeat FRP or execute a generic fastboot unlock command across manufacturers.",
                "This release provides the guided OEM workflow only; automated manufacturer-specific unlock engines are not implemented."
            ]
        }
    }
    if workflow not in workflows:
        raise ValueError("Unknown recovery workflow")
    if workflow == "frp_recovery":
        audit("frp_owner_recovery_guidance_opened", {"workflow": workflow, "credentials_collected": False})
    return workflows[workflow]

def classify_usb_interface(instance_id: str = "", friendly_name: str = "", device_class: str = "") -> dict[str, Any]:
    """Conservatively classify a Windows USB interface from its reported PnP identity.

    USB IDs identify an interface/vendor, not a handset model. Only Qualcomm's
    well-known 05C6:9008 ID is labelled EDL; MediaTek and Samsung are reported
    as possible vendor interfaces unless the Windows name states the mode.
    """
    raw = " ".join((instance_id, friendly_name, device_class))
    upper = raw.upper()
    match = re.search(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", upper)
    vid, pid = (match.group(1), match.group(2)) if match else ("", "")
    base = {
        "vendor_id": vid or None, "product_id": pid or None,
        "protocol_family": "unknown", "mode": "unknown_usb_mode",
        "confidence": "low", "brand_hint": None,
        "model_identified": False,
    }
    if vid == "05C6" and pid == "9008":
        return {**base, "protocol_family": "qualcomm_edl", "mode": "edl_9008",
                "confidence": "high", "brand_hint": "Qualcomm chipset (phone brand unknown)"}
    if vid == "0E8D":
        named_preloader = any(x in upper for x in ("PRELOADER", "VCOM", "BOOTROM", "BROM"))
        return {**base, "protocol_family": "mediatek_usb",
                "mode": "possible_preloader_or_bootrom" if named_preloader else "mediatek_usb_interface",
                "confidence": "medium" if named_preloader else "low",
                "brand_hint": "MediaTek interface (phone brand and model unknown)"}
    if vid == "04E8":
        named_download = "DOWNLOAD MODE" in upper or "ODIN" in upper
        return {**base, "protocol_family": "samsung_usb",
                "mode": "download_mode_candidate" if named_download else "samsung_usb_interface",
                "confidence": "medium" if named_download else "low",
                "brand_hint": "Samsung USB interface (exact mode/model unconfirmed)"}
    if any(x in upper for x in ("ANDROID BOOTLOADER", "FASTBOOT")):
        return {**base, "protocol_family": "android_fastboot", "mode": "fastboot_candidate",
                "confidence": "medium", "brand_hint": "Android device (brand/model unknown)"}
    if any(x in upper for x in ("ANDROID ADB", "ANDROID COMPOSITE")):
        return {**base, "protocol_family": "android_usb", "mode": "android_usb_interface",
                "confidence": "low", "brand_hint": "Android USB interface (ADB authorisation not confirmed)"}
    return base


def windows_usb_inventory() -> dict[str, Any]:
    if os.name != "nt": return {"supported": False, "devices": [], "message": "Windows USB inventory is available only on Windows."}
    # Include USB interfaces (including transient preloader/EDL nodes) and WPD/MTP nodes.
    # Inventory only: this never installs drivers or changes device state.
    script = "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '^(USB|USBSTOR)\\\\' -or $_.InstanceId -like 'SWD\\\\WPDBUSENUM*' } | Select-Object Status,Class,FriendlyName,InstanceId | ConvertTo-Json -Compress"
    result = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=20)
    if not result["ok"]: return {"supported": True, "devices": [], "message": result.get("stderr") or result.get("error") or "Unable to query Windows devices."}
    try:
        data = json.loads(result["stdout"] or "[]")
        if isinstance(data, dict): data = [data]
        devices = []
        for item in data:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["detection"] = classify_usb_interface(
                str(row.get("InstanceId") or ""),
                str(row.get("FriendlyName") or row.get("Name") or ""),
                str(row.get("Class") or ""),
            )
            devices.append(row)
        detected = [x for x in devices if x["detection"]["protocol_family"] != "unknown"]
        audit("usb_inventory_scanned", {"device_count": len(devices), "protocol_candidates": len(detected)})
        return {"supported": True, "devices": devices, "count": len(devices),
                "protocol_candidates": detected,
                "message": "USB interfaces classified conservatively. A USB match does not identify the exact handset model or prove a usable service session."}
    except json.JSONDecodeError: return {"supported": True, "devices": [], "message": "Windows returned an unreadable device inventory."}

def readiness_report() -> dict[str, Any]:
    # Report the exact executable actually used by discovery, including installer-bundled tools.
    adb_path, fastboot_path = _tool_path("adb"), _tool_path("fastboot")
    names = ("python", "powershell")
    tools = {
        "adb": {"available": tool_status()["adb"], "path": adb_path if tool_status()["adb"] else None, "source": "bundled_or_path"},
        "fastboot": {"available": tool_status()["fastboot"], "path": fastboot_path if tool_status()["fastboot"] else None, "source": "bundled_or_path"},
    }
    tools.update({n: {"available": bool(shutil.which(n)), "path": shutil.which(n)} for n in names})
    return {"tools": tools,
        "platform": os.name, "manufacturer_profiles": MANUFACTURER_PROTOCOLS,
        "iphone_library_installed": iphone_status()["supported_library_installed"],
        "operation_approval": {"backend_enforced": True, "single_use": True, "expires_in_seconds": _APPROVAL_TTL_SECONDS,
            "supported_operations": ["android_reboot", "factory_recovery_preparation"]},
        "firmware_flashing": {"available": False, "status": "not_implemented", "execution_endpoint": "disabled"},
        "limitations": ["Protocol profiles are readiness records, not implemented flashing or repair engines.",
        "Firmware flashing engines are not implemented; ZIP inspection is not a flash operation.", "Factory reset support is guided recovery preparation only; Vendora does not issue wipe commands.", "No screen-lock, FRP, Activation Lock, or account bypass is provided.",
        "USB presence alone does not mean ADB authorisation is complete; enable USB debugging and approve this computer on the phone.",
        "Physical-device validation is required before claiming model compatibility."]}


def prepare_factory_reset(serial: str, backup_confirmed: bool, confirmation: str,
                          approval_token: str = "") -> dict[str, Any]:
    """Requires a one-time backend approval; enters recovery but never wipes data."""
    expected = _approval_payload(serial, "factory_reset_prepare",
                                 backup_confirmed=backup_confirmed, confirmation=confirmation)
    identity = android_properties(serial)
    if not identity.get("ok"):
        raise ValueError(identity.get("error") or "Unable to verify the selected Android device.")
    _consume_approval(approval_token, expected)
    audit("operation_started", expected)
    result = _perform_reboot_android(serial, "recovery")
    audit("factory_reset_recovery_preparation", {
        "serial": serial, "backup_confirmed": True, "reboot_ok": result.get("ok", False)
    })
    audit("operation_completed" if result.get("ok") else "operation_failed", expected)
    return {
        "ok": bool(result.get("ok")),
        "stage": "recovery_preparation",
        "result": result,
        "message": "The phone was asked to reboot into recovery. Vendora did NOT erase data. Review the recovery screen on the phone; only choose Wipe data/factory reset there if the owner has explicitly authorised erasure."
    }

# Short-lived, single-use approvals are held only in this local backend process.
_APPROVAL_TTL_SECONDS = 120
_APPROVAL_LOCK = threading.Lock()
_PENDING_CHALLENGES: dict[str, dict[str, Any]] = {}
_APPROVED_TOKENS: dict[str, dict[str, Any]] = {}

def _approval_payload(serial: str, operation: str, target: str = "",
                      backup_confirmed: bool = False, confirmation: str = "") -> dict[str, Any]:
    if not _valid_serial(serial):
        raise ValueError("Invalid device serial")
    if operation == "reboot":
        if target not in SAFE_REBOOT_TARGETS:
            raise ValueError("Unsupported reboot target")
        return {"serial": serial, "operation": operation, "target": target}
    if operation == "factory_reset_prepare":
        if backup_confirmed is not True or confirmation != "PREPARE RECOVERY":
            raise ValueError("Factory recovery preparation requires backup confirmation and the exact PREPARE RECOVERY phrase.")
        return {"serial": serial, "operation": operation, "target": "recovery",
                "backup_confirmed": True, "confirmation": confirmation}
    raise ValueError("This operation is not available for approval")

def create_operation_preview(serial: str, operation: str, target: str = "",
                             backup_confirmed: bool = False, confirmation: str = "") -> dict[str, Any]:
    payload = _approval_payload(serial, operation, target, backup_confirmed, confirmation)
    identity = android_properties(serial)
    if not identity.get("ok"):
        raise ValueError(identity.get("error") or "The selected device could not be verified.")
    challenge = secrets.token_urlsafe(24)
    now = time.monotonic()
    with _APPROVAL_LOCK:
        # Bound memory use if a user repeatedly opens and cancels approval dialogs.
        for key in [k for k, v in _PENDING_CHALLENGES.items() if v["expires"] < now]:
            _PENDING_CHALLENGES.pop(key, None)
        for key in [k for k, v in _APPROVED_TOKENS.items() if v["expires"] < now]:
            _APPROVED_TOKENS.pop(key, None)
        _PENDING_CHALLENGES[challenge] = {"payload": payload, "expires": now + _APPROVAL_TTL_SECONDS}
    audit("operation_approval_requested", {"serial": serial, "operation": operation, "target": payload["target"]})
    return {"ok": True, "challenge_id": challenge, "expires_in_seconds": _APPROVAL_TTL_SECONDS,
            "operation": payload, "device": identity.get("properties", {})}

def approve_operation(challenge_id: str) -> dict[str, Any]:
    if not challenge_id or len(challenge_id) > 128:
        raise ValueError("Invalid approval challenge")
    with _APPROVAL_LOCK:
        challenge = _PENDING_CHALLENGES.pop(challenge_id, None)
        if not challenge or challenge["expires"] < time.monotonic():
            audit("operation_approval_expired_or_invalid", {})
            raise ValueError("Approval request expired or is invalid. Prepare it again.")
        token = secrets.token_urlsafe(32)
        _APPROVED_TOKENS[token] = {"payload": challenge["payload"], "expires": time.monotonic() + _APPROVAL_TTL_SECONDS}
    audit("operation_approved", {"serial": challenge["payload"]["serial"],
          "operation": challenge["payload"]["operation"], "target": challenge["payload"]["target"]})
    return {"ok": True, "approval_token": token, "expires_in_seconds": _APPROVAL_TTL_SECONDS}

def _consume_approval(token: str, expected: dict[str, Any]) -> None:
    if not token or len(token) > 256:
        raise ValueError("A fresh approval for this exact operation is required.")
    with _APPROVAL_LOCK:
        record = _APPROVED_TOKENS.pop(token, None)
        if not record or record["expires"] < time.monotonic() or record["payload"] != expected:
            audit("operation_rejected_missing_expired_or_mismatched_approval",
                  {"serial": expected.get("serial"), "operation": expected.get("operation")})
            raise ValueError("Approval is missing, expired, already used, or does not match this device and operation. Prepare and approve again.")

def _perform_reboot_android(serial: str, target: str) -> dict[str, Any]:
    result = _run([_tool_path("adb"), "-s", serial, "reboot", target])
    audit("android_reboot", {"serial": serial, "target": target, "ok": result["ok"]})
    return result

def execute_approved_reboot(serial: str, target: str, approval_token: str) -> dict[str, Any]:
    expected = _approval_payload(serial, "reboot", target)
    identity = android_properties(serial)
    if not identity.get("ok"):
        raise ValueError(identity.get("error") or "The selected device is no longer available.")
    _consume_approval(approval_token, expected)
    audit("operation_started", expected)
    result = _perform_reboot_android(serial, target)
    audit("operation_completed" if result.get("ok") else "operation_failed",
          {**expected, "returncode": result.get("returncode")})
    return result


def assess_boot_repair(serial: str = "", symptom: str = "stuck_logo") -> dict[str, Any]:
    """Read-only boot-failure assessment. Never wipes, flashes, unlocks or reboots a phone."""
    allowed = {"stuck_logo", "boot_loop", "failed_update", "recovery_mode", "black_screen"}
    if symptom not in allowed:
        raise ValueError("Unsupported boot symptom")
    if serial and not _valid_serial(serial):
        raise ValueError("Invalid device serial")
    found = discover_android()
    adb_rows = found.get("adb", [])
    fastboot_rows = found.get("fastboot", [])
    selected_adb = next((x for x in adb_rows if x.get("serial") == serial), None) if serial else None
    selected_fastboot = next((x for x in fastboot_rows if x.get("serial") == serial), None) if serial else None
    report: dict[str, Any] = {
        "ok": True, "read_only": True, "symptom": symptom,
        "detected": {"adb": adb_rows, "fastboot": fastboot_rows},
        "device_mode": "not_detected",
        "identity": {}, "diagnostics": {}, "assessment": "", "next_steps": [],
        "limitations": [
            "This assessment does not repair, wipe, flash, unlock or reboot the phone.",
            "USB inventory alone is not proof that a bootloader, recovery or service protocol is usable.",
            "A firmware repair engine is not implemented; never flash a package based only on a matching brand."
        ]
    }
    if selected_adb and selected_adb.get("state") == "device":
        report["device_mode"] = "android_adb"
        identity = android_properties(serial)
        report["identity"] = identity.get("properties", {})
        report["identity_read_ok"] = bool(identity.get("ok"))
        if identity.get("ok"):
            profile = classify_android(
                report["identity"].get("ro.product.manufacturer", ""),
                report["identity"].get("ro.product.model", ""),
                report["identity"].get("ro.product.device", ""),
                report["identity"].get("ro.build.fingerprint", ""))
            report["protocol_profile"] = profile
            diag = android_diagnostics(serial)
            report["diagnostics"] = diag.get("summary", {})
        else:
            report["identity_error"] = identity.get("error") or identity.get("stderr")
    elif selected_adb:
        report["device_mode"] = "adb_" + selected_adb.get("state", "unknown")
    elif selected_fastboot:
        report["device_mode"] = "fastboot"
        for key in ("product", "version", "current-slot", "unlocked"):
            value = _run([_tool_path("fastboot"), "-s", serial, "getvar", key], timeout=8)
            report["identity"][key] = (value.get("stderr") or value.get("stdout") or "").strip()
    elif not serial and (adb_rows or fastboot_rows):
        report["device_mode"] = "multiple_devices_detected"
    report["assessment"] = {
        "stuck_logo": "A startup logo freeze is reported. If the phone is detected in ADB or Fastboot, Vendora can collect the read-only information above; otherwise use the exact model's official recovery instructions.",
        "boot_loop": "Repeated restarts can be caused by a failed update, storage fault, battery/power issue or firmware problem. The available connection mode determines which diagnostics are possible.",
        "failed_update": "An interrupted update may leave Android unable to boot. Do not flash a package until exact model, region, hardware revision and build compatibility are verified.",
        "recovery_mode": "The phone is already reported to be in recovery. Read the on-device menu carefully; do not select factory reset or wipe unless the owner explicitly accepts permanent data loss.",
        "black_screen": "A black screen may be display, power or boot failure. Check charging and physical condition first; USB detection alone cannot distinguish these causes."
    }[symptom]
    if report["device_mode"] == "android_adb":
        report["next_steps"] = [
            "Save the detected model, build fingerprint and diagnostic summary before attempting recovery.",
            "Check available storage and battery condition in the report; investigate obvious power or storage faults.",
            "Use only the manufacturer's documented, model-specific recovery procedure.",
            "Back up accessible data before any repair that may alter partitions."
        ]
    elif report["device_mode"] == "fastboot":
        report["next_steps"] = [
            "Record the reported product and bootloader variables and verify them against the exact model and regional variant.",
            "Do not issue unlock, erase, format or flash commands from this assessment.",
            "Use the manufacturer's official service or recovery instructions for the verified model."
        ]
    elif report["device_mode"].startswith("adb_"):
        report["next_steps"] = [
            "ADB is present but not authorised/ready. If Android is usable, unlock it and approve this computer; a logo-stuck phone may not be able to do this.",
            "Run a fresh scan in Recovery or Bootloader mode; do not assume an ADB session exists."
        ]
    else:
        report["next_steps"] = [
            "Try a fresh scan while the phone is in its own recovery or bootloader screen, using the manufacturer's documented button combination.",
            "If Windows lists only a generic USB device, install only the official driver for the exact manufacturer/model and scan again.",
            "Samsung Download Mode, Qualcomm EDL and MediaTek Preloader need separate validated detection and service engines; those engines are not active in this build."
        ]
    audit("boot_repair_assessment", {"serial": serial or None, "symptom": symptom,
          "device_mode": report["device_mode"], "read_only": True})
    return report
