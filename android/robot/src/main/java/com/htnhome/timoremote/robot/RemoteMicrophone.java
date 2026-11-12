package com.htnhome.timoremote.robot;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.SystemClock;
import java.util.concurrent.atomic.AtomicReference;

/** نگه‌داری آخرین قطعهٔ ۱۰۰ میلی‌ثانیه‌ای صدای PCM در حافظه. */
public final class RemoteMicrophone {
    public static final class Packet {public final byte[] bytes;public final long at;
        Packet(byte[] b){bytes=b;at=SystemClock.elapsedRealtime();}}
    private final Context context;private volatile AudioRecord recorder;
    private final AtomicReference<Packet> latest=new AtomicReference<>();
    public volatile boolean active=false;public volatile String error="";private int generation=0;
    public RemoteMicrophone(Context context){this.context=context;}
    public boolean available(){return context.checkSelfPermission(Manifest.permission.RECORD_AUDIO)==PackageManager.PERMISSION_GRANTED;}
    public synchronized boolean start(){
        if(active)return true;if(!available()){error="مجوز میکروفون داده نشده است.";return false;}
        stop();final int version=++generation;
        try{
            int min=AudioRecord.getMinBufferSize(16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT);
            if(min<0)throw new IllegalStateException("Unsupported microphone format");
            final AudioRecord record=new AudioRecord(MediaRecorder.AudioSource.MIC,16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,Math.max(min*2,12800));
            if(record.getState()!=AudioRecord.STATE_INITIALIZED){record.release();throw new IllegalStateException("Microphone initialization failed");}
            record.startRecording();if(record.getRecordingState()!=AudioRecord.RECORDSTATE_RECORDING){record.release();throw new IllegalStateException("Microphone did not start");}
            recorder=record;active=true;error="";
            new Thread(()->{
                try{while(active && version==generation){byte[] bytes=new byte[3200];int count=0;
                    while(count<bytes.length && active && version==generation){int n=record.read(bytes,count,bytes.length-count);if(n<=0)throw new IllegalStateException("Microphone read "+n);count+=n;}
                    if(active && version==generation && count==bytes.length)latest.set(new Packet(bytes));
                }}catch(Exception e){if(version==generation){error=e.getMessage();stop();}}
            },"TimoRemoteMic").start();return true;
        }catch(Exception e){error=e.getClass().getSimpleName()+": "+e.getMessage();stop();return false;}
    }
    public Packet take(){return latest.getAndSet(null);}
    public synchronized void stop(){active=false;generation++;latest.set(null);AudioRecord r=recorder;recorder=null;
        if(r!=null){try{r.stop();}catch(Exception ignored){}try{r.release();}catch(Exception ignored){}}}
}
