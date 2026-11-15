const API="http://127.0.0.1:8765";const $=id=>document.getElementById(id);let devices=[];let lastUsb=[];
async function api(path,options={}){const r=await fetch(API+path,{headers:{"Content-Type":"application/json"},...options});const d=await r.json().catch(()=>({detail:"Invalid API response"}));if(!r.ok)throw new Error(d.detail||"HTTP "+r.status);return d;}
function output(id,v){const el=$(id);if(!el)return;el.textContent=typeof v==="string"?v:JSON.stringify(v,null,2);}
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function setPage(id){document.querySelectorAll(".page").forEach(x=>x.classList.toggle("active",x.id===id));document.querySelectorAll(".nav").forEach(x=>x.classList.toggle("active",x.dataset.tab===id));$("pageTitle").textContent=id==="repair"?"System Repair":id==="unlock"?"Owner Recovery":"Overview";window.scrollTo({top:0,behavior:"smooth"});}
document.querySelectorAll(".nav").forEach(b=>b.addEventListener("click",()=>setPage(b.dataset.tab)));
document.querySelectorAll("[data-open]").forEach(b=>b.addEventListener("click",()=>setPage(b.dataset.open)));
document.querySelectorAll(".subnav").forEach(b=>b.addEventListener("click",()=>{setPage(b.dataset.tab);const target=$(b.dataset.focus);if(target)target.scrollIntoView({behavior:"smooth",block:"center"});}));
async function health(){try{const h=await api("/api/health");$("statusText").textContent="Local service connected";$("sideStatus").textContent="Connected";$("statusDot").style.background="#35d4ad";$("toolsState").textContent=(h.tools.adb?"ADB":"—")+" / "+(h.tools.fastboot?"Fastboot":"—");}catch(e){$("statusText").textContent="Local service unavailable";$("sideStatus").textContent="Unavailable";$("statusDot").style.background="#e7b15c";$("toolsState").textContent="Offline";}}
async function readiness(){try{output("readinessOutput",await api("/api/readiness"));}catch(e){output("readinessOutput",e.message);}}
async function scan(){const box=$("deviceList");box.textContent="Scanning ADB, Fastboot and Windows USB…";try{const [d,usb]=await Promise.all([api("/api/devices/android"),api("/api/devices/usb").catch(e=>({supported:false,devices:[],message:e.message}))]);devices=[...(d.adb||[]).map(x=>({...x,mode:"ADB"})),...(d.fastboot||[]).map(x=>({...x,mode:"Fastboot"}))];lastUsb=usb.devices||[];$("adbCount").textContent=(d.adb||[]).length;$("fbCount").textContent=(d.fastboot||[]).length;$("usbCount").textContent=usb.supported?(usb.count??lastUsb.length):"N/A";const androidRows=devices.map(x=>{const hint=x.state==="unauthorized"?" · approve USB debugging on phone":x.state==="offline"?" · reconnect device":"";return '<div class="device"><b>'+esc(x.serial)+'</b><span>'+esc(x.mode)+" · "+esc(x.state)+esc(hint)+'</span></div>';});const usbRows=lastUsb.slice(0,15).map(x=>{const d=x.detection||{};const detail=d.protocol_family&&d.protocol_family!=="unknown"?" · "+d.protocol_family+" / "+d.mode+" ("+d.confidence+")":" · USB interface not classified";return '<div class="device"><b>'+esc(x.FriendlyName||x.Name||"USB device")+'</b><span>Windows USB · '+esc(x.Status||"Unknown")+esc(detail)+'</span></div>';});let message="";if(!devices.length)message='<div class="empty-state"><b>No ADB or Fastboot session detected.</b><br>For Android: unlock the phone, select File Transfer (MTP), enable Developer options → USB debugging, reconnect and approve this computer. USB listing below helps distinguish a driver issue from an ADB authorisation issue.</div>';const usbHeader=usb.supported?'<p class="muted-line">Windows USB devices present: '+lastUsb.length+'</p>':'<p class="muted-line">Windows USB inventory unavailable: '+esc(usb.message||"")+'</p>';box.innerHTML=androidRows.join("")+message+usbHeader+usbRows.join("")+(lastUsb.length>15?'<p class="muted-line">Showing first 15 USB entries.</p>':"");const select=$("repairDevice");const prior=select.value;select.innerHTML=devices.filter(x=>(x.mode==="ADB"&&x.state==="device")||x.mode==="Fastboot").map(x=>'<option value="'+esc(x.serial)+'">'+esc(x.serial)+' · '+esc(x.mode)+'</option>').join("")||'<option value="">No authorised ADB device</option>';if([...select.options].some(x=>x.value===prior))select.value=prior;$("selectionState").textContent=select.value?"DEVICE SELECTED":"NO DEVICE SELECTED";if(select.value)loadIdentity();if(!devices.length&&d.warnings?.length)box.innerHTML+='<p class="muted-line">Tool warning: '+esc(d.warnings.join("; "))+'</p>'; }catch(e){box.textContent="Scan failed: "+e.message;}}
async function selectedAction(path){const serial=$("repairDevice").value;if(!serial){output("repairOutput","No authorised Android device selected. Run a scan and approve the USB debugging prompt on the phone.");$("selectionState").textContent="NO DEVICE SELECTED";return;}$("selectionState").textContent="DEVICE SELECTED";try{output("repairOutput","Working…");const result=await api(path,{method:"POST",body:JSON.stringify({serial})});output("repairOutput",result);}catch(e){output("repairOutput","Operation failed: "+e.message);}}
async function loadIdentity(){
 const serial=$("repairDevice").value;
 if(!serial){$("selectionState").textContent="NO DEVICE SELECTED";return;}
 $("selectionState").textContent="READING DEVICE…";
 try {
  const selected=devices.find(x=>x.serial===serial);
  if(selected?.mode==="Fastboot"){
   const r=await api("/api/boot-repair/assess",{method:"POST",body:JSON.stringify({serial,symptom:$("bootSymptom")?.value||"stuck_logo"})});
   output("repairOutput",["FASTBOOT DEVICE IDENTITY","Serial: "+serial,"Mode: "+r.device_mode,JSON.stringify(r.identity||{},null,2),"","This is read-only bootloader information. No unlock, erase, reboot or flash command was sent."].join("\n"));
   $("selectionState").textContent="FASTBOOT IDENTIFIED";
   return;
  }
  const pair=await Promise.all([api("/api/android/properties",{method:"POST",body:JSON.stringify({serial})}),api("/api/android/classify",{method:"POST",body:JSON.stringify({serial})})]);
  const p=pair[0].properties||{}, profile=pair[1];
  const lines=["DEVICE IDENTITY","Manufacturer: "+(p["ro.product.manufacturer"]||"Not reported"),"Model: "+(p["ro.product.model"]||"Not reported"),"Device code: "+(p["ro.product.device"]||"Not reported"),"Android version: "+(p["ro.build.version.release"]||"Not reported"),"SDK: "+(p["ro.build.version.sdk"]||"Not reported"),"Build fingerprint: "+(p["ro.build.fingerprint"]||"Not reported"),"","PROTOCOL PROFILE",profile.manufacturer_family||"Unknown","Readiness: "+(profile.protocols?.status||"Not classified"),"Confidence: "+(profile.identification_confidence||"unknown"),"","Device properties are reported by the phone. A protocol profile is not proof that a repair engine is available."];
  output("repairOutput",lines.join("\\n"));$("selectionState").textContent="IDENTIFIED";
 } catch(e) { output("repairOutput","Could not read device identity: "+e.message+"\\nCheck USB debugging authorisation.");$("selectionState").textContent="IDENTITY READ FAILED"; }
}
$("repairDevice").addEventListener("change",loadIdentity);
$("scanBtn").onclick=$("refreshBtn").onclick=$("repairScanBtn").onclick=$("headerScan").onclick=scan;$("readinessBtn").onclick=readiness;
$("mediaBackupBtn").onclick=async()=>{const serial=$("repairDevice").value;const destination=$("mediaBackupPath").value.trim();if(!serial){output("repairOutput","Select an authorised ADB device first.");return;}if(!destination){output("repairOutput","Choose a destination folder on this PC.");return;}if(!window.confirm("Export accessible shared media from "+serial+" to "+destination+"? Existing files with the same names may be overwritten. This does not recover deleted files or private app data.")){output("repairOutput","Media export cancelled.");return;}try{output("repairOutput","Exporting shared media. Keep the phone connected and unlocked…");const r=await api("/api/android/media-backup",{method:"POST",body:JSON.stringify({serial,destination})});output("repairOutput",r);}catch(e){output("repairOutput","Media export failed: "+e.message);}};
$("propsBtn").onclick=()=>selectedAction("/api/android/properties");$("diagBtn").onclick=()=>selectedAction("/api/android/diagnostics");$("classifyBtn").onclick=()=>selectedAction("/api/android/classify");
$("rebootBtn").onclick=async()=>{const serial=$("repairDevice").value,target=$("rebootTarget").value;if(!serial){output("repairOutput","Select an authorised Android device first.");return;}try{output("repairOutput","Verifying device and preparing approval…");const preview=await api("/api/operations/preview",{method:"POST",body:JSON.stringify({serial,operation:"reboot",target})});const p=preview.device||{};const summary="DEVICE-CHANGE APPROVAL\\nDevice: "+(p["ro.product.manufacturer"]||"Unknown")+" "+(p["ro.product.model"]||"Unknown")+"\\nSerial: "+serial+"\\nAction: Reboot to "+target+"\\n\\nThis approval applies only to this device and this action, expires in 2 minutes and can be used once. Continue?";if(!window.confirm(summary)){output("repairOutput","Operation cancelled. No device command was sent.");return;}const approved=await api("/api/operations/approve",{method:"POST",body:JSON.stringify({challenge_id:preview.challenge_id})});output("repairOutput","Approval recorded. Sending the approved reboot…");const result=await api("/api/android/reboot",{method:"POST",body:JSON.stringify({serial,target,approval_token:approved.approval_token})});output("repairOutput",result);}catch(e){output("repairOutput","Reboot not performed: "+e.message);}};
$("flashCapabilitiesBtn").onclick=async()=>{
 try {
  const r=await api("/api/firmware/flash/capabilities");
  const lines=["FIRMWARE FLASHING ENGINE READINESS","Customer approval required: "+r.approval_required,"Global write enabled: "+r.global_write_enabled,"Execution policy: "+r.execution_policy,"",...Object.entries(r.engines||{}).flatMap(([id,e])=>[id.toUpperCase(),e.label+" · "+e.status,"Write enabled: "+e.write_enabled,e.reason||"",...(e.supported_models||[]).map(x=>"Supported model: "+x),""]), "REQUIRED SAFETY GATES",...(r.required_gates||[]).map((x,i)=>(i+1)+". "+x)];
  output("repairOutput",lines.join("\n"));
  $("flashExecuteBtn").disabled=true;
  $("flashExecuteBtn").textContent="Flash device (locked)";
 } catch(e){output("repairOutput","Could not read flash readiness: "+e.message);}
};
$("flashPlanBtn").onclick=async()=>{
 const serial=$("repairDevice").value;
 const firmware_path=$("firmwarePath").value.trim();
 const engine_id=$("flashEngine").value;
 if(!serial){output("repairOutput","Select a device before preparing a flash plan.");return;}
 if(!firmware_path){output("repairOutput","Enter the firmware ZIP path and inspect it before preparing a plan.");return;}
 try {
  output("repairOutput","Checking engine, device and firmware gates. No write command will be sent.");
  const r=await api("/api/firmware/flash/plan",{method:"POST",body:JSON.stringify({serial,firmware_path,engine_id})});
  const lines=["FLASH PLAN REVIEW","Flash enabled: "+r.flash_enabled,"Customer approval required: "+r.approval_required,"Device serial: "+r.serial,"Engine: "+(r.engine?.label||engine_id),"Engine status: "+(r.engine?.status||"unknown"),"","FIRMWARE",JSON.stringify(r.firmware||{},null,2),"","PARTITION PLAN",JSON.stringify(r.partition_plan||[],null,2),"","BLOCKERS",...(r.blockers||[]).map(x=>"• "+x),"",r.message||""];
  output("repairOutput",lines.join("\n"));
  $("flashExecuteBtn").disabled=true;
  $("flashExecuteBtn").textContent="Flash device (locked)";
 } catch(e){output("repairOutput","Flash plan rejected: "+e.message);}
};
$("flashExecuteBtn").disabled=true;
$("flashExecuteBtn").title="Locked until a validated manufacturer engine and approved exact flash plan are available.";
$("firmwareBtn").onclick=async()=>{try{const path=$("firmwarePath").value.trim();if(!path)throw new Error("Enter the full path to a firmware ZIP file.");output("repairOutput",await api("/api/firmware/inspect",{method:"POST",body:JSON.stringify({path})}));}catch(e){output("repairOutput",e.message);}};
$("factoryResetPrepareBtn").onclick=async()=>{const serial=$("repairDevice").value;if(!serial){output("repairOutput","Select an authorised Android device first.");return;}if(!$("resetBackupAck").checked){output("repairOutput","Confirm that important data is backed up before proceeding.");return;}const confirmation=window.prompt('Type PREPARE RECOVERY to confirm:');if(confirmation===null)return;try{output("repairOutput","Verifying device and preparing approval…");const preview=await api("/api/operations/preview",{method:"POST",body:JSON.stringify({serial,operation:"factory_reset_prepare",backup_confirmed:true,confirmation})});const p=preview.device||{};const summary="RECOVERY PREPARATION APPROVAL\\nDevice: "+(p["ro.product.manufacturer"]||"Unknown")+" "+(p["ro.product.model"]||"Unknown")+"\\nSerial: "+serial+"\\nAction: Reboot into Recovery Mode\\nBackup confirmed: Yes\\n\\nVendora will NOT erase data. This approval is single-use and expires in 2 minutes. Continue?";if(!window.confirm(summary)){output("repairOutput","Operation cancelled. No device command was sent.");return;}const approved=await api("/api/operations/approve",{method:"POST",body:JSON.stringify({challenge_id:preview.challenge_id})});const result=await api("/api/android/factory-reset/prepare",{method:"POST",body:JSON.stringify({serial,backup_confirmed:true,confirmation,approval_token:approved.approval_token})});output("repairOutput",result);}catch(e){output("repairOutput","Recovery preparation not performed: "+e.message);}};
$("bootAssessBtn").onclick=async()=>{
 const serial=$("repairDevice").value||"";
 const symptom=$("bootSymptom").value;
 output("repairOutput","Running read-only boot assessment…");
 try {
  const r=await api("/api/boot-repair/assess",{method:"POST",body:JSON.stringify({serial,symptom})});
  const lines=["BOOT REPAIR ASSESSMENT","Mode: "+r.device_mode,"Read-only: "+r.read_only,"","ASSESSMENT",r.assessment,"","DEVICE IDENTITY",JSON.stringify(r.identity||{},null,2),"","DIAGNOSTICS",JSON.stringify(r.diagnostics||{},null,2),"","NEXT SAFE STEPS",...(r.next_steps||[]).map((x,i)=>(i+1)+". "+x),"","LIMITATIONS",...(r.limitations||[]).map(x=>"• "+x)];
  output("repairOutput",lines.join("\\n"));
 } catch(e) { output("repairOutput","Boot assessment failed: "+e.message); }
};
$("repairPrepareBtn").onclick=async()=>{
 const serial=$("repairDevice").value||"";
 const symptom=$("bootSymptom")?.value||"stuck_logo";
 const firmware_path=$("repairFirmwarePath").value.trim();
 const programmer_path=$("repairProgrammerPath").value.trim();
 output("repairOutput","Preparing automatic repair plan… This is read-only; no phone commands will be written.");
 try {
  const r=await api("/api/repair/prepare",{method:"POST",body:JSON.stringify({serial,symptom,firmware_path,programmer_path})});
  const lines=["AUTOMATIC REPAIR PREPARATION","Read-only: "+r.read_only,"Execution enabled: "+r.execution_enabled,"Repair ready: "+r.repair_ready,"","DEVICE","Manufacturer: "+r.device.manufacturer,"Model: "+r.device.model,"Product / board: "+r.device.product_or_board,"Chipset: "+r.device.chipset,"Protocol: "+r.device.protocol_family,"Connection: "+r.device_mode,"","PROTOCOL ENGINE",r.protocol_engine.name+" · "+r.protocol_engine.status,...(r.protocol_engine.requirements||[]).map(x=>"Required: "+x),"","DRIVER CHECK",JSON.stringify(r.driver_check,null,2),"","FIRMWARE CHECK",JSON.stringify(r.firmware_check,null,2),"","PROGRAMMER CHECK",JSON.stringify(r.programmer_check,null,2),"","BLOCKERS",...(r.blockers||[]).map(x=>"• "+x),"","RECOMMENDED AUTOMATION PIPELINE",...(r.recommended_pipeline||[]).map((x,i)=>(i+1)+". "+x),"","SAFETY LIMITS",...(r.limitations||[]).map(x=>"• "+x)];
  output("repairOutput",lines.join("\n"));
 } catch(e) { output("repairOutput","Repair preparation failed: "+e.message); }
};
$("iphoneBtn").onclick=async()=>{try{const r=await api("/api/devices/iphone");output("otherDevicesOutput",r);}catch(e){output("otherDevicesOutput",e.message);}};
document.querySelectorAll(".recovery-card").forEach(b=>b.onclick=async()=>{const platform=b.dataset.platform;$("recoveryState").textContent=platform==="ios"?"APPLE RECOVERY":"ANDROID RECOVERY";try{const r=await api("/api/recovery/"+platform);output("unlockOutput",r.steps.map((x,i)=>(i+1)+". "+x).join("\n"));}catch(e){output("unlockOutput",e.message);}});

document.querySelectorAll("[data-workflow]").forEach(b=>b.onclick=async()=>{
 const workflow=b.dataset.workflow;
 const labels={frp_recovery:"FRP OWNER RECOVERY",screen_lock:"SCREEN-LOCK RECOVERY",carrier_unlock:"SIM / NETWORK UNLOCK",bootloader_unlock:"OFFICIAL BOOTLOADER UNLOCK"};
 $("workflowState").textContent=labels[workflow]||"RECOVERY WORKFLOW";
 output("workflowOutput","Loading official owner-recovery guidance…");
 try {
  const r=await api("/api/recovery/workflows/"+workflow);
  const lines=[r.title||labels[workflow]||"RECOVERY WORKFLOW","STATUS: "+(r.status||"GUIDANCE_ONLY"),"",...(r.steps||[]).map((x,i)=>(i+1)+". "+x),"","IMPORTANT LIMITS",...(r.limitations||[]).map(x=>"• "+x)];
  output("workflowOutput",lines.join("\n"));
 } catch(e) { output("workflowOutput","Could not load this workflow: "+e.message); }
});

health();readiness();setInterval(health,8000);