# Vendora Mobile Toolkit — Development Build 0.6.0

Windows-first desktop service toolkit for owner-authorised Android and Apple device diagnostics and recovery guidance.

## Included
- Electron desktop interface and local FastAPI backend.
- Android ADB/Fastboot discovery, properties, diagnostics and safe reboot targets.
- Firmware ZIP integrity and SHA-256 inspection (inspection only; no flashing).
- Owner Recovery workflows for forgotten screen locks, authorised carrier/network unlocking, and official OEM bootloader unlocking.
- Explicit limitations and owner/data-protection warnings for all recovery workflows.
- Manufacturer readiness catalogue for Samsung, Google, Qualcomm, MediaTek, Apple and generic Android.
- Conservative Android family classification from reported device properties.
- Read-only Windows USB Plug-and-Play inventory endpoint.
- Desktop readiness panel and automated tests.\n- UI actions for owner-confirmed Android reboot to system, recovery or bootloader.\n- UI access to iPhone tooling status and read-only Windows USB inventory.
- Windows x64 NSIS installer build configuration and GitHub Actions workflow.

## Status and limitations
Manufacturer protocol profiles are readiness records, not completed vendor flashing engines. Qualcomm EDL and MediaTek BootROM/Preloader servicing are not implemented. Samsung Download Mode servicing is not implemented. Apple discovery remains experimental. No firmware is automatically selected or flashed. Owner recovery includes official forgotten-screen-lock guidance, carrier-authorised SIM/network unlock request guidance, and manufacturer-supported bootloader unlock guidance. These are guided workflows, not universal automated unlock engines. No PIN/pattern removal, FRP bypass, Activation Lock bypass, account bypass, carrier-code generation, OEM eligibility bypass or generic forced bootloader unlock is provided. Physical-device validation is outstanding; unknown models must remain unverified.

## Current desktop actions\nThe desktop interface now exposes the safe Android reboot endpoint with an explicit confirmation, plus iPhone tooling-status and Windows USB-inventory checks. The iPhone endpoint now attempts read-only discovery through the optional `pymobiledevice3 usbmux list` command. Install `pymobiledevice3` separately and, on Windows, install Apple's classic iTunes package to provide Apple Mobile Device Service. Discovery is not iOS repair or restore. See the [pymobiledevice3 installation guide](https://github.com/doronz88/pymobiledevice3/blob/master/docs/installation.md).\n\n## API additions
- GET /api/readiness — tool availability, protocol profiles and limitations.
- GET /api/devices/usb — read-only Windows USB PnP inventory.
- POST /api/android/classify — classify a connected Android device from its reported properties.

## Tests
Install development/test dependencies from the project root with `python -m pip install -r backend/requirements-dev.txt`, then run `python -m pytest -q`. The runtime requirements exclude test-only packages.

## Reliability, packaging and source protection
- Desktop startup waits for the local backend health check and records diagnostic logs under the user's application data folder.
- The desktop app uses a single-instance lock, backend restart attempts, renderer crash recovery and graceful shutdown handling.
- Audit entries are flushed to disk; audit-storage errors are non-fatal to device operations.
- Release preparation minifies the desktop JavaScript and packages only the release bundle, not the original desktop JavaScript file.
- Electron resources are packaged in ASAR and the NSIS installer uses maximum compression.
- The backend is packaged as a PyInstaller executable rather than loose Python source files. This raises the effort required to inspect it but does not make reverse engineering impossible; Python bytecode and Electron resources can still be extracted by determined users.
- Installer size and recovery behaviour must be measured on a real Windows build. No size target or crash-proof guarantee is claimed before that testing.

## External device tools\n- Android: install the official [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools) for `adb` and `fastboot`. The current installer does not bundle these tools or OEM USB drivers.\n- iPhone/iPad: install `pymobiledevice3` separately; Windows also needs Apple's classic iTunes package for Apple Mobile Device Service. The Microsoft Store Apple Devices service has known discovery limitations in some Wi-Fi scenarios.\n\n## Windows installer
The GitHub Actions workflow builds a Windows x64 NSIS installer. Open **Actions**, select **Windows installer**, and choose **Run workflow**, or push a `v*` tag. Download the resulting installer artifact.

For a local Windows build with Python 3.11+ and Node.js 20+:
1. Run `backend\build_windows.bat`.
2. Run `npm install` inside `desktop`.
3. Run `npm run dist:win` inside `desktop`.

The workflow has been prepared but has not yet been executed on a Windows runner. No installer is claimed as built or verified yet.


## Owner recovery workflows
- **Forgotten screen lock:** provides official account/manufacturer recovery steps and explains when an authorised reset may erase local data. It does not remove credentials or bypass anti-theft checks.
- **SIM/network unlock:** provides a carrier eligibility checklist and authorised request procedure. Carrier eligibility lookup and unlock-code generation require a supported carrier integration and are not implemented.
- **Bootloader unlock:** provides OEM compatibility checks, consequences and official procedure guidance. There is no generic fastboot unlock command and no automated OEM unlock engine in this build.
- Device-changing operations remain separately approval-gated. These three guidance workflows do not themselves issue device commands.
