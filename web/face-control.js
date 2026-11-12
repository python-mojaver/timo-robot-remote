'use strict';
(() => {
 let busy=false;
 const names={normal:'معمولی',happy:'شاد',sad:'غمگین',angry:'عصبانی',surprised:'متعجب'};
 const buttons=[...document.querySelectorAll('[data-face]')];
 window.faceControls=()=>buttons.forEach(b=>b.disabled=!(logged && owned && caps.face && !busy));
 buttons.forEach(button=>button.addEventListener('click',async()=>{
  if(button.disabled || busy || !owned)return;
  const mode=button.dataset.face,before=proof;if(!Object.prototype.hasOwnProperty.call(names,mode))return;
  busy=true;window.faceControls();$('face-status').textContent='در حال ارسال حالت چهره…';
  try{
   await command('face',{expression:mode});
   if(logged && owned && proof===before){buttons.forEach(b=>b.setAttribute('aria-pressed',String(b===button)));$('face-status').textContent='حالت درخواستی: '+names[mode]+'؛ نتیجهٔ دریافت را در آخرین فرمان‌ها ببین.';}
  }catch(e){if(logged)$('face-status').textContent=e.message;}
  finally{busy=false;window.faceControls();}
 }));
 window.faceControls();
})();
