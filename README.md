# Vendora Mobile Toolkit — v0.4 development source

Windows-first desktop service toolkit for owner-authorised Android and Apple device diagnostics and recovery guidance.

## Included
- Electron desktop interface and local FastAPI backend.
- Android ADB/Fastboot discovery and read-only diagnostics.
- Exact-model compatibility catalogue with conservative `unverified` defaults.
- Firmware ZIP integrity and SHA-256 inspection.
- Safe reboot targets and recovery guidance.
- Read-only protocol capability inventory for Android standard tools, Samsung USB/Download Mode, Qualcomm EDL, MediaTek Preloader, Apple Mobile Device/Recovery/DFU, and OEM USB families.
- Automated tests included in the source package.
- Windows x64 NSIS installer build scripts.
- GitHub Actions workflow at `.github/workflows/windows-build.yml`.

## Build
See the source package and workflow for build instructions. Manufacturer protocol entries are capability records and integration scaffolding, not completed proprietary repair engines. This version does not flash firmware, restore iOS, remove screen passcodes, bypass FRP or Activation Lock, or unlock bootloaders. Physical-device validation remains required. Unknown models remain `unverified`; do not claim universal compatibility.
