const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const root=path.join(__dirname,'..'),modes=['normal','happy','sad','upset','surprised'];
const html=fs.readFileSync(path.join(root,'android/robot/src/main/assets/face.html'),'utf8');
const groups=modes.map(id=>({id,active:false,classList:{toggle(key,value){groups.find(g=>g.id===id).active=value;}}}));
const renderer={document:{querySelectorAll:()=>groups,body:{dataset:{}}}};renderer.window=renderer;vm.createContext(renderer);
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],renderer);
assert.equal(groups.filter(x=>x.active)[0].id,'normal');
for(const mode of modes){assert(renderer.setTimoExpression(mode));assert.equal(groups.filter(x=>x.active).length,1);assert.equal(groups.find(x=>x.active).id,mode);}
assert.equal(renderer.setTimoExpression('unknown'),false);assert.equal(groups.find(x=>x.active).id,'surprised');
assert(!/https?:\/\//.test(html.replace('http://www.w3.org/2000/svg','')));
function fixture(){
 const calls=[],status={textContent:''};const buttons=['normal','happy','sad','angry','surprised'].map(mode=>({dataset:{face:mode},disabled:false,setAttribute(k,v){this[k]=v;},addEventListener(_,f){this.click=f;}}));
 const c={logged:true,owned:true,caps:{face:true},proof:'owner',document:{querySelectorAll:()=>buttons},$:()=>status,command:async(kind,args)=>{calls.push({kind,args});}};
 c.window=c;vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(root,'web/face-control.js'),'utf8'),c);return {c,buttons,calls,status};
}
(async()=>{
 let f=fixture();await f.buttons[3].click();assert.equal(f.calls.pop().args.expression,'angry');await f.buttons[1].click();assert.equal(f.calls[0].kind,'face');assert.equal(f.calls[0].args.expression,'happy');assert.equal(f.buttons[1]['aria-pressed'],'true');
 f.c.owned=false;f.c.faceControls();assert(f.buttons.every(b=>b.disabled));await f.buttons[2].click();assert.equal(f.calls.length,1);
 f=fixture();let resolve;f.c.command=()=>new Promise(r=>resolve=r);const pending=f.buttons[3].click();assert(f.buttons.every(b=>b.disabled));f.c.proof='new-owner';resolve({});await pending;assert(!f.buttons[3]['aria-pressed']);
 console.log('Face renderer: five states, normal startup, invalid-state rejection; controls: ownership, late reply and bounded command passed.');
})().catch(e=>{console.error(e);process.exit(1);});
