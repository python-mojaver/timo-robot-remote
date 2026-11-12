const fs=require('fs'),vm=require('vm'),assert=require('assert');
const path=require('path'),root=path.join(__dirname,'..');
const source=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const talk=source.slice(source.indexOf('let talkHeld='),source.indexOf("$('login-form').addEventListener"));
function fixture(options={}){
 const nodes={},calls=[],state={media:0,stopped:0,context:0};
 const stream={getTracks:()=>[{stop:()=>state.stopped++}]};
 const context={console,setTimeout,clearTimeout,AbortController,atob:s=>Buffer.from(s,'base64').toString('binary'),Uint8Array,ArrayBuffer,
  owned:true,caps:{speaker:true},proof:'owner',csrf:'csrf',micActive:false,audioContext:null,audioCursor:0,audioNext:0,
  $:id=>nodes[id]??=( {disabled:false,textContent:'',addEventListener(){},setPointerCapture(){}}),
  document:{hidden:false},stopAudio(){this.audioContext=null;},
  api:options.api || (async()=>({stream_id:'a'.repeat(32)})),
  fetch:async(url,request)=>{calls.push({url,request});return {ok:true,json:async()=>({ok:true})};},
  navigator:{mediaDevices:{getUserMedia:()=>{state.media++;return options.media || Promise.resolve(stream);}}},
  AudioWorkletNode:class {constructor(){this.port={};}connect(){}disconnect(){}},
 };
 context.window=context;context.addEventListener=()=>{};
 context.AudioContext=class {constructor(){state.context++;this.audioWorklet={addModule:async()=>{}};}resume(){return Promise.resolve();}close(){return Promise.resolve();}createMediaStreamSource(){return {connect(){}};}createGain(){return {gain:{value:1},connect(){}};}};
 vm.createContext(context);vm.runInContext(talk,context);
 return {context,nodes,calls,state,stream,run:s=>vm.runInContext(s,context)};
}
(async()=>{
 let resolve;
 let f=fixture({api:()=>new Promise(r=>resolve=r)});let begin=f.run('talkBegin()');f.run('talkEnd()');resolve({stream_id:'a'.repeat(32)});await begin;
 assert.equal(f.state.media,0);assert(f.calls.some(c=>c.url==='/api/talk/stop'));
 let permit;f=fixture({media:new Promise(r=>permit=r)});begin=f.run('talkBegin()');await new Promise(setImmediate);f.run('talkEnd()');permit(f.stream);await begin;
 assert.equal(f.state.stopped,1);assert.equal(f.state.context,0);
 f=fixture();let nativeStarted=0,nativeStopped=0;f.context.TimoTalk={start:()=>nativeStarted++,stop:()=>nativeStopped++};await f.run('talkBegin()');
 assert.equal(nativeStarted,1);assert.equal(f.state.media,0);
 f.context.timoTalkPCM('a'.repeat(32),Buffer.from([1,0,2,0]).toString('base64'));await new Promise(setImmediate);
 assert(f.calls.some(c=>c.url==='/api/talk/audio' && c.request.headers['X-Control-Token']==='owner'));
 f.run('talkEnd()');const n=f.calls.length;f.context.timoTalkPCM('a'.repeat(32),'AQACAA==');await new Promise(setImmediate);assert.equal(f.calls.length,n);assert(nativeStopped>0);
 // Worklet resampling must preserve phase between arbitrary render quanta.
 function render(step){let Processor;const packets=[];
  const c={sampleRate:48000,AudioWorkletProcessor:class{constructor(){this.port={postMessage:bytes=>packets.push(Buffer.from(bytes))};}},registerProcessor:(name,p)=>Processor=p};vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(root,'web/talk-worklet.js'),'utf8'),c);
  const p=new Processor();const data=Float32Array.from({length:48001},(_,i)=>.5*Math.sin(2*Math.PI*440*i/48000));
  for(let i=0;i<data.length;i+=step)p.process([[data.slice(i,i+step)]]);return packets;
 }
 const a=render(137),b=render(4096);assert.equal(a.length,10);assert.equal(b.length,10);a.forEach((bytes,i)=>assert(bytes.equals(b[i])));
 console.log('Web talk: late start/permission cancellation, native bridge upload, late-packet suppression and worklet continuity passed.');
})().catch(e=>{console.error(e);process.exit(1);});
