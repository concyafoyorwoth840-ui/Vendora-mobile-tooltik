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
