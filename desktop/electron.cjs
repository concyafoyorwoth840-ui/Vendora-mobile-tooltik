const { app, BrowserWindow, dialog } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");

const API = "http://127.0.0.1:8765";
const STARTUP_TIMEOUT_MS = 30000;
const MAX_BACKEND_RESTARTS = 2;
let backend = null;
let mainWindow = null;
let quitting = false;
let restartCount = 0;
let restartTimer = null;
let logStream = null;

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

function log(message) {
  const line = `[${new Date().toISOString()}] ${message}\n`;
  try {
    if (!logStream) {
      const logDir = path.join(app.getPath("userData"), "logs");
      fs.mkdirSync(logDir, { recursive: true });
      logStream = fs.createWriteStream(path.join(logDir, "vendora.log"), { flags: "a" });
    }
    logStream.write(line);
  } catch (_) {
    // Logging must never crash the application.
  }
}

function backendCommand() {
  const bundled = path.join(process.resourcesPath, "backend", "VendoraBackend.exe");
  const backendDir = path.join(__dirname, "..", "backend");
  if (app.isPackaged && fs.existsSync(bundled)) {
    return { exe: bundled, args: [], cwd: path.dirname(bundled) };
  }
  const venvPython = path.join(backendDir, ".venv", "Scripts", "python.exe");
  if (process.platform === "win32" && fs.existsSync(venvPython)) {
    return { exe: venvPython, args: ["app.py"], cwd: backendDir };
  }
  const python = process.env.VENDORA_PYTHON || (process.platform === "win32" ? "py" : "python3");
  return { exe: python, args: python === "py" ? ["-3", "app.py"] : ["app.py"], cwd: backendDir };
}

function startBackend() {
  const command = backendCommand();
  log(`Starting backend: ${command.exe}`);
  try {
    backend = spawn(command.exe, command.args, {
      cwd: command.cwd,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" }
    });
  } catch (error) {
    log(`Backend spawn failed: ${error.message}`);
    return null;
  }
  backend.stdout.on("data", data => log(`backend: ${String(data).trim()}`));
  backend.stderr.on("data", data => log(`backend error: ${String(data).trim()}`));
  backend.on("error", error => log(`Backend process error: ${error.message}`));
  backend.on("exit", (code, signal) => {
    log(`Backend exited: code=${code}, signal=${signal}`);
    backend = null;
    if (!quitting && restartCount < MAX_BACKEND_RESTARTS) {
      restartCount += 1;
      clearTimeout(restartTimer);
      restartTimer = setTimeout(async () => {
        log(`Restart attempt ${restartCount}`);
        startBackend();
      }, 1800);
    } else if (!quitting && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("vendora-backend-status", "Backend stopped. Please restart Vendora.");
    }
  });
  return backend;
}

async function waitForBackend() {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline && !quitting) {
    if (backend && backend.exitCode === null) {
      try {
        const response = await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(1200) });
        if (response.ok) {
          const health = await response.json();
          if (health.ok) {
            restartCount = 0;
            log("Backend health check passed.");
            return true;
          }
        }
      } catch (_) {
        // Backend is still starting; retry until the startup deadline.
      }
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  log("Backend startup health check timed out.");
  return false;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 680,
    backgroundColor: "#071426",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    log(`Renderer process gone: ${details.reason}`);
    if (!quitting && !mainWindow.isDestroyed()) {
      mainWindow.webContents.reload();
    }
  });
  mainWindow.on("unresponsive", () => {
    log("Renderer became unresponsive.");
    dialog.showMessageBox(mainWindow, {
      type: "warning",
      buttons: ["Wait", "Reload"],
      defaultId: 0,
      message: "Vendora is taking longer than expected.",
      detail: "You can wait for it to recover or reload the interface."
    }).then(({ response }) => {
      if (response === 1 && mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.reload();
    }).catch(error => log(`Recovery dialog failed: ${error.message}`));
  });
  mainWindow.loadFile(path.join(__dirname, "index.html"));
  mainWindow.on("closed", () => { mainWindow = null; });
}

app.whenReady().then(async () => {
  if (quitting) return;
  startBackend();
  const ready = await waitForBackend();
  createWindow();
  if (!ready) {
    dialog.showMessageBox(mainWindow, {
      type: "warning",
      buttons: ["Continue"],
      message: "Vendora's local service did not start yet.",
      detail: "The interface will open, but device functions may be unavailable. Check the Vendora log file for details."
    }).catch(error => log(`Startup dialog failed: ${error.message}`));
  }
}).catch(error => {
  log(`Application startup failed: ${error.stack || error.message}`);
  dialog.showErrorBox("Vendora Mobile Toolkit", "Vendora could not start. Please restart the application.");
});

app.on("before-quit", () => {
  quitting = true;
  clearTimeout(restartTimer);
  if (backend && !backend.killed) {
    try { backend.kill(); } catch (error) { log(`Backend shutdown error: ${error.message}`); }
  }
  if (logStream) {
    try { logStream.end(); } catch (_) {}
    logStream = null;
  }
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
