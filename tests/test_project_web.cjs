const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(require('path').join(__dirname,'../web/project.js'),'utf8');
function fixture(){
 const nodes={},calls=[],intervals=[];let response={response:'خیلی عالی بود'},pending=null;
 const node=()=>({value:'',textContent:'',disabled:false,checked:true,children:[],listeners:{},addEventListener(n,f){this.listeners[n]=f;},append(...x){this.children.push(...x);if(!this.value && x[0]?.value)this.value=x[0].value;},replaceChildren(){this.children=[];this.value='';},get options(){return this.children;}});
 const c={logged:true,owned:true,proof:'owner',caps:{speech:true},crypto:{randomUUID:()=> 'unique_request_001'},
  $:id=>nodes[id]??=node(),setInterval:f=>intervals.push(f),document:{hidden:false,createElement:()=>node()},
  api:async(path,body)=>{calls.push({path,body});if(path.endsWith('/state'))return {rooms:[{id:1,name:'اتاق من',available:true}],map_name:'HTN Home',navigation:{ready:true,busy:false}};if(path.endsWith('/chat'))return pending?pending:response;return {ok:true};},
  stopAll(){calls.push({path:'STOP'});},releaseLocal(){c.owned=false;c.proof='';},console};c.window=c;vm.createContext(c);vm.runInContext(source,c);
 return {c,nodes,calls,intervals,reply:v=>response=v,delay:p=>pending=p};
}
(async()=>{
 let f=fixture();await f.intervals[0]();assert.equal(f.nodes['project-room-go'].disabled,false);
 f.c.$('project-text').value='سلام';await f.nodes['project-chat-form'].listeners.submit({preventDefault(){}});await new Promise(setImmediate);
 assert(f.calls.some(x=>x.path.endsWith('/say')&&x.body.text==='خیلی عالی بود'));
 await f.nodes['project-room-go'].listeners.click();assert(f.calls.some(x=>x.path.endsWith('/navigate')&&x.body.room_id===1));
 f.nodes['project-nav-stop'].listeners.click();assert(f.calls.some(x=>x.path==='STOP'));
 // A reply arriving after ownership changes must neither appear nor speak.
 f=fixture();let resolve;f.delay(new Promise(r=>resolve=r));f.c.$('project-text').value='سلام';const task=f.nodes['project-chat-form'].listeners.submit({preventDefault(){}});f.c.proof='another-owner';resolve({response:'late'});await task;
 assert(!f.calls.some(x=>x.path.endsWith('/say')));assert.equal(f.nodes['project-chat-log'].children.length,1);
 f=fixture();f.reply({response:'توقف',stopped:true});f.c.$('project-text').value='توقف';await f.nodes['project-chat-form'].listeners.submit({preventDefault(){}});assert(!f.c.owned);assert(!f.calls.some(x=>x.path.endsWith('/say')));
 console.log('Project UI: canonical room ID, chat auto-speech, stop and stale-owner suppression passed.');
})().catch(e=>{console.error(e);process.exit(1);});
