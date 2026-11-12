'use strict';
(() => {
 let view={},refreshing=false,chatBusy=false,sayBusy=false,navBusy=false,newSession=true;
 const id=()=>crypto.randomUUID?.() || ('req_'+Date.now()+'_'+Math.random().toString(36).slice(2));
 const note=text=>$('project-status').textContent=text;
 window.projectControls=()=>{
  $('project-send').disabled=!(logged && owned && !chatBusy);
  $('project-say').disabled=!(logged && owned && caps.speech && !sayBusy);
  $('project-room-go').disabled=!(logged && owned && view.navigation?.ready && !view.navigation?.busy && !navBusy && !view.error && $('project-room').value);
 };
 window.projectReset=()=>{view={};newSession=true;$('project-chat-log').replaceChildren();$('project-room').replaceChildren();window.projectControls();};
 function append(label,text){
  const row=document.createElement('p'),strong=document.createElement('strong'),body=document.createElement('span');
  strong.textContent=label+'\n';body.textContent=text;row.append(strong,body);$('project-chat-log').append(row);row.scrollIntoView?.({block:'nearest'});
 }
 async function refreshProject(){
  if(!logged || refreshing || document.hidden)return;refreshing=true;
  try{
   view=await api('/api/project/state',undefined,5000);note(view.error || 'اتصال به پروژه برقرار است؛ کلید مدیر در سرویس ویندوز نگه‌داری می‌شود.');
   $('project-map').textContent='نقشهٔ مشترک: '+(view.map_name || 'تنظیم نشده');
   const previous=$('project-room').value;$('project-room').replaceChildren();
   for(const r of view.rooms || []){
    const option=document.createElement('option');option.value=String(r.id);option.textContent=r.name+(r.available?'':' — نقشه نامطابق');option.disabled=!r.available;$('project-room').append(option);
   }
   if([...$('project-room').options].some(o=>o.value===previous))$('project-room').value=previous;
   $('project-nav-status').textContent=view.navigation?.message || 'منتظر وضعیت SDK';
   if(view.speech?.message && !sayBusy)$('project-speech-status').textContent=view.speech.message;
  }catch(e){view={};note(e.message);}
  finally{refreshing=false;window.projectControls();}
 }
 async function speak(text){
  if(sayBusy || !owned || !text.trim())return;sayBusy=true;const before=proof;window.projectControls();
  $('project-speech-status').textContent='در حال تولید صدای پاسخ با پروژه…';
  try{const r=await api('/api/project/say',{request_id:id(),text},50000);if(before===proof)$('project-speech-status').textContent=r.error || 'درخواست پخش به ربات ارسال شد؛ منتظر وضعیت پخش.';}
  catch(e){$('project-speech-status').textContent=e.message;}
  finally{sayBusy=false;window.projectControls();}
 }
 $('project-chat-form').addEventListener('submit',async e=>{
  e.preventDefault();const text=$('project-text').value.trim();if(!owned || !text || chatBusy)return;
  const before=proof;chatBusy=true;append('شما',text);$('project-text').value='';note('در حال دریافت پاسخ…');window.projectControls();
  try{
   const r=await api('/api/project/chat',{request_id:id(),text,new_session:newSession},50000);
   if(!logged || before!==proof)return;
   if(r.error)throw Error(r.error);newSession=false;append('تیمو',r.response || '');if(r.notice)append('وضعیت',r.notice);note('پاسخ دریافت شد.');
   if(r.stopped)releaseLocal();else if($('project-auto-speech').checked && r.response)speak(r.response);
   refreshProject();
  }catch(e){if(logged)append('خطا',e.message);}
  finally{chatBusy=false;window.projectControls();}
 });
 $('project-say').addEventListener('click',()=>speak($('project-text').value));
 $('project-new-chat').addEventListener('click',()=>{if(!chatBusy){newSession=true;$('project-chat-log').replaceChildren();}});
 $('project-room').addEventListener('change',window.projectControls);
 $('project-refresh').addEventListener('click',refreshProject);
 $('project-room-go').addEventListener('click',async()=>{
  if(navBusy || $('project-room-go').disabled)return;navBusy=true;window.projectControls();
  try{const r=await api('/api/project/navigate',{request_id:id(),room_id:Number($('project-room').value)},5000);$('project-nav-status').textContent=r.error || 'درخواست مقصد ثبت شد؛ منتظر تأیید SDK.';await refreshProject();}
  catch(e){$('project-nav-status').textContent=e.message;}
  finally{navBusy=false;window.projectControls();}
 });
 $('project-nav-stop').addEventListener('click',()=>stopAll());
 setInterval(refreshProject,1800);window.projectControls();
})();
