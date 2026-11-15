import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import pytest
import flashing


def test_all_vendor_engines_are_fail_closed():
    capabilities = flashing.flash_capabilities()
    assert capabilities["approval_required"] is True
    assert capabilities["global_write_enabled"] is False
    assert all(not engine["write_enabled"] for engine in capabilities["engines"].values())


@pytest.mark.parametrize("engine_id", [
    "google_fastboot", "samsung_download", "qualcomm_edl", "mediatek_preloader"
])
def test_unvalidated_engine_cannot_create_flash_plan(engine_id):
    result = flashing.prepare_flash_plan("TEST123", "not-used.zip", engine_id)
    assert result["flash_enabled"] is False
    assert result["plan_id"] == ""
    assert result["blockers"]


def test_unknown_engine_rejected():
    with pytest.raises(ValueError, match="Unknown"):
        flashing.prepare_flash_plan("TEST123", "not-used.zip", "unknown")


def test_unvalidated_engine_cannot_flash_even_with_forged_approval():
    with pytest.raises(ValueError, match="blocked"):
        flashing.execute_flash("TEST123", "a" * 64, "samsung_download",
                               "b" * 64, "forged-token")
