package com.htnhome.timoremote.robot;

import android.media.AudioAttributes;
import android.media.MediaPlayer;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import java.util.HashMap;

/** پخش پاسخ صوتی تولیدشده در بک‌اند از مسیر درگاه احراز هویت‌شده. */
public final class ProjectSpeech {
    private final android.content.Context context;
    public ProjectSpeech(android.content.Context value){context=value.getApplicationContext();}
    private final Handler ui=new Handler(Looper.getMainLooper());
    private MediaPlayer player;private int generation=0;private long lease=0,lastAudio=-10000;
    public volatile boolean active=false;public volatile String state="idle",request="",message="";
    public synchronized void lease(long ms){lease=SystemClock.elapsedRealtime()+Math.max(0,Math.min(1600,ms));if(ms<=0)stop();}
    public synchronized boolean muted(){return active || SystemClock.elapsedRealtime()-lastAudio<500;}
    public synchronized void tick(){if(active && SystemClock.elapsedRealtime()>=lease)stop();}
    public synchronized void stop(){generation++;active=false;if(!"idle".equals(state)&&!"done".equals(state))state="stopped";ui.post(()->{if(player!=null){try{player.release();}catch(Exception ignored){}player=null;}});}
    public void play(String base,String token,String instance,String audio,String id,long validUntil){
        final int version;
        synchronized(this){if(SystemClock.elapsedRealtime()>=lease || SystemClock.elapsedRealtime()>=validUntil)return;stop();version=generation;active=true;state="preparing";request=id;message="در حال آماده‌سازی صدای پاسخ";}
        ui.post(()->{
            synchronized(this){if(version!=generation || SystemClock.elapsedRealtime()>=lease)return;}
            try{
                MediaPlayer p=new MediaPlayer();player=p;
                p.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build());
                HashMap<String,String> headers=new HashMap<>();headers.put("Authorization","Bearer "+token);headers.put("X-Agent-Instance",instance);
                p.setDataSource(context,android.net.Uri.parse(base+"/api/agent/speech/"+audio),headers);
                p.setOnPreparedListener(v->{synchronized(this){if(version!=generation || SystemClock.elapsedRealtime()>=lease){v.release();if(player==v)player=null;return;}state="playing";message="در حال پخش پاسخ از ربات";lastAudio=SystemClock.elapsedRealtime();v.start();}});
                p.setOnCompletionListener(v->{synchronized(this){if(version==generation){state="done";message="پخش پاسخ روی ربات پایان یافت.";active=false;lastAudio=SystemClock.elapsedRealtime();}v.release();if(player==v)player=null;}});
                p.setOnErrorListener((v,what,extra)->{synchronized(this){if(version==generation){state="failed";message="پخش صدای پاسخ ناموفق بود: "+what+"/"+extra;active=false;}v.release();if(player==v)player=null;}return true;});
                p.prepareAsync();
                ui.postDelayed(()->{synchronized(this){if(version==generation && active){message="مهلت پخش صدا تمام شد.";stop();}}},45000);
            }catch(Exception e){synchronized(this){if(version==generation){message="خطای پخش صدا: "+e.getClass().getSimpleName();stop();state="failed";}}}
        });
    }
}
