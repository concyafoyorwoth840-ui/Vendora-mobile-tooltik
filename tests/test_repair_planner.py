import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import pytest
import repair_planner as rp


def test_preflight_is_read_only_and_reports_missing_identity(monkeypatch):
    monkeypatch.setattr(rp, "discover_android", lambda: {
        "adb": [], "fastboot": [], "warnings": []
    })
    monkeypatch.setattr(rp, "windows_usb_inventory", lambda: {
        "supported": False, "devices": []
    })
    monkeypatch.setattr(rp, "audit", lambda *args, **kwargs: None)
    result = rp.build_repair_plan()
    assert result["ok"] is True
    assert result["read_only"] is True
    assert result["execution_enabled"] is False
    assert result["repair_ready"] is False
    assert result["device_mode"] == "not_detected"
    assert result["blockers"]


def test_preflight_identifies_adb_model_and_chipset(monkeypatch):
    monkeypatch.setattr(rp, "discover_android", lambda: {
        "adb": [{"serial": "PHONE123", "state": "device"}],
        "fastboot": [], "warnings": []
    })
    monkeypatch.setattr(rp, "android_properties", lambda serial: {
        "ok": True, "properties": {
            "ro.product.manufacturer": "samsung",
            "ro.product.model": "SM-G998W",
            "ro.product.device": "p3q",
            "ro.board.platform": "exynos2100",
            "ro.build.fingerprint": "samsung/p3q/p3q:13"
        }
    })
    monkeypatch.setattr(rp, "windows_usb_inventory", lambda: {
        "supported": True, "devices": [], "count": 0
    })
    monkeypatch.setattr(rp, "audit", lambda *args, **kwargs: None)
    result = rp.build_repair_plan("PHONE123")
    assert result["device"]["model"] == "SM-G998W"
    assert result["device"]["chipset"] == "exynos2100"
    assert result["protocol_engine"]["name"] == "Samsung Download Mode"
    assert result["execution_enabled"] is False
    assert "not implemented" in " ".join(result["blockers"]).lower()


def test_preflight_rejects_unknown_symptom():
    with pytest.raises(ValueError, match="symptom"):
        rp.build_repair_plan(symptom="factory_wipe")


def test_firmware_metadata_match_is_not_marked_compatible(monkeypatch, tmp_path):
    import zipfile
    archive_path = tmp_path / "firmware.zip"
    with zipfile.ZipFile(archive_path, "w") as z:
        z.writestr("android-info.txt", "require board=p3q")
    monkeypatch.setattr(rp, "discover_android", lambda: {
        "adb": [{"serial": "PHONE123", "state": "device"}],
        "fastboot": [], "warnings": []
    })
    monkeypatch.setattr(rp, "android_properties", lambda serial: {
        "ok": True, "properties": {
            "ro.product.manufacturer": "samsung",
            "ro.product.model": "SM-G998W",
            "ro.product.device": "p3q",
            "ro.board.platform": "exynos2100",
            "ro.build.fingerprint": "samsung/p3q/p3q:13"
        }
    })
    monkeypatch.setattr(rp, "windows_usb_inventory", lambda: {
        "supported": False, "devices": []
    })
    monkeypatch.setattr(rp, "audit", lambda *args, **kwargs: None)
    result = rp.build_repair_plan("PHONE123", firmware_path=str(archive_path))
    assert result["firmware_check"]["status"] == "model_token_found_but_not_authenticated"
    assert result["firmware_check"]["compatible"] is False
