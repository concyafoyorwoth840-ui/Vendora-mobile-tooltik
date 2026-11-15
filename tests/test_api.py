import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient
import app as api

client = TestClient(api.app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["app"] == "Vendora Mobile Toolkit"

def test_android_discovery_endpoint(monkeypatch):
    monkeypatch.setattr(api, "discover_android", lambda: {
        "adb_available": True, "fastboot_available": True,
        "adb": [{"serial": "TEST123", "state": "device"}],
        "fastboot": [], "warnings": []
    })
    response = client.get("/api/devices/android")
    assert response.status_code == 200
    assert response.json()["adb"][0]["serial"] == "TEST123"

def test_reboot_rejects_unsafe_target():
    response = client.post("/api/android/reboot", json={"serial":"TEST123","target":"wipe"})
    assert response.status_code == 400

def test_unknown_recovery_platform():
    response = client.get("/api/recovery/unknown")
    assert response.status_code == 400

def test_iphone_endpoint_is_explicit_about_status():
    response = client.get("/api/devices/iphone")
    assert response.status_code == 200
    assert "message" in response.json()


def test_readiness_endpoint():
    response = client.get("/api/readiness")
    assert response.status_code == 200
    assert "limitations" in response.json()

def test_usb_inventory_endpoint():
    response = client.get("/api/devices/usb")
    assert response.status_code == 200

def test_screen_lock_workflow_is_guidance_only():
    response = client.get("/api/recovery/workflows/screen_lock")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OFFICIAL_RECOVERY_GUIDANCE"
    assert any("does not remove PINs" in item for item in body["limitations"])

def test_carrier_unlock_workflow_does_not_claim_to_generate_codes():
    response = client.get("/api/recovery/workflows/carrier_unlock")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CARRIER_AUTHORISED_PROCESS"
    assert any("cannot query carrier eligibility" in item for item in body["limitations"])

def test_bootloader_unlock_workflow_requires_oem_compatibility():
    response = client.get("/api/recovery/workflows/bootloader_unlock")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OEM_COMPATIBILITY_CHECK_REQUIRED"
    assert any("generic fastboot unlock command" in item for item in body["limitations"])

def test_unknown_unlock_workflow_rejected():
    response = client.get("/api/recovery/workflows/not-a-workflow")
    assert response.status_code == 400


def test_frp_recovery_is_owner_guidance_not_bypass():
    response = client.get("/api/recovery/workflows/frp_recovery")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OWNER_VERIFICATION_AND_OFFICIAL_ACCOUNT_RECOVERY"
    assert any("does not bypass" in item and "FRP" in item for item in body["limitations"])
    assert any("previously added and synced" in item for item in body["steps"])
    assert any("password" in item.lower() for item in body["limitations"])


def test_boot_repair_assessment_endpoint_is_read_only(monkeypatch):
    monkeypatch.setattr(api, "assess_boot_repair", lambda serial="", symptom="stuck_logo": {
        "ok": True, "read_only": True, "symptom": symptom, "device_mode": "not_detected",
        "assessment": "No service protocol detected", "next_steps": [], "limitations": ["No flashing"]
    })
    response = client.post("/api/boot-repair/assess", json={"symptom": "stuck_logo"})
    assert response.status_code == 200
    assert response.json()["read_only"] is True

def test_boot_repair_rejects_unknown_symptom():
    response = client.post("/api/boot-repair/assess", json={"symptom": "wipe_phone"})
    assert response.status_code == 400


def test_automatic_repair_preparation_endpoint_is_read_only(monkeypatch):
    monkeypatch.setattr(api, "build_repair_plan", lambda serial="", symptom="stuck_logo", firmware_path="", programmer_path="": {
        "ok": True, "read_only": True, "execution_enabled": False,
        "repair_ready": False, "blockers": ["No validated engine"]
    })
    response = client.post("/api/repair/prepare", json={"symptom": "stuck_logo"})
    assert response.status_code == 200
    assert response.json()["read_only"] is True
    assert response.json()["execution_enabled"] is False


def test_flash_capabilities_are_fail_closed():
    response = client.get("/api/firmware/flash/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["approval_required"] is True
    assert body["global_write_enabled"] is False
    assert all(not engine["write_enabled"] for engine in body["engines"].values())


def test_flash_plan_does_not_enable_unvalidated_engine():
    response = client.post("/api/firmware/flash/plan", json={
        "serial": "TEST123", "firmware_path": "C:/not-used.zip",
        "engine_id": "samsung_download"
    })
    assert response.status_code == 200
    assert response.json()["flash_enabled"] is False
    assert response.json()["plan_id"] == ""


def test_flash_execution_fails_closed_without_validated_engine():
    response = client.post("/api/firmware/flash", json={
        "serial": "TEST123", "package_sha256": "a" * 64,
        "engine_id": "samsung_download", "partition_plan_sha256": "b" * 64,
        "approval_token": "not-a-real-token"
    })
    assert response.status_code == 409

def test_media_backup_endpoint_uses_selected_device_and_destination(monkeypatch, tmp_path):
    captured = {}
    def fake_backup(serial, destination):
        captured["serial"] = serial
        captured["destination"] = destination
        return {"ok": True, "operation": "accessible_shared_media_export"}
    monkeypatch.setattr(api, "backup_accessible_media", fake_backup)
    response = client.post("/api/android/media-backup", json={
        "serial": "TEST123", "destination": str(tmp_path / "backup")
    })
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["serial"] == "TEST123"
    assert captured["destination"] == str(tmp_path / "backup")


def test_phone_transfer_endpoint_calls_transfer_engine(monkeypatch):
    captured = {}
    def fake_transfer(source_serial, destination_serial):
        captured["source"] = source_serial
        captured["destination"] = destination_serial
        return {"ok": True, "operation": "shared_media_phone_to_phone_transfer"}
    monkeypatch.setattr(api, "transfer_shared_media", fake_transfer)
    response = client.post("/api/android/phone-transfer", json={
        "source_serial": "PHONE_A", "destination_serial": "PHONE_B"
    })
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured == {"source": "PHONE_A", "destination": "PHONE_B"}


def test_media_restore_endpoint_calls_restore_engine(monkeypatch, tmp_path):
    captured = {}
    def fake_restore(serial, source_folder):
        captured["serial"] = serial
        captured["source_folder"] = source_folder
        return {"ok": True, "operation": "accessible_shared_media_restore"}
    monkeypatch.setattr(api, "restore_accessible_media", fake_restore)
    response = client.post("/api/android/media-restore", json={
        "serial": "PHONE_A", "source_folder": str(tmp_path)
    })
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured == {"serial": "PHONE_A", "source_folder": str(tmp_path)}
