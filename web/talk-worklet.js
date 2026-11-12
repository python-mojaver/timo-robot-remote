class TimoTalkProcessor extends AudioWorkletProcessor {
 constructor(){super();this.position=0;this.samples=[];this.output=[];this.step=sampleRate/16000;}
 process(inputs){
  const channels=inputs[0];if(!channels || !channels.length)return true;
  for(let i=0;i<channels[0].length;i++){let x=0;for(const c of channels)x+=c[i] || 0;this.samples.push(x/channels.length);}
  while(this.position+1<this.samples.length){
   const i=Math.floor(this.position),f=this.position-i;
   const x=Math.max(-1,Math.min(1,this.samples[i]*(1-f)+this.samples[i+1]*f));
   this.output.push(Math.round(x*(x<0?32768:32767)));this.position+=this.step;
   if(this.output.length===1600){const bytes=new ArrayBuffer(3200),v=new DataView(bytes);this.output.forEach((x,i)=>v.setInt16(i*2,x,true));this.port.postMessage(bytes,[bytes]);this.output=[];}
  }
  const used=Math.min(Math.floor(this.position),Math.max(0,this.samples.length-1));this.samples=this.samples.slice(used);this.position-=used;return true;
 }
}
registerProcessor('timo-talk',TimoTalkProcessor);
