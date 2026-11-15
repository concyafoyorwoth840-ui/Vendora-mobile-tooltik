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
