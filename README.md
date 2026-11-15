# Vendora Mobile Toolkit — Development Build 0.6.0

Windows-first desktop toolkit for owner-authorised Android and Apple device discovery, diagnostics and recovery workflows.

## Included
- Electron desktop interface with a local FastAPI backend.
- Android ADB/Fastboot discovery, device properties, diagnostics and safe reboot targets.
- Read-only Windows USB Plug-and-Play inventory.
- Firmware ZIP integrity inspection and SHA-256 calculation (inspection only).
- FRP owner-recovery guidance, forgotten-screen-lock guidance, carrier-authorised SIM/network unlock guidance and official OEM bootloader-unlock guidance.
- Read-only Boot Repair assessment for startup-logo freezes, boot loops, failed updates, recovery-mode issues and black screens.
- Automatic repair preflight: device/protocol identification, USB inventory, firmware archive metadata and programmer-file hashing.
- Flashing engine registry, capability report, flash-plan endpoint and fail-closed execution endpoint.
- Automated Python tests and Windows x64 NSIS installer workflow.

## Working Android media export
The System Repair workspace includes an ADB-based **Shared media backup** operation. With an authorised, online Android ADB session, it copies accessible shared-storage folders (DCIM, Pictures, Movies, Music and Download) to a user-selected folder on the Windows PC. The export is initiated by the operator and audited. It does not access private app sandboxes, protected system partitions, messages or deleted files, and it is not a full-device image or a promise of data recovery.

USB inventory also classifies known interface candidates (including Qualcomm 9008, possible MediaTek preloader/BootROM and Samsung Download Mode candidates) conservatively. A USB vendor/product ID is not proof of the exact phone model or a working manufacturer service session.

## Recovery workflow scope
These are guided owner-recovery workflows, not universal automated unlock engines.
- **FRP:** ownership-verification checklist, previously synced Google Account recovery guidance and authorised manufacturer/service-centre referral. Vendora does not bypass or disable FRP and never collects account passwords or verification codes.
- **Screen lock:** official account/manufacturer recovery and authorised reset guidance. It does not remove a PIN/pattern or defeat device security.
- **SIM/network unlock:** carrier eligibility checklist and authorised request process. Carrier eligibility lookup and unlock-code generation are not implemented.
- **Bootloader unlock:** OEM compatibility and official procedure guidance. No generic forced unlock command or automated OEM eligibility bypass is provided.

## Boot Repair assessment
The assessment reads ADB properties/diagnostics when an authorised ADB session exists and selected Fastboot getvar fields when a device is already in Fastboot. It does not reboot, unlock, erase, format or flash a device. If no supported protocol is detected, it reports that limitation and provides safe next steps. This is diagnostic triage, not a firmware repair engine.

## Automatic repair preparation
The preflight planner can identify a selected ADB/Fastboot device, read reported manufacturer/model/product/build and chipset properties, inspect Windows USB PnP status, classify the likely protocol family, inspect a supplied ZIP and extract limited metadata, hash a supplied programmer/Download Agent file, and report blockers with a suggested pipeline. Metadata token matches do not prove firmware compatibility or authenticity; a file hash does not prove OEM authorisation or signature validity.

Endpoint: `POST /api/repair/prepare`. It is strictly read-only and returns `execution_enabled: false`. It does not install drivers, download firmware, validate OEM signatures, flash, erase, unlock or reset devices.

## Firmware flashing and customer approval
The flashing workspace exposes an engine registry, capability report, flash-plan endpoint and fail-closed execution endpoint. Before any production engine can be enabled, it must implement and pass:
1. Exact device/model/board and hardware-revision identification.
2. Trusted OEM firmware provenance and cryptographic signature verification.
3. Exact partition-plan and anti-rollback verification.
4. Required authorised programmer and driver checks.
5. Physical-device validation for every supported model/variant.
6. A fresh, single-use customer approval bound to the exact device serial, firmware SHA-256, engine and partition-plan hash.
7. A live device and package re-check immediately before the first write.

**Current status:** Google/Android Fastboot is not model-validated; Samsung Download Mode is not implemented; Qualcomm EDL and MediaTek Preloader are not implemented. No production write engine is enabled. The Flash button remains locked and the backend rejects flash execution. Customer approval will not override a failed compatibility or authenticity check. This framework is not yet a working universal flasher.

## Device-changing operations
Android reboot operations use a short-lived, one-time approval challenge bound to the selected device and target. Factory-reset preparation only reboots to Android Recovery; it does not issue a wipe command. Device-changing actions must never run automatically on connection or selection.

## Apple support
Apple discovery is experimental and depends on optional `pymobiledevice3` and Apple device support components. Discovery is not iOS repair, restore or Activation Lock removal.

## Reliability and packaging
- Desktop startup waits for the local backend health check.
- The desktop app uses a single-instance lock, backend restart attempts, renderer crash recovery and graceful shutdown handling.
- Audit entries are flushed to disk; audit-storage errors are non-fatal to device operations.
- The backend is packaged with PyInstaller; Electron resources are packaged in ASAR and release JavaScript is minified. These measures make casual inspection harder but do not prevent determined reverse engineering.
- USB drivers and external vendor service components may still need separate installation; support depends on the exact device and Windows driver state.

## Tests
Install development dependencies with `python -m pip install -r backend/requirements-dev.txt`, then run `python -m pytest -q` from the repository root.

## Windows installer
The GitHub Actions **Windows installer** workflow builds a Windows x64 NSIS installer on pushes to `main`. Download its artifact from the successful workflow run under **Actions**. The installer artifact is a ZIP containing the installer; the artifact archive size is not the same as the installed application size.

For a local Windows build with Python 3.11+ and Node.js 20+:
1. Run `backend\\build_windows.bat`.
2. Run `npm install` inside `desktop`.
3. Run `npm run dist:win` inside `desktop`.

A successful CI package build verifies the build and smoke-test steps, but physical-device behaviour still requires testing on supported sample phones. No claim of universal device compatibility or risk-free repair is made.


## Phone-to-phone transfer (shared files)
Vendora includes an ADB-based transfer operation for two Android phones that are both online and authorised on the PC. It copies accessible shared-storage folders (DCIM, Pictures, Movies, Music and Download) through a temporary local staging directory, then places the copied folders in a new `Vendora_Transfer_YYYYMMDD_HHMMSS` folder on the destination phone. Both device serials are checked before copying begins. This is not an app migration or a WhatsApp/chat transfer: private app data, accounts, messages, settings and protected content are not included. Physical-device testing is required across supported Android versions and manufacturers.
