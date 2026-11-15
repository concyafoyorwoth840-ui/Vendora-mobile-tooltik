import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient
import app as api
client=TestClient(api.app)

def test_health_endpoint():
    r=client.get("/api/health")
    assert r.status_code==200 and r.json()["app"]=="Vendora Mobile Toolkit"

def test_readiness_endpoint():
    r=client.get("/api/readiness")
    assert r.status_code==200 and "limitations" in r.json()

def test_usb_inventory_endpoint():
    assert client.get("/api/devices/usb").status_code==200

def test_reboot_rejects_unsafe_target():
    r=client.post("/api/android/reboot",json={"serial":"TEST123","target":"wipe"})
    assert r.status_code==400

def test_unknown_recovery_platform():
    assert client.get("/api/recovery/unknown").status_code==400
