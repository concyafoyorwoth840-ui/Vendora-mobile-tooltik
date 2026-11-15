# Vendora Mobile Toolkit — Development Build 0.4

Windows-first desktop service toolkit for owner-authorised Android and Apple device diagnostics and recovery guidance.

## Included
- Electron desktop interface and local FastAPI backend.
- Android ADB/Fastboot discovery, properties, diagnostics and safe reboot targets.
- Firmware ZIP integrity and SHA-256 inspection (inspection only; no flashing).
- Manufacturer readiness catalogue for Samsung, Google, Qualcomm, MediaTek, Apple and generic Android.
- Conservative Android family classification from reported device properties.
- Read-only Windows USB Plug-and-Play inventory endpoint.
- Desktop readiness panel and automated tests.\n- UI actions for owner-confirmed Android reboot to system, recovery or bootloader.\n- UI access to iPhone tooling status and read-only Windows USB inventory.
- Windows x64 NSIS installer build configuration and GitHub Actions workflow.

## Status and limitations
Manufacturer protocol profiles are readiness records, not completed vendor flashing engines. Qualcomm EDL and MediaTek BootROM/Preloader servicing are not implemented. Samsung Download Mode servicing is not implemented. Apple discovery remains experimental. No firmware is automatically selected or flashed. No screen-lock, FRP, Activation Lock, account or bootloader bypass is provided. Physical-device validation is outstanding; unknown models must remain unverified.

## Current desktop actions\nThe desktop interface now exposes the safe Android reboot endpoint with an explicit confirmation, plus iPhone tooling-status and Windows USB-inventory checks. The iPhone endpoint now attempts read-only discovery through the optional `pymobiledevice3 usbmux list` command. Install `pymobiledevice3` separately and, on Windows, install Apple's classic iTunes package to provide Apple Mobile Device Service. Discovery is not iOS repair or restore. See the [pymobiledevice3 installation guide](https://github.com/doronz88/pymobiledevice3/blob/master/docs/installation.md).\n\n## API additions
- GET /api/readiness — tool availability, protocol profiles and limitations.
- GET /api/devices/usb — read-only Windows USB PnP inventory.
- POST /api/android/classify — classify a connected Android device from its reported properties.

## Tests
Run from the project root: `python -m pytest -q`.

## External device tools\n- Android: install the official [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools) for `adb` and `fastboot`. The current installer does not bundle these tools or OEM USB drivers.\n- iPhone/iPad: install `pymobiledevice3` separately; Windows also needs Apple's classic iTunes package for Apple Mobile Device Service. The Microsoft Store Apple Devices service has known discovery limitations in some Wi-Fi scenarios.\n\n## Windows installer
The GitHub Actions workflow builds a Windows x64 NSIS installer. Open **Actions**, select **Windows installer**, and choose **Run workflow**, or push a `v*` tag. Download the resulting installer artifact.

For a local Windows build with Python 3.11+ and Node.js 20+:
1. Run `backend\build_windows.bat`.
2. Run `npm install` inside `desktop`.
3. Run `npm run dist:win` inside `desktop`.

The workflow has been prepared but has not yet been executed on a Windows runner. No installer is claimed as built or verified yet.
