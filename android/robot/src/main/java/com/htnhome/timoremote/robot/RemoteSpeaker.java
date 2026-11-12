package com.htnhome.timoremote.robot;

import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.os.SystemClock;
import java.util.concurrent.ConcurrentLinkedQueue;

/** توقف پخش همان لحظه انجام می‌شود. آزادسازی AudioTrack پس از پایان نوشتن روی نخ دانلود است. */
public final class RemoteSpeaker {
    private AudioTrack track;private int generation=0;private long lease=0,until=0,lastSequence=0;
    private long lastPacketAt=-10000;
    public synchronized boolean mutesMicrophone(){return active || SystemClock.elapsedRealtime()-lastPacketAt<500;}
    private String stream="";private final ConcurrentLinkedQueue<AudioTrack> retired=new ConcurrentLinkedQueue<>();
    public volatile boolean active=false;public volatile String error="";public volatile long packets=0;
    public synchronized void lease(long ms){lease=SystemClock.elapsedRealtime()+Math.max(0,Math.min(1600,ms));if(ms<=0)stop();}
    public synchronized void tick(){long now=SystemClock.elapsedRealtime();if(active && (now>=lease || now>=until))stop();}
    public synchronized void stop(){
        generation++;active=false;stream="";lastSequence=0;AudioTrack old=track;track=null;
        if(old!=null){try{old.pause();old.flush();old.stop();}catch(Exception ignored){}retired.add(old);}
    }
    public void releaseRetired(){AudioTrack old;while((old=retired.poll())!=null)try{old.release();}catch(Exception ignored){}}
    public void feed(String id,long seq,byte[] pcm,long validMs){
        releaseRetired();if(id==null || !id.matches("[a-f0-9]{32}") || pcm.length==0 || pcm.length>6400 || pcm.length%2!=0 || validMs<=0)return;
        AudioTrack output;int version;long deadline;
        synchronized(this){
            if(SystemClock.elapsedRealtime()>=lease)return;
            if(!id.equals(stream)){stop();stream=id;}
            if(seq<=lastSequence)return;lastSequence=seq;lastPacketAt=SystemClock.elapsedRealtime();
            version=generation;deadline=Math.min(lease,SystemClock.elapsedRealtime()+Math.min(350,validMs));until=deadline;output=track;
        }
        try{
            if(output==null){
                int min=AudioTrack.getMinBufferSize(16000,AudioFormat.CHANNEL_OUT_MONO,AudioFormat.ENCODING_PCM_16BIT);
                if(min<=0)throw new IllegalStateException("Unsupported speaker PCM format");
                output=new AudioTrack.Builder().setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                    .setAudioFormat(new AudioFormat.Builder().setSampleRate(16000).setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                    .setBufferSizeInBytes(Math.max(min,3200)).setTransferMode(AudioTrack.MODE_STREAM).build();
                if(output.getState()!=AudioTrack.STATE_INITIALIZED){output.release();throw new IllegalStateException("Speaker initialization failed");}
                synchronized(this){if(version!=generation || SystemClock.elapsedRealtime()>=lease){output.release();return;}track=output;until=Math.min(lease,SystemClock.elapsedRealtime()+350);output.setVolume(.8f);output.play();active=true;error="";}
            }
            int offset=0;
            while(offset<pcm.length){
                synchronized(this){if(version!=generation || SystemClock.elapsedRealtime()>=deadline)return;}
                int n=output.write(pcm,offset,pcm.length-offset,AudioTrack.WRITE_NON_BLOCKING);
                if(n<0)throw new IllegalStateException("Speaker write error "+n);
                if(n==0)SystemClock.sleep(5);else offset+=n;
            }
            packets++;
        }catch(Exception exc){synchronized(this){if(version==generation){error=exc.getClass().getSimpleName()+": "+exc.getMessage();stop();}}}
        finally{releaseRetired();}
    }
    public void closeWorker(){stop();releaseRetired();}
}
