from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from device_service import (tool_status, discover_android, android_properties,
    android_diagnostics, reboot_android, inspect_firmware_zip, iphone_status,
    recovery_guidance, unlock_workflow_guidance, classify_android, windows_usb_inventory, readiness_report, prepare_factory_reset,
    create_operation_preview, approve_operation, assess_boot_repair)

app = FastAPI(title="Vendora Mobile Toolkit API", version="0.6.0")

class DeviceRequest(BaseModel):
    serial: str = Field(min_length=1, max_length=128)

class RebootRequest(DeviceRequest):
    target: str
    approval_token: str = Field(default="", max_length=256)

class FirmwareRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2048)

class FactoryResetPrepareRequest(DeviceRequest):
    backup_confirmed: bool
    confirmation: str = Field(min_length=1, max_length=64)
    approval_token: str = Field(min_length=1, max_length=256)

class OperationPreviewRequest(DeviceRequest):
    operation: str
    target: str = ""
    backup_confirmed: bool = False
    confirmation: str = ""

class OperationApprovalRequest(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=128)


class BootRepairAssessmentRequest(BaseModel):
    serial: str = Field(default="", max_length=128)
    symptom: str = Field(default="stuck_logo", max_length=32)

@app.post("/api/boot-repair/assess")
def boot_repair_assess(req: BootRepairAssessmentRequest):
    try: return assess_boot_repair(req.serial, req.symptom)
    except ValueError as e: raise HTTPException(400, str(e))

@app.get("/api/health")
def health():
    return {"ok": True, "app": "Vendora Mobile Toolkit", "version": app.version, "tools": tool_status()}

@app.get("/api/devices/android")
def android_devices():
    return discover_android()

@app.get("/api/devices/iphone")
def iphone_devices():
    return iphone_status()

@app.get("/api/devices/usb")
def usb_devices():
    return windows_usb_inventory()

@app.get("/api/readiness")
def readiness():
    return readiness_report()

@app.post("/api/android/properties")
def properties(req: DeviceRequest):
    try: return android_properties(req.serial)
    except ValueError as e: raise HTTPException(400, str(e))

@app.post("/api/android/classify")
def classify(req: DeviceRequest):
    try:
        data = android_properties(req.serial)
        if not data.get("ok"): return data
        p = data.get("properties", {})
        return {"serial": req.serial, **classify_android(p.get("ro.product.manufacturer", ""),
            p.get("ro.product.model", ""), p.get("ro.product.device", ""), p.get("ro.build.fingerprint", ""))}
    except ValueError as e: raise HTTPException(400, str(e))

@app.post("/api/android/diagnostics")
def diagnostics(req: DeviceRequest):
    try: return android_diagnostics(req.serial)
    except ValueError as e: raise HTTPException(400, str(e))

@app.post("/api/operations/preview")
def operation_preview(req: OperationPreviewRequest):
    try:
        return create_operation_preview(req.serial, req.operation, req.target,
            req.backup_confirmed, req.confirmation)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/operations/approve")
def operation_approve(req: OperationApprovalRequest):
    try: return approve_operation(req.challenge_id)
    except ValueError as e: raise HTTPException(400, str(e))

@app.post("/api/android/reboot")
def reboot(req: RebootRequest):
    try: return reboot_android(req.serial, req.target, req.approval_token)
    except ValueError as e: raise HTTPException(400, str(e))

@app.post("/api/android/factory-reset/prepare")
def factory_reset_prepare(req: FactoryResetPrepareRequest):
    try:
        return prepare_factory_reset(req.serial, req.backup_confirmed, req.confirmation, req.approval_token)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/api/firmware/inspect")
def firmware(req: FirmwareRequest):
    try: return inspect_firmware_zip(req.path)
    except ValueError as e: raise HTTPException(400, str(e))


@app.get("/api/recovery/workflows/{workflow}")
def recovery_workflow(workflow: str):
    try: return unlock_workflow_guidance(workflow)
    except ValueError as e: raise HTTPException(400, str(e))

@app.get("/api/recovery/{platform}")
def recovery(platform: str):
    try: return {"platform": platform, "steps": recovery_guidance(platform)}
    except ValueError as e: raise HTTPException(400, str(e))

@app.post("/api/firmware/flash")
def firmware_flash_unavailable():
    # Fail closed until an OEM-specific, validated flashing engine exists.
    raise HTTPException(501, "Firmware flashing is not implemented for this device family. No device command was executed.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)

