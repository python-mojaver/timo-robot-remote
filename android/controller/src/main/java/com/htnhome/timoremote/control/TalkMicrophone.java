package com.htnhome.timoremote.control;

import android.media.AudioRecord;
import android.media.AudioFormat;
import android.media.MediaRecorder;

/** ضبط میکروفون فقط در پیش‌زمینه و تا زمانی که دکمه نگه داشته شده فعال است. */
public final class TalkMicrophone {
    public interface Sink {void pcm(String id,byte[] bytes);void error(String id,String text);}
    private final Sink sink;private int generation=0;private AudioRecord record;private Thread worker;
    public TalkMicrophone(Sink sink){this.sink=sink;}
    public synchronized boolean start(String id){
        stop();if(worker!=null && worker.isAlive()){sink.error(id,"میکروفون قبلی در حال بسته‌شدن است؛ دوباره دکمه را نگه دار.");return false;}
        final int version=generation;
        worker=new Thread(()->{
            AudioRecord own=null;
            try{
                int min=AudioRecord.getMinBufferSize(16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT);
                if(min<=0)throw new IllegalStateException("Unsupported microphone format");
                own=new AudioRecord(MediaRecorder.AudioSource.MIC,16000,AudioFormat.CHANNEL_IN_MONO,AudioFormat.ENCODING_PCM_16BIT,Math.max(min*2,6400));
                synchronized(this){if(version!=generation)return;
                    if(own.getState()!=AudioRecord.STATE_INITIALIZED)throw new IllegalStateException("Microphone initialization failed");
                    record=own;own.startRecording();}
                while(current(version)){
                    byte[] data=new byte[3200];int offset=0;
                    while(offset<data.length && current(version)){int n=own.read(data,offset,data.length-offset);if(n<=0)throw new IllegalStateException("Microphone read "+n);offset+=n;}
                    if(current(version) && offset==data.length)sink.pcm(id,data);
                }
            }catch(Exception exc){if(current(version))sink.error(id,exc.getClass().getSimpleName()+": "+exc.getMessage());}
            finally{ synchronized(this){if(record==own)record=null;}if(own!=null){try{own.stop();}catch(Exception ignored){}try{own.release();}catch(Exception ignored){}}}
        },"TimoPhoneTalk");worker.start();return true;
    }
    private synchronized boolean current(int version){return version==generation;}
    public synchronized void stop(){generation++;if(record!=null)try{record.stop();}catch(Exception ignored){}}
}
