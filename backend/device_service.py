from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess, zipfile
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
        "ro.build.version.sdk", "ro.build.fingerprint", "ro.boot.verifiedbootstate", "ro.boot.flash.locked")
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

def reboot_android(serial: str, target: str) -> dict[str, Any]:
    if target not in SAFE_REBOOT_TARGETS: raise ValueError("Unsupported reboot target")
    if not _valid_serial(serial): raise ValueError("Invalid device serial")
    result = _run([_tool_path("adb"), "-s", serial, "reboot", target])
    audit("android_reboot", {"serial": serial, "target": target, "ok": result["ok"]})
    return result

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

def windows_usb_inventory() -> dict[str, Any]:
    if os.name != "nt": return {"supported": False, "devices": [], "message": "Windows USB inventory is available only on Windows."}
    # Include composite USB interfaces and Windows portable-device (MTP/WPD) nodes.
    # Inventory only: this never installs drivers or changes device state.
    script = "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '^(USB|USBSTOR)\\\\' -or $_.InstanceId -like 'SWD\\\\WPDBUSENUM*' } | Select-Object Status,Class,FriendlyName,InstanceId | ConvertTo-Json -Compress"
    result = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=20)
    if not result["ok"]: return {"supported": True, "devices": [], "message": result.get("stderr") or result.get("error") or "Unable to query Windows devices."}
    try:
        data = json.loads(result["stdout"] or "[]")
        if isinstance(data, dict): data = [data]
        return {"supported": True, "devices": data, "count": len(data)}
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
        "limitations": ["Protocol profiles are readiness records, not implemented flashing or repair engines.",
        "Firmware flashing engines are not implemented; ZIP inspection is not a flash operation.", "Factory reset support is guided recovery preparation only; Vendora does not issue wipe commands.", "No screen-lock, FRP, Activation Lock, or account bypass is provided.",
        "USB presence alone does not mean ADB authorisation is complete; enable USB debugging and approve this computer on the phone.",
        "Physical-device validation is required before claiming model compatibility."]}


def prepare_factory_reset(serial: str, backup_confirmed: bool, confirmation: str) -> dict[str, Any]:
    """Safely prepare a user-confirmed reset by entering stock recovery; never issues wipe commands."""
    if not _valid_serial(serial):
        raise ValueError("Invalid device serial")
    if backup_confirmed is not True:
        raise ValueError("Confirm that important data is backed up before continuing.")
    if confirmation != "PREPARE RECOVERY":
        raise ValueError('Type PREPARE RECOVERY exactly to confirm this operation.')
    identity = android_properties(serial)
    if not identity.get("ok"):
        raise ValueError(identity.get("error") or "Unable to verify the selected Android device.")
    result = reboot_android(serial, "recovery")
    audit("factory_reset_recovery_preparation", {
        "serial": serial, "backup_confirmed": True, "reboot_ok": result.get("ok", False)
    })
    return {
        "ok": bool(result.get("ok")),
        "stage": "recovery_preparation",
        "result": result,
        "message": "The phone was asked to reboot into recovery. Vendora did NOT erase data. Review the recovery screen on the phone; only choose Wipe data/factory reset there if the owner has explicitly authorised erasure."
    }
