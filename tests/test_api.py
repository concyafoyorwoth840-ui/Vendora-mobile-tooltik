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


def test_frp_recovery_is_owner_guidance_not_bypass(monkeypatch):
    events = []
    monkeypatch.setattr(api, "unlock_workflow_guidance", lambda workflow: {
        "title": "Android Factory Reset Protection (FRP) owner recovery",
        "status": "OWNER_VERIFICATION_AND_OFFICIAL_ACCOUNT_RECOVERY",
        "steps": ["Use the previously synced Google Account."],
        "limitations": ["Vendora does not bypass FRP."]
    } if workflow == "frp_recovery" else (_ for _ in ()).throw(ValueError("Unknown recovery workflow")))
    response = client.get("/api/recovery/workflows/frp_recovery")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "OWNER_VERIFICATION_AND_OFFICIAL_ACCOUNT_RECOVERY"
    assert any("does not bypass FRP" in item for item in body["limitations"])
