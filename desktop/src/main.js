const API="http://127.0.0.1:8765";const $=id=>document.getElementById(id);let devices=[];
async function api(path,options={}){const r=await fetch(API+path,{headers:{"Content-Type":"application/json"},...options});const d=await r.json().catch(()=>({detail:"Invalid API response"}));if(!r.ok)throw new Error(d.detail||"HTTP "+r.status);return d;}
function output(id,v){$(id).textContent=typeof v==="string"?v:JSON.stringify(v,null,2);}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
async function health(){try{const h=await api("/api/health");$("statusText").textContent="Local service connected";$("sideStatus").textContent="Connected";$("statusDot").style.background="#31d68a";$("toolsState").textContent=(h.tools.adb?"ADB":"—")+" / "+(h.tools.fastboot?"Fastboot":"—");}catch(e){$("statusText").textContent="Backend unavailable";$("sideStatus").textContent="Unavailable";$("statusDot").style.background="#e6a23c";$("toolsState").textContent="Offline";}}
async function readiness(){try{output("readinessOutput",await api("/api/readiness"));}catch(e){output("readinessOutput",e.message);}}
async function scan(){
  $("deviceList").textContent="Scanning Android and USB devices…";
  try{
    const [d,usb]=await Promise.all([
      api("/api/devices/android"),
      api("/api/devices/usb").catch(error=>({supported:false,devices:[],message:error.message}))
    ]);
    devices=[...(d.adb||[]).map(x=>({...x,mode:"ADB"})),...(d.fastboot||[]).map(x=>({...x,mode:"Fastboot"}))];
    $("adbCount").textContent=(d.adb||[]).length;
    $("fbCount").textContent=(d.fastboot||[]).length;
    const androidRows=devices.map(x=>{
      const hint=x.state==="unauthorized"?" — unlock phone and approve USB debugging prompt":x.state==="offline"?" — reconnect cable and restart ADB":"";
      return '<div class="device"><b>'+esc(x.serial)+'</b><span>'+esc(x.mode)+" · "+esc(x.state)+esc(hint)+'</span></div>';
    });
    const usbRows=(usb.devices||[]).map(x=>{
      const name=x.FriendlyName||x.Name||"USB device";
      const status=x.Status||"Unknown status";
      return '<div class="device"><b>'+esc(name)+'</b><span>Windows USB · '+esc(status)+'</span></div>';
    });
    let message="";
    if(!devices.length){
      message='<p>No ADB/Fastboot phone session found.</p><p><b>Next checks:</b> unlock Android, choose File Transfer (MTP), enable Developer options → USB debugging, reconnect and approve the computer prompt. If the phone appears in Windows USB below but not ADB, its USB driver or debugging authorisation may be missing.</p>';
      if(d.warnings&&d.warnings.length) message+='<p>ADB/Fastboot warning: '+esc(d.warnings.join("; "))+'</p>';
    }
    const usbHeader=usb.supported?'<p><b>Windows USB devices currently present: '+((usb.devices||[]).length)+'</b></p>':'<p>Windows USB inventory unavailable: '+esc(usb.message||"")+'</p>';
    $("deviceList").innerHTML=androidRows.join("")+message+usbHeader+usbRows.slice(0,12).join("")+(usbRows.length>12?'<p>Showing first 12 USB entries.</p>':"");
    $("repairDevice").innerHTML=devices.filter(x=>x.mode==="ADB"&&x.state==="device").map(x=>'<option value="'+esc(x.serial)+'">'+esc(x.serial)+'</option>').join("")||'<option value="">No authorised ADB device</option>';
  }catch(e){$("deviceList").textContent=e.message;}
}
document.querySelectorAll(".nav").forEach(b=>b.onclick=()=>{document.querySelectorAll(".nav").forEach(x=>x.classList.toggle("active",x===b));document.querySelectorAll(".page").forEach(x=>x.classList.toggle("active",x.id===b.dataset.tab));$("pageTitle").textContent=b.textContent.trim();});
$("scanBtn").onclick=$("refreshBtn").onclick=scan;$("readinessBtn").onclick=readiness;
for(const [id,path] of [["propsBtn","/api/android/properties"],["diagBtn","/api/android/diagnostics"],["classifyBtn","/api/android/classify"]])$(id).onclick=async()=>{try{if(!$("repairDevice").value)throw new Error("Connect and authorise an ADB device first.");output("repairOutput",await api(path,{method:"POST",body:JSON.stringify({serial:$("repairDevice").value})}));}catch(e){output("repairOutput",e.message);}};
$("rebootBtn").onclick=async()=>{const serial=$("repairDevice").value,target=$("rebootTarget").value;if(!serial){output("repairOutput","Connect and authorise an ADB device first.");return;}if(!window.confirm("Send the selected reboot command to "+serial+"? The phone will restart."))return;try{output("repairOutput",await api("/api/android/reboot",{method:"POST",body:JSON.stringify({serial,target})}));}catch(e){output("repairOutput",e.message);}};
$("firmwareBtn").onclick=async()=>{try{output("firmwareOutput",await api("/api/firmware/inspect",{method:"POST",body:JSON.stringify({path:$("firmwarePath").value})}));}catch(e){output("firmwareOutput",e.message);}};
$("iphoneBtn").onclick=async()=>{try{output("otherDevicesOutput",await api("/api/devices/iphone"));}catch(e){output("otherDevicesOutput",e.message);}};
$("usbBtn").onclick=async()=>{try{output("otherDevicesOutput",await api("/api/devices/usb"));}catch(e){output("otherDevicesOutput",e.message);}};
document.querySelectorAll(".choice").forEach(b=>b.onclick=async()=>{try{const r=await api("/api/recovery/"+b.dataset.platform);output("unlockOutput",r.steps.map((x,i)=>(i+1)+". "+x).join("\n"));}catch(e){output("unlockOutput",e.message);}});
health();readiness();setInterval(health,5000);