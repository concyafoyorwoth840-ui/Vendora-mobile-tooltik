const { app, BrowserWindow } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");
let backend = null, quitting = false;
function startBackend() {
  const bundled = path.join(process.resourcesPath, "backend", "VendoraBackend.exe");
  const dir = path.join(__dirname, "..", "backend");
  const win = process.platform === "win32";
  let exe, args, cwd;
  if (app.isPackaged && fs.existsSync(bundled)) { exe = bundled; args = []; cwd = path.dirname(bundled); }
  else {
    const venv = path.join(dir, ".venv", "Scripts", "python.exe");
    const useVenv = win && fs.existsSync(venv);
    exe = useVenv ? venv : (process.env.VENDORA_PYTHON || (win ? "py" : "python3"));
    args = !useVenv && win && exe === "py" ? ["-3", "app.py"] : ["app.py"]; cwd = dir;
  }
  backend = spawn(exe, args, {cwd, windowsHide:true, stdio:["ignore","pipe","pipe"], env:{...process.env,PYTHONUNBUFFERED:"1"}});
  backend.on("error", e => console.error("Vendora backend:", e.message));
  backend.on("exit", (c,s) => { if (!quitting) console.error("Vendora backend stopped", c, s); backend=null; });
}
function createWindow() {
  const win = new BrowserWindow({width:1280,height:820,minWidth:980,minHeight:680,backgroundColor:"#071426",
    webPreferences:{contextIsolation:true,nodeIntegration:false,sandbox:true}});
  win.loadFile(path.join(__dirname,"index.html"));
}
app.whenReady().then(()=>{startBackend();createWindow();});
app.on("before-quit",()=>{quitting=true;if(backend&&!backend.killed)backend.kill();});
app.on("window-all-closed",()=>{if(process.platform!=="darwin")app.quit();});
