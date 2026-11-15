import sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import pytest
import device_service as ds

def test_reboot_rejects_unsafe_target():
    with pytest.raises(ValueError): ds.reboot_android("abc123", "wipe")

def test_reboot_rejects_invalid_serial():
    with pytest.raises(ValueError): ds.reboot_android("bad serial", "system")

def test_recovery_guidance_platforms():
    assert any("Factory Reset Protection" in s for s in ds.recovery_guidance("android"))
    assert any("Activation Lock" in s for s in ds.recovery_guidance("ios"))

def test_unknown_platform_rejected():
    with pytest.raises(ValueError): ds.recovery_guidance("windows")

def test_inspect_zip(tmp_path):
    z=tmp_path/"firmware.zip"
    with zipfile.ZipFile(z,"w") as f: f.writestr("android-info.txt","require board=test")
    result=ds.inspect_firmware_zip(str(z))
    assert result["ok"] is True
    assert "android-info.txt" in result["possible_manifests"]
    assert len(result["sha256"])==64

def test_invalid_zip_rejected(tmp_path):
    p=tmp_path/"bad.zip"; p.write_text("not a zip")
    with pytest.raises(ValueError): ds.inspect_firmware_zip(str(p))

def test_serial_parser():
    parsed=ds._parse_adb_devices("List of devices attached\nABC123 device\nXYZ unauthorized\n")
    assert parsed==[{"serial":"ABC123","state":"device"},{"serial":"XYZ","state":"unauthorized"}]

def test_fastboot_parser():
    assert ds._parse_fastboot_devices("ABC123\tfastboot\n")==[{"serial":"ABC123","state":"fastboot"}]


def test_manufacturer_classification_profiles():
    assert ds.classify_android("samsung", "SM-G998W")["protocol_profile"] == "samsung"
    assert ds.classify_android("Google", "Pixel 8")["protocol_profile"] == "google"
    assert ds.classify_android("", "", "", "vendor/mt6789")["protocol_profile"] == "mediatek"

def test_readiness_is_explicit_about_limitations():
    report = ds.readiness_report()
    assert "manufacturer_profiles" in report
    assert any("not implemented" in x.lower() for x in report["limitations"])

def test_usb_inventory_is_graceful_off_windows(monkeypatch):
    monkeypatch.setattr(ds.os, "name", "posix")
    result = ds.windows_usb_inventory()
    assert result["supported"] is False


def test_iphone_status_parses_discovered_devices(monkeypatch):
    monkeypatch.setattr(ds.shutil, "which", lambda name: "/tools/pymobiledevice3.exe")
    monkeypatch.setattr(ds, "_run", lambda command, timeout=12: {
        "ok": True,
        "stdout": '[{"Identifier":"00008030ABC","DeviceName":"Test iPhone","DeviceClass":"iPhone","ProductType":"iPhone15,2","ProductVersion":"17.5","ConnectionType":"USB"}]',
        "stderr": ""
    })
    result = ds.iphone_status()
    assert result["count"] == 1
    assert result["devices"][0]["name"] == "Test iPhone"
    assert result["devices"][0]["model"] == "iPhone15,2"


def test_iphone_status_reports_missing_cli(monkeypatch):
    monkeypatch.setattr(ds.shutil, "which", lambda name: None)
    result = ds.iphone_status()
    assert result["supported_library_installed"] is False
    assert result["devices"] == []


def test_iphone_status_handles_usbmux_failure(monkeypatch):
    monkeypatch.setattr(ds.shutil, "which", lambda name: "/tools/pymobiledevice3.exe")
    monkeypatch.setattr(ds, "_run", lambda command, timeout=12: {
        "ok": False, "stderr": "Apple Mobile Device Service unavailable"
    })
    result = ds.iphone_status()
    assert result["supported_library_installed"] is True
    assert result["count"] == 0
    assert "Apple Mobile Device Service" in result["message"]


def test_battery_diagnostics_parser():
    parsed = ds._parse_battery_diagnostics(
        "AC powered: false\nUSB powered: true\nstatus: 2\nhealth: 2\nlevel: 87\ntemperature: 315\nvoltage: 4100\n"
    )
    assert parsed["level_percent"] == 87
    assert parsed["status"] == "charging"
    assert parsed["health"] == "good"
    assert parsed["temperature_c"] == 31.5
    assert parsed["voltage_mv"] == 4100


def test_data_storage_parser():
    parsed = ds._parse_data_storage(
        "Filesystem      Size Used Avail Use% Mounted on\n/dev/block/dm-10  100G 60G 40G 60% /data\n"
    )
    assert parsed["size"] == "100G"
    assert parsed["available"] == "40G"
    assert parsed["use_percent"] == "60%"
    assert parsed["mount"] == "/data"


def test_android_diagnostics_returns_parsed_summary(monkeypatch):
    def fake_run(command, timeout=12):
        if "dumpsys" in command:
            return {"ok": True, "stdout": "level: 90\nstatus: 5\nhealth: 2\ntemperature: 300"}
        if "df" in command:
            return {"ok": True, "stdout": "Filesystem Size Used Avail Use% Mounted on\n/dev/block/dm-1 64G 20G 44G 32% /data"}
        return {"ok": True, "stdout": "up 2 days"}
    monkeypatch.setattr(ds, "_run", fake_run)
    monkeypatch.setattr(ds, "audit", lambda *args, **kwargs: None)
    result = ds.android_diagnostics("TEST123")
    assert result["summary"]["battery"]["level_percent"] == 90
    assert result["summary"]["data_storage"]["available"] == "44G"
    assert result["summary"]["uptime"] == "up 2 days"


def test_audit_disk_error_does_not_crash_operation(monkeypatch, tmp_path):
    bad_path = tmp_path / "missing" / "audit.jsonl"
    monkeypatch.setattr(ds, "AUDIT_PATH", bad_path)
    def fail_mkdir(*args, **kwargs):
        raise OSError("disk unavailable")
    monkeypatch.setattr(ds.Path, "mkdir", fail_mkdir)
    ds.audit("test", {"serial": "TEST123"})


def test_subprocess_os_error_is_reported(monkeypatch):
    def fail_run(*args, **kwargs):
        raise OSError("access denied")
    monkeypatch.setattr(ds.subprocess, "run", fail_run)
    result = ds._run(["fake-tool"])
    assert result["ok"] is False
    assert "access denied" in result["error"]

def test_bundled_platform_tools_are_preferred(monkeypatch, tmp_path):
    tools = tmp_path / "platform-tools"
    tools.mkdir()
    adb = tools / ("adb.exe" if ds.os.name == "nt" else "adb")
    adb.write_text("test executable placeholder")
    monkeypatch.setenv("VENDORA_PLATFORM_TOOLS", str(tools))
    monkeypatch.setattr(ds.shutil, "which", lambda name: "/system/"+name)
    assert ds._tool_path("adb") == str(adb)

def test_usb_inventory_queries_usb_and_mtp_nodes(monkeypatch):
    monkeypatch.setattr(ds.os, "name", "nt")
    captured = {}
    def fake_run(command, timeout=12):
        captured["command"] = command[-1]
        return {"ok": True, "stdout": "[]"}
    monkeypatch.setattr(ds, "_run", fake_run)
    result = ds.windows_usb_inventory()
    assert result["supported"] is True
    assert "USBSTOR" in captured["command"]
    assert "WPDBUSENUM" in captured["command"]

def test_discovery_reports_adb_command_failure(monkeypatch):
    def fake_run(command, timeout=12):
        if "adb" in command[0]:
            return {"ok": False, "returncode": 1, "stdout": "", "stderr": "daemon unavailable"}
        return {"ok": True, "stdout": "", "stderr": ""}
    monkeypatch.setattr(ds, "_run", fake_run)
    monkeypatch.setattr(ds, "tool_status", lambda: {"adb": True, "fastboot": True})
    result = ds.discover_android()
    assert any("daemon unavailable" in warning for warning in result["warnings"])


def test_reboot_requires_backend_issued_one_time_approval(monkeypatch):
    ds._PENDING_CHALLENGES.clear()
    ds._APPROVED_TOKENS.clear()
    monkeypatch.setattr(ds, "android_properties", lambda serial: {
        "ok": True, "properties": {"ro.product.model": "Test"}
    })
    monkeypatch.setattr(ds, "audit", lambda *args, **kwargs: None)
    called = []
    monkeypatch.setattr(ds, "_run", lambda command, timeout=12: (
        called.append(command) or {"ok": True, "returncode": 0, "stdout": "", "stderr": ""}
    ))
    with pytest.raises(ValueError, match="approval"):
        ds.reboot_android("TEST123", "recovery")
    preview = ds.create_operation_preview("TEST123", "reboot", "recovery")
    approved = ds.approve_operation(preview["challenge_id"])
    result = ds.reboot_android("TEST123", "recovery", approved["approval_token"])
    assert result["ok"] is True
    assert len(called) == 1
    with pytest.raises(ValueError, match="Approval"):
        ds.reboot_android("TEST123", "recovery", approved["approval_token"])
    assert len(called) == 1


def test_approval_is_bound_to_exact_device_and_target(monkeypatch):
    ds._PENDING_CHALLENGES.clear()
    ds._APPROVED_TOKENS.clear()
    monkeypatch.setattr(ds, "android_properties", lambda serial: {"ok": True, "properties": {}})
    monkeypatch.setattr(ds, "audit", lambda *args, **kwargs: None)
    preview = ds.create_operation_preview("PHONE_A", "reboot", "system")
    token = ds.approve_operation(preview["challenge_id"])["approval_token"]
    with pytest.raises(ValueError, match="does not match"):
        ds.reboot_android("PHONE_B", "system", token)
    assert not ds._APPROVED_TOKENS


def test_factory_recovery_requires_approval_and_never_wipes(monkeypatch):
    ds._PENDING_CHALLENGES.clear()
    ds._APPROVED_TOKENS.clear()
    monkeypatch.setattr(ds, "android_properties", lambda serial: {"ok": True, "properties": {}})
    monkeypatch.setattr(ds, "audit", lambda *args, **kwargs: None)
    commands = []
    monkeypatch.setattr(ds, "_run", lambda command, timeout=12: (
        commands.append(command) or {"ok": True, "returncode": 0, "stdout": "", "stderr": ""}
    ))
    with pytest.raises(ValueError, match="approval"):
        ds.prepare_factory_reset("TEST123", True, "PREPARE RECOVERY")
    preview = ds.create_operation_preview("TEST123", "factory_reset_prepare",
        backup_confirmed=True, confirmation="PREPARE RECOVERY")
    token = ds.approve_operation(preview["challenge_id"])["approval_token"]
    result = ds.prepare_factory_reset("TEST123", True, "PREPARE RECOVERY", token)
    assert result["ok"] is True
    assert commands == [[ds._tool_path("adb"), "-s", "TEST123", "reboot", "recovery"]]
    assert "wipe" not in " ".join(commands[0]).lower()


def test_flashing_is_not_available_as_an_engine():
    report = ds.readiness_report()
    assert any("flashing engines are not implemented" in item.lower()
               for item in report["limitations"])


def test_boot_repair_assessment_is_read_only_when_no_device(monkeypatch):
    monkeypatch.setattr(ds, "discover_android", lambda: {
        "adb": [], "fastboot": [], "adb_available": True, "fastboot_available": True, "warnings": []
    })
    monkeypatch.setattr(ds, "audit", lambda *args, **kwargs: None)
    result = ds.assess_boot_repair(symptom="stuck_logo")
    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["device_mode"] == "not_detected"
    assert any("official driver" in x for x in result["next_steps"])

def test_boot_repair_assessment_rejects_invalid_symptom():
    with pytest.raises(ValueError):
        ds.assess_boot_repair(symptom="erase")

def test_boot_repair_fastboot_reads_identity_without_modifying_device(monkeypatch):
    commands = []
    monkeypatch.setattr(ds, "discover_android", lambda: {
        "adb": [], "fastboot": [{"serial": "FAST123", "state": "fastboot"}],
        "adb_available": True, "fastboot_available": True, "warnings": []
    })
    def fake_run(command, timeout=12):
        commands.append(command)
        return {"ok": True, "stdout": "", "stderr": "(bootloader) product: test"}
    monkeypatch.setattr(ds, "_run", fake_run)
    monkeypatch.setattr(ds, "audit", lambda *args, **kwargs: None)
    result = ds.assess_boot_repair("FAST123", "boot_loop")
    assert result["device_mode"] == "fastboot"
    assert len(commands) == 4
    assert all("getvar" in c for c in commands)
    assert not any(any(x in c for x in ("flash", "erase", "format", "reboot", "unlock")) for c in commands)


def test_usb_interface_detects_qualcomm_edl_without_guessing_phone_model():
    result = ds.classify_usb_interface(
        r"USB\\VID_05C6&PID_9008\\1234", "Qualcomm HS-USB QDLoader 9008", "Ports"
    )
    assert result["protocol_family"] == "qualcomm_edl"
    assert result["mode"] == "edl_9008"
    assert result["confidence"] == "high"
    assert result["model_identified"] is False


def test_usb_interface_reports_mediatek_as_candidate_not_exact_model():
    result = ds.classify_usb_interface(
        r"USB\\VID_0E8D&PID_2000\\ABC", "MediaTek PreLoader USB VCOM", "Ports"
    )
    assert result["protocol_family"] == "mediatek_usb"
    assert result["mode"] == "possible_preloader_or_bootrom"
    assert result["model_identified"] is False


def test_usb_interface_does_not_claim_samsung_download_mode_without_evidence():
    result = ds.classify_usb_interface(
        r"USB\\VID_04E8&PID_6860\\ABC", "Samsung Mobile USB Composite Device", "USB"
    )
    assert result["protocol_family"] == "samsung_usb"
    assert result["mode"] == "samsung_usb_interface"
    assert result["confidence"] == "low"


def test_unknown_usb_vendor_is_not_guessed():
    result = ds.classify_usb_interface(r"USB\\VID_FFFF&PID_0001\\ABC", "Unknown device")
    assert result["protocol_family"] == "unknown"
    assert result["brand_hint"] is None

def test_accessible_media_export_pulls_only_shared_storage(monkeypatch, tmp_path):
    commands = []
    def fake_run(command, timeout=12):
        commands.append(command)
        if command[-1] == "get-state":
            return {"ok": True, "stdout": "device", "stderr": ""}
        if "test" in command:
            return {"ok": command[-1] in ("/sdcard/DCIM", "/sdcard/Pictures"), "stdout": "", "stderr": ""}
        if "pull" in command:
            return {"ok": True, "stdout": "2 files pulled", "stderr": ""}
        raise AssertionError(command)
    monkeypatch.setattr(ds, "_run", fake_run)
    monkeypatch.setattr(ds, "audit", lambda *args, **kwargs: None)
    result = ds.backup_accessible_media("TEST123", str(tmp_path / "backup"))
    assert result["ok"] is True
    assert [x["folder"] for x in result["copied"]] == ["DCIM", "Pictures"]
    assert set(result["skipped"]) == {"Movies", "Music", "Download"}
    assert all("/sdcard/" in " ".join(command) for command in commands if "pull" in command)
    assert not any("data/data" in " ".join(command) for command in commands)


def test_accessible_media_export_requires_authorised_adb(monkeypatch, tmp_path):
    monkeypatch.setattr(ds, "_run", lambda command, timeout=12: {
        "ok": True, "stdout": "unauthorized", "stderr": ""
    })
    with pytest.raises(ValueError, match="not authorised"):
        ds.backup_accessible_media("TEST123", str(tmp_path / "backup"))


def test_phone_transfer_requires_two_distinct_authorised_devices(monkeypatch):
    calls = []
    def fake_run(command, timeout=12):
        calls.append(command)
        return {"ok": True, "stdout": "device", "stderr": ""}
    monkeypatch.setattr(ds, "_run", fake_run)
    monkeypatch.setattr(ds, "audit", lambda *args, **kwargs: None)
    result = ds.transfer_shared_media("PHONE_A", "PHONE_B")
    assert result["operation"] == "shared_media_phone_to_phone_transfer"
    assert result["ok"] is False
    assert len(calls) == 2
    with pytest.raises(ValueError, match="different phones"):
        ds.transfer_shared_media("PHONE_A", "PHONE_A")


def test_phone_transfer_stops_before_copy_if_destination_not_authorised(monkeypatch):
    calls = []
    def fake_run(command, timeout=12):
        calls.append(command)
        return {"ok": True, "stdout": "device" if "-s" in command and "PHONE_A" in command else "unauthorized", "stderr": ""}
    monkeypatch.setattr(ds, "_run", fake_run)
    with pytest.raises(ValueError, match="destination phone"):
        ds.transfer_shared_media("PHONE_A", "PHONE_B")
    assert len(calls) == 2
