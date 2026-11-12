'use strict';
const $=id=>document.getElementById(id);
let csrf='',proof='',epoch=0,logged=false,owned=false,caps={},statusBusy=false,holdBusy=false;
let driving=null,driveBusy=false,braking=false,driveTimer,stopping=false,cameraActive=false,frameBusy=false,frameUrl=null;
let audioContext=null,audioCursor=0,audioBusy=false,audioNext=0,micActive=false,micWaitUntil=0;
let headUntil=0,headBusy=false;
const names={face:'چهرهٔ نمایشگر',drive:'حرکت دستی',brake:'توقف جهت',stop:'توقف و آزادکردن کنترل',head_step:'حرکت سر',head_reset:'سر روبه‌رو',camera_on:'روشن‌کردن دوربین',camera_off:'خاموش‌کردن دوربین',mic_on:'روشن‌کردن میکروفون',mic_off:'خاموش‌کردن میکروفون'};
const resultNames={queued:'در صف',submitted:'درخواست ارسال شد',rejected:'اجرا نشد',failed:'ناموفق',expired:'منقضی',cancelled:'لغو شده',unknown:'تأیید دریافت نشد'};
let toastTimer;
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4000);}
async function api(path,body,timeout=2000){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
 try{
  const response=await fetch(path,{method:body===undefined?'GET':'POST',cache:'no-store',credentials:'same-origin',
   headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'X-Control-Token':proof},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});
  const data=await response.json();if(!response.ok){if(response.status===401 && path!=='/api/login')loginScreen();throw new Error(data.error || 'ارتباط برقرار نشد.');}return data;
 }finally{clearTimeout(timer);}
}
async function media(path){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),1200);
 try{const response=await fetch(path,{headers:{'X-Control-Token':proof},cache:'no-store',signal:controller.signal});
  if(!response.ok)throw Error('no fresh media');return {bytes:await response.arrayBuffer(),sequence:Number(response.headers.get('X-Audio-Sequence'))};
 }finally{clearTimeout(timer);}
}
function clearDrive(){driving=null;clearInterval(driveTimer);document.querySelectorAll('.direction').forEach(b=>b.classList.remove('active'));}
function stopAudio(){const previous=audioContext;audioContext=null;audioCursor=0;audioNext=0;micWaitUntil=0;if(previous)previous.close().catch(()=>{});$('mic-status').textContent='پخش صدای محیط خاموش است.';}
function hideFrame(){if(frameUrl)URL.revokeObjectURL(frameUrl);frameUrl=null;$('camera-image').hidden=true;$('camera-image').removeAttribute('src');$('camera-empty').hidden=false;}
function releaseLocal(){talkResumeListening=false;talkEnd();owned=false;proof='';clearDrive();stopAudio();hideFrame();controls();}
function loginScreen(){window.projectReset?.();logged=false;csrf='';releaseLocal();$('dashboard').hidden=true;$('login-screen').hidden=false;}
function dashboard(token){csrf=token;logged=true;$('password').value='';$('login-screen').hidden=true;$('dashboard').hidden=false;refresh();}
function controls(){
 window.projectControls?.();
 window.faceControls?.();
 talkControls();
 document.querySelectorAll('[data-direction]').forEach(b=>b.disabled=!(owned && caps.sdk && caps.drive && !braking));
 document.querySelectorAll('[data-head]').forEach(b=>b.disabled=!(!caps.head_arm_rest && owned && caps.sdk && caps.head && !headBusy && performance.now()>=headUntil));
 $('control-badge').textContent=owned?'در اختیار شما':'غیرفعال';$('control-badge').classList.toggle('online',owned);
 $('acquire-button').textContent=owned?'آزادکردن کنترل':'فعال‌کردن کنترل';$('acquire-button').disabled=!logged || !caps.sdk || stopping;
 $('camera-button').disabled=!owned || !caps.camera;$('camera-button').textContent=cameraActive?'خاموش‌کردن دوربین':'روشن‌کردن دوربین';
 $('mic-button').disabled=!owned || !caps.microphone;$('mic-button').textContent=micActive?'خاموش‌کردن میکروفون':'روشن‌کردن میکروفون';
 $('drive-note').textContent=caps.drive?'فلش را نگه دار؛ با رهاکردن، درخواست توقف ارسال می‌شود.':'در انتظار اتصال SDK حرکت ربات.';
 $('stop-label').textContent='توقف و آزادکردن کنترل';$('stop-note').textContent='ارسال فرمان، تأیید توقف فیزیکی نیست.';
}
async function refresh(){
 if(!logged || statusBusy)return;statusBusy=true;const initialProof=proof;
 try{
  const state=await api('/api/status');caps=state.capabilities || {};cameraActive=!!caps.camera_active;micActive=!!caps.mic_active;
  if(initialProof===proof){if(!state.control_owned && owned)releaseLocal();else if(state.control_owned){owned=true;epoch=Math.max(epoch,state.drive_epoch || 0);}}
  $('online-badge').classList.toggle('online',state.online);$('online-badge').querySelector('span').textContent=state.online?'ربات متصل است':'ربات آفلاین';
  $('connection-description').textContent=state.online?'اپ مستقل ربات متصل است؛ اختیار کنترل را فعال کن.':'اپ Timo Remote Robot را روی ربات باز و متصل کن.';
  $('robot-state').textContent=state.online?'متصل':'قطع';$('sdk-state').textContent=caps.sdk?'متصل':'قطع';$('owner-state').textContent=owned?'در اختیار شما':state.control_busy?'دستگاه دیگر':'آزاد';
  $('camera-state').textContent=state.camera_live?'تصویر تازه':cameraActive?'منتظر تصویر':'خاموش';$('live-label').textContent=state.camera_live?'● تصویر تازه':'تصویر دریافت نشده';
  $('camera-note').textContent=[state.media_notice,state.camera_error,state.mic_error].filter(Boolean).join(' | ') || 'کنترل را فعال کن و دوربین را روشن کن.';
  $('head-note').textContent=state.head_notice || 'کنترل سر هنوز شناسایی نشده است؛ اتصال ربات را در ویندوز بزن.';
  $('mic-status').textContent=talkHeld?'هنگام صحبت، صدای برگشتی موقتاً قطع است.':micActive?(audioContext?'در حال دریافت صدای محیط ربات…':'میکروفون روشن است؛ برای شنیدن دوباره آن را خاموش و روشن کن.'):'میکروفون خاموش است.';
  $('diagnostics-text').textContent=(state.diagnostics || []).join('\n');
  $('events').replaceChildren();for(const item of state.results.slice(-8).reverse()){
   const li=document.createElement('li'),a=document.createElement('div'),b=document.createElement('strong'),c=document.createElement('small'),d=document.createElement('span');
   a.className='event-info';b.textContent=names[item.kind] || item.kind;c.textContent=item.detail;d.className='event-tag';d.textContent=resultNames[item.status] || item.status;a.append(b,c);li.append(a,d);$('events').append(li);
  }
  if(!state.camera_live)hideFrame();if(micActive)micWaitUntil=0;
  if(!micActive && audioContext && performance.now()>micWaitUntil)stopAudio();controls();
 }catch(e){caps={};releaseLocal();$('online-badge').querySelector('span').textContent='ارتباط پنل قطع است';}
 finally{statusBusy=false;}
}
async function command(kind,args={}){return api('/api/command',{kind,args});}
async function stopAll(silent=false){
 if(stopping)return;stopping=true;releaseLocal();
 try{if(logged)await command('stop');if(!silent)toast('درخواست توقف ارسال شد.');}catch(e){if(!silent)toast(e.message);}finally{stopping=false;controls();}
}
async function brake(){
 if(!driving || braking)return;clearDrive();braking=true;controls();
 try{const result=await command('brake');epoch=result.drive_epoch;}catch(e){await stopAll(true);}finally{braking=false;controls();}
}
function startDrive(direction,button){
 if(!owned || !caps.drive || driving || braking || document.hidden)return;driving=direction;button.classList.add('active');
 const tick=async()=>{if(!driving || driveBusy)return;driveBusy=true;const directionAtStart=driving;
  try{await command('drive',{direction:directionAtStart,drive_epoch:epoch});}catch(e){if(driving===directionAtStart)await stopAll(true);}finally{driveBusy=false;}};
 tick();driveTimer=setInterval(tick,200);
}
document.querySelectorAll('[data-direction]').forEach(button=>{
 button.addEventListener('pointerdown',event=>{event.preventDefault();if(button.disabled)return;button.setPointerCapture(event.pointerId);startDrive(button.dataset.direction,button);});
 ['pointerup','pointercancel','lostpointercapture'].forEach(type=>button.addEventListener(type,brake));
});
const keyMap={ArrowUp:'forward',ArrowDown:'backward',ArrowLeft:'left',ArrowRight:'right'};
document.addEventListener('keydown',event=>{if(!logged || /INPUT|TEXTAREA/.test(event.target.tagName))return;
 if(event.code==='Space'){event.preventDefault();stopAll();return;}if(keyMap[event.key]){event.preventDefault();if(!event.repeat)startDrive(keyMap[event.key],document.querySelector('[data-direction="'+keyMap[event.key]+'"]'));}});
document.addEventListener('keyup',event=>{if(keyMap[event.key] && driving){event.preventDefault();brake();}});
async function hold(){if(!owned || !logged || document.hidden || holdBusy)return;holdBusy=true;const initialProof=proof;
 try{await api('/api/control/hold',{},1000);}catch(e){if(initialProof===proof)await stopAll(true);}finally{holdBusy=false;}}
async function frame(){if(!owned || !cameraActive || frameBusy || document.hidden)return;frameBusy=true;const initialProof=proof;
 try{const result=await media('/api/frame');if(proof!==initialProof || !owned)return;
  const previous=frameUrl;frameUrl=URL.createObjectURL(new Blob([result.bytes],{type:'image/jpeg'}));$('camera-image').src=frameUrl;$('camera-image').hidden=false;$('camera-empty').hidden=true;if(previous)URL.revokeObjectURL(previous);
 }catch(e){hideFrame();}finally{frameBusy=false;}}
async function audio(){if(talkHeld || !owned || !audioContext || audioBusy || document.hidden)return;audioBusy=true;const context=audioContext,initialProof=proof;
 try{const result=await media('/api/audio?after='+audioCursor);if(context!==audioContext || initialProof!==proof || !owned)return;
  audioCursor=result.sequence;const pcm=new DataView(result.bytes),buffer=context.createBuffer(1,result.bytes.byteLength/2,16000),channel=buffer.getChannelData(0);
  for(let i=0;i<channel.length;i++)channel[i]=pcm.getInt16(i*2,true)/32768;
  if(audioNext<context.currentTime || audioNext>context.currentTime+0.35)audioNext=context.currentTime+0.02;
  const source=context.createBufferSource();source.buffer=buffer;source.connect(context.destination);source.start(audioNext);audioNext+=buffer.duration;
 }catch(e){}finally{audioBusy=false;}}
let talkHeld=false,talkGeneration=0,talkStream='',talkSequence=0,talkBusy=false;
let talkMedia=null,talkContext=null,talkNode=null,talkResumeListening=false;
function talkControls(){
 $('talk-button').disabled=!(owned && caps.speaker);
 $('talk-button').textContent=talkHeld?'● در حال ارسال صدا — رها کن تا قطع شود':'🎙 نگه دار و صحبت کن';
}
function stopTalkOnServer(id,token){
 if(!id)return;
 fetch('/api/talk/stop',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'X-Control-Token':token},body:JSON.stringify({stream_id:id}),keepalive:true}).catch(()=>{});
}
function talkEnd(){
 // شمارهٔ نسل، پاسخ دیرهنگام میکروفون را بعد از رهاکردن دکمه باطل می‌کند.
 const id=talkStream,token=proof;talkHeld=false;talkStream='';talkGeneration++;
 try{window.TimoTalk?.stop();}catch(e){}
 if(talkMedia)talkMedia.getTracks().forEach(t=>t.stop());talkMedia=null;
 if(talkNode){talkNode.disconnect();talkNode=null;}
 if(talkContext){talkContext.close().catch(()=>{});talkContext=null;}
 stopTalkOnServer(id,token);$('talk-status').textContent='ارسال صدا خاموش است.';
 if(talkResumeListening && owned && micActive){
  talkResumeListening=false;
  try{const C=window.AudioContext || window.webkitAudioContext;audioContext=new C();audioContext.resume().catch(()=>{});audioCursor=0;audioNext=0;}catch(e){}
 }
 talkControls();
}
async function talkChunk(bytes){
 if(!talkHeld || !talkStream || talkBusy || !owned || document.hidden)return;
 talkBusy=true;const id=talkStream,token=proof,generation=talkGeneration,controller=new AbortController();const timer=setTimeout(()=>controller.abort(),1000);
 try{
  const r=await fetch('/api/talk/audio',{method:'POST',cache:'no-store',credentials:'same-origin',headers:{'Content-Type':'application/octet-stream','X-CSRF-Token':csrf,'X-Control-Token':token,'X-Talk-Stream':id,'X-Audio-Sequence':String(++talkSequence)},body:bytes,signal:controller.signal});
  if(!r.ok)throw Error((await r.json()).error || 'ارسال صدا انجام نشد.');
  if(generation===talkGeneration)$('talk-status').textContent='صدای میکروفون در حال ارسال است؛ برای پایان رها کن.';
 }catch(e){if(generation===talkGeneration){talkEnd();$('talk-status').textContent='ارسال صدا قطع شد: '+e.message;}}
 finally{clearTimeout(timer);talkBusy=false;}
}
window.timoTalkPCM=(id,base64)=>{
 if(!talkHeld || id!==talkStream || talkBusy || typeof base64!=='string' || base64.length>9000)return;
 try{const b=atob(base64),data=new Uint8Array(b.length);for(let i=0;i<b.length;i++)data[i]=b.charCodeAt(i);talkChunk(data.buffer);}catch(e){}
};
window.timoTalkError=(id,error)=>{if(id===talkStream){talkEnd();$('talk-status').textContent=String(error).slice(0,250);}};
async function talkBegin(){
 if(talkHeld || !owned || !caps.speaker || document.hidden)return;
 talkHeld=true;talkGeneration++;const generation=talkGeneration,token=proof;
 talkResumeListening=!!audioContext;if(audioContext)stopAudio();talkControls();$('talk-status').textContent='در حال آماده‌کردن میکروفون…';
 try{
  const data=await api('/api/talk/start',{});const id=data.stream_id;
  if(!talkHeld || generation!==talkGeneration || token!==proof){stopTalkOnServer(id,token);return;}
  talkStream=id;talkSequence=0;
  if(window.TimoTalk){window.TimoTalk.start(id);}
  else{
   if(!navigator.mediaDevices?.getUserMedia)throw Error('برای میکروفون از اپ موبایل جدید، ریموت ویندوز یا صفحهٔ HTTPS استفاده کن.');
   const media=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
   if(!talkHeld || generation!==talkGeneration){media.getTracks().forEach(t=>t.stop());return;}
   talkMedia=media;media.getTracks().forEach(track=>track.addEventListener?.('ended',()=>{if(generation===talkGeneration){talkEnd();$('talk-status').textContent='میکروفون این دستگاه قطع شد.';}}));const C=window.AudioContext || window.webkitAudioContext;const context=new C();talkContext=context;
   await context.resume();await context.audioWorklet.addModule('/talk-worklet.js');
   if(!talkHeld || generation!==talkGeneration){context.close().catch(()=>{});return;}
   talkNode=new AudioWorkletNode(context,'timo-talk');talkNode.port.onmessage=event=>{if(generation===talkGeneration)talkChunk(event.data);};
   const source=context.createMediaStreamSource(media),mute=context.createGain();mute.gain.value=0;
   source.connect(talkNode);talkNode.connect(mute);mute.connect(context.destination);
  }
  if(generation===talkGeneration)$('talk-status').textContent='صحبت کن؛ برای پایان دکمه را رها کن.';
 }catch(e){if(generation===talkGeneration){talkEnd();$('talk-status').textContent=e.message;}}
}
$('talk-button').addEventListener('pointerdown',event=>{event.preventDefault();if($('talk-button').disabled)return;$('talk-button').setPointerCapture(event.pointerId);talkBegin();});
['pointerup','pointercancel','lostpointercapture'].forEach(type=>$('talk-button').addEventListener(type,()=>talkEnd()));
window.addEventListener('blur',()=>{if(talkHeld)talkEnd();});

$('login-form').addEventListener('submit',async event=>{event.preventDefault();$('login-button').disabled=true;try{dashboard((await api('/api/login',{password:$('password').value})).csrf);}catch(e){$('login-error').textContent=e.message;}finally{$('login-button').disabled=false;}});
$('acquire-button').addEventListener('click',async()=>{if(owned){await stopAll();return;}try{const data=await api('/api/control/acquire',{});proof=data.control_token;epoch=data.drive_epoch || 0;owned=true;controls();refresh();}catch(e){toast(e.message);}});
$('stop-button').addEventListener('click',()=>stopAll());
document.querySelectorAll('[data-head]').forEach(button=>button.addEventListener('click',async()=>{
 if(!owned || !caps.head || headBusy || performance.now()<headUntil || caps.head_arm_rest)return;
 headBusy=true;headUntil=performance.now()+1200;controls();
 try{const args=button.dataset.head==='center'?{}:{direction:button.dataset.head};await command(button.dataset.head==='center'?'head_reset':'head_step',args);}
 catch(e){toast(e.message);}finally{headBusy=false;controls();setTimeout(controls,1250);}
}));
$('camera-button').addEventListener('click',()=>command(cameraActive?'camera_off':'camera_on').catch(e=>toast(e.message)));
$('mic-button').addEventListener('click',async()=>{
 try{if(micActive){stopAudio();await command('mic_off');}
 else{const Context=window.AudioContext || window.webkitAudioContext;if(!Context)throw Error('پخش صوت در این مرورگر پشتیبانی نمی‌شود.');
  audioContext=new Context();await audioContext.resume();audioCursor=0;micWaitUntil=performance.now()+4000;await command('mic_on');}}
 catch(e){stopAudio();toast(e.message);}
});
$('logout-button').addEventListener('click',async()=>{await stopAll(true);try{await api('/api/logout',{});}catch(e){}loginScreen();});
$('copy-diagnostics').addEventListener('click',()=>navigator.clipboard?.writeText($('diagnostics-text').textContent).catch(()=>{}));
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopAll(true);else refresh();});
window.addEventListener('pagehide',()=>stopAll(true));window.addEventListener('offline',()=>stopAll(true));window.addEventListener('blur',()=>{if(driving)stopAll(true);});
setInterval(refresh,650);setInterval(hold,400);setInterval(frame,250);setInterval(audio,80);
api('/api/session').then(result=>{if(result.authenticated)dashboard(result.csrf);}).catch(()=>{});
