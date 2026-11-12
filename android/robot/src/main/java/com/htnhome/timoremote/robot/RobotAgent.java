package com.htnhome.timoremote.robot;

import android.content.Context;
import android.os.SystemClock;
import android.util.Log;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;

/** دریافت فرمان، تمدید مهلت و ارسال رسانه بین اپ ربات و درگاه. */
public final class RobotAgent {
    public interface FaceListener {void change(String value);}
    private volatile FaceListener faceListener;private volatile String faceMode="normal";
    public void setFaceListener(FaceListener value){faceListener=value;}

    private final String base,token,fallback,instance=UUID.randomUUID().toString();private volatile String activeBase;
    private final SdkBridge sdk;private final DriveGuard drive;private final HeadControl head;private final ArmRange arms;private final RemoteCamera camera;private final RemoteMicrophone mic;
    private final java.util.Set<HttpURLConnection> connections=ConcurrentHashMap.newKeySet();
    private final ScheduledExecutorService watchdog=Executors.newSingleThreadScheduledExecutor();
    // بازکردن میکروفون و گزارش نتیجه روی صف جدا هستند تا دریافت مهلت عقب نیفتد.
    private final ThreadPoolExecutor reports=new ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<Runnable>(16));
    private final ThreadPoolExecutor sensors=new ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<Runnable>(8));
    private final AtomicInteger mediaGeneration=new AtomicInteger();
    private final RemoteSpeaker speaker=new RemoteSpeaker();
    private final ProjectSpeech projectSpeech;
    private final NavigationControl navigation;
    private final SdkBridge.Receiver feedback=this::sdkFeedback;
    private final java.util.concurrent.ExecutorService navigationWorker=Executors.newSingleThreadExecutor();
    private final Object leaseLock=new Object();
    private volatile boolean running=false,hadLease=false;private volatile long leaseUntil=0;
    private volatile String mediaNotice="",talkError="",armWaveReply="";
    public volatile String status="آمادهٔ اتصال";
    public RobotAgent(Context context,String base,String token,String cameraId,SdkBridge sdk,String fallback){
        this.base=base;this.activeBase=base;this.fallback=fallback;this.token=token;this.sdk=sdk;projectSpeech=new ProjectSpeech(context);camera=new RemoteCamera(context,cameraId);mic=new RemoteMicrophone(context);
        android.content.SharedPreferences navigationPrefs=context.getSharedPreferences("timo_remote_navigation",Context.MODE_PRIVATE);
        navigation=new NavigationControl(value->{Log.i("TIMO_REMOTE_NAV",value);return sdk.send(value);},SystemClock::elapsedRealtime,
            value->navigationPrefs.edit().putBoolean("pending",value).apply(),navigationPrefs.getBoolean("pending",false));
        sdk.setReceiver(feedback);
        drive=new DriveGuard(value->{Log.i("TIMO_REMOTE_DRIVE",value);return sdk.send(value);},SystemClock::elapsedRealtime);
        head=new HeadControl(value->{Log.i("TIMO_REMOTE_HEAD",value);return sdk.send(value);},SystemClock::elapsedRealtime,
            context.getSharedPreferences("MainActivity",Context.MODE_PRIVATE).getString("head_profile",""));
        arms=new ArmRange(value->{Log.i("TIMO_REMOTE_ARM",value);return sdk.send(value);},SystemClock::elapsedRealtime);
    }
    public void start(){if(running)return;running=true;
        watchdog.scheduleAtFixedRate(()->{if(!running)return;drive.tick();speaker.tick();projectSpeech.tick();navigation.tick(sdk.ready(),drive.settled());synchronized(leaseLock){
            if(hadLease && SystemClock.elapsedRealtime()>=leaseUntil){hadLease=false;arms.lease(0);stopMedia("مهلت کنترل تمدید نشد؛ حسگرها خاموش شدند. کنترل و اتصال را بررسی کن.");}
        }},100,100,TimeUnit.MILLISECONDS);
        new Thread(this::poll,"TimoRemotePoll").start();new Thread(this::frames,"TimoRemoteFrames").start();new Thread(this::audio,"TimoRemoteAudio").start();new Thread(this::talkAudio,"TimoRemoteTalk").start();
    }
    private JSONObject request(String path,byte[] data,String mime) throws Exception {
        try{return requestAt(activeBase,path,data,mime);}
        catch(java.io.IOException error){
            // فقط poll می‌تواند مسیر ارتباطی را عوض کند. ارسال رسانه و نتیجه دوباره اجرا نمی‌شود.
            if(!"/api/agent/poll".equals(path) || fallback==null || fallback.isEmpty() || !running)throw error;
            String alternate=activeBase.equals(base)?fallback:base;
            if(alternate.equals(activeBase))throw error;
            JSONObject result=requestAt(alternate,path,data,mime);activeBase=alternate;return result;
        }
    }
    private JSONObject requestAt(String origin,String path,byte[] data,String mime) throws Exception {
        HttpURLConnection c=(HttpURLConnection)new URL(origin+path).openConnection();connections.add(c);
        try{if(!running)throw new IllegalStateException("Agent closed");
            c.setInstanceFollowRedirects(false);c.setRequestMethod("POST");c.setConnectTimeout(1500);c.setReadTimeout(1800);
            c.setRequestProperty("Authorization","Bearer "+token);c.setRequestProperty("X-Agent-Instance",instance);c.setRequestProperty("Content-Type",mime);
            c.setDoOutput(true);c.setFixedLengthStreamingMode(data.length);try(java.io.OutputStream out=c.getOutputStream()){out.write(data);}
            if(c.getResponseCode()!=200)throw new IllegalStateException("HTTP "+c.getResponseCode());
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();try(java.io.InputStream in=c.getInputStream()){
                byte[] buf=new byte[4096];int n;while((n=in.read(buf))>=0){if(bytes.size()+n>65536)throw new IllegalStateException("Response too large");bytes.write(buf,0,n);}}
            return new JSONObject(bytes.toString("UTF-8"));
        }finally{connections.remove(c);c.disconnect();}
    }
    private JSONObject json(String path,JSONObject body) throws Exception{return request(path,body.toString().getBytes("UTF-8"),"application/json");}
    private void stopMedia(String reason){
        mediaGeneration.incrementAndGet();
        if(camera.active || mic.active){mediaNotice=reason;Log.w("TIMO_REMOTE_MEDIA",reason);}
        camera.stop();mic.stop();speaker.stop();projectSpeech.stop();
    }
    private void report(JSONObject command,boolean ok,String detail){
        if(!running)return;
        try{reports.execute(()->{
            try{if(running)json("/api/agent/result",new JSONObject().put("instance",instance).put("id",command.optString("id"))
                .put("status",ok?"submitted":"rejected").put("detail",ok?detail:"اجرا نشد: "+detail));}
            catch(Exception e){Log.w("TIMO_REMOTE_NET","Result report failed: "+e.getClass().getSimpleName());}
        });}catch(java.util.concurrent.RejectedExecutionException e){Log.w("TIMO_REMOTE_NET","Result report queue full/closed");}
    }
    private void sensorCommand(JSONObject command,String kind,long validUntil){
        final int version=mediaGeneration.get();
        try{sensors.execute(()->{
            if(!running || version!=mediaGeneration.get() || SystemClock.elapsedRealtime()>=validUntil || SystemClock.elapsedRealtime()>=leaseUntil){report(command,false,"مهلت فرمان حسگر یا کنترل منقضی شده است.");return;}
            boolean ok;String detail;
            if("camera_on".equals(kind)){ok=camera.start();detail=ok?"دوربین در حال بازشدن است؛ منتظر تصویر باشید.":camera.error;}
            else if("camera_off".equals(kind)){camera.stop();ok=true;detail="دوربین خاموش شد.";}
            else if("mic_on".equals(kind)){ok=mic.start();detail=ok?"میکروفون زنده روشن شد.":mic.error;}
            else{mic.stop();ok=true;detail="میکروفون خاموش شد.";}
            // اگر اختیار حین بازشدن حسگر باطل شد، حسگر بلافاصله بسته می‌شود.
            if(!running || version!=mediaGeneration.get() || SystemClock.elapsedRealtime()>=leaseUntil){
                camera.stop();mic.stop();ok=false;detail="کنترل هنگام راه‌اندازی حسگر پایان یافت.";
            }
            if(ok)mediaNotice="";else mediaNotice=detail;
            Log.i("TIMO_REMOTE_MEDIA",kind+": "+detail);report(command,ok,detail);
        });}catch(java.util.concurrent.RejectedExecutionException e){report(command,false,"راه‌اندازی حسگر قبلی هنوز در حال انجام است.");}
    }
    private void poll(){
        while(running){try{
            boolean sdkReady=sdk.ready();
            if(!sdkReady){arms.lease(0);arms.stop(false);}
            boolean armReady=sdkReady && head.coupled() && drive.settled() && navigation.ready();
            // هنگام ناوبری یا آزمون بازو، کنترل دستی پایه به پنل ارائه نمی‌شود.
            boolean navBusy=navigation.busy(), armsActive=arms.active();
            String driveBlock=navBusy?"navigation":armsActive?"arms":"";
            JSONObject caps=new JSONObject().put("face",faceListener!=null).put("sdk",sdkReady).put("drive",sdkReady && !navBusy && !armsActive).put("navigation",sdkReady && !armsActive).put("speech",true).put("stop",sdkReady)
                .put("speaker",true).put("head_arm_rest",head.coupled()).put("head",sdkReady && head.supported()).put("camera",camera.available()).put("camera_active",camera.active).put("microphone",mic.available()).put("mic_active",mic.active).put("moving",drive.moving()).put("arm_wave_stop",sdkReady).put("arm_range",sdkReady && head.coupled()).put("arm_range_ready",armReady);
            long sent=SystemClock.elapsedRealtime();
            JSONObject response=json("/api/agent/poll",new JSONObject().put("instance",instance).put("capabilities",caps)
                .put("diagnostics",new JSONArray().put(camera.diagnostic()).put("Microphone: "+mic.error).put(head.diagnostic()).put("Speaker active="+speaker.active+"; packets="+speaker.packets+"; error="+speaker.error+"; download="+talkError).put("Face requested="+faceMode).put(armWaveReply).put(sdk.lastMessage))
                .put("navigation",navigationSnapshot()).put("speech",new JSONObject().put("state",projectSpeech.state).put("request_id",projectSpeech.request).put("message",projectSpeech.message))
                .put("drive_block",driveBlock)
                .put("arm_range",new JSONObject().put("armed",arms.armed()).put("can_begin",arms.canBegin()).put("can_finish",arms.canFinish()).put("left",arms.left()).put("right",arms.right()))
                .put("camera_error",camera.error).put("mic_error",mic.error).put("media_notice",mediaNotice).put("head_notice",head.notice()));
            if(!running)break;long elapsed=SystemClock.elapsedRealtime()-sent;
            long lease=Math.min(1600,ControlTiming.remaining(response.optLong("lease_remaining_ms"),elapsed,response.optLong("server_wait_ms")));
            synchronized(leaseLock){drive.lease(lease);head.lease(lease);arms.lease(lease);speaker.lease(lease);projectSpeech.lease(lease);navigation.lease(lease);leaseUntil=SystemClock.elapsedRealtime()+lease;
                if(lease>0)hadLease=true;else if(hadLease){hadLease=false;stopMedia("کنترل آزاد یا منقضی شد؛ دوربین و میکروفون خاموش شدند.");}}
            status="متصل به پنل · SDK: "+(sdk.ready()?"متصل":"قطع")+" · دوربین: "+camera.active+" · میکروفون: "+mic.active;
            JSONObject command=response.optJSONObject("command");if(command==null)continue;
            String kind=command.optString("kind"),detail="فرمان شناخته نشد.";boolean ok=false;
            long remaining=ControlTiming.remaining(command.optLong("valid_for_ms"),elapsed,response.optLong("server_wait_ms"));
            if("stop".equals(kind) || "brake".equals(kind)){
                ok=drive.stopBarrier(command.optLong("seq"));
                detail=ok?"درخواست توقف پایه به SDK ارسال شد.":"ارسال درخواست توقف پایه به SDK تأیید نشد.";
                if("stop".equals(kind)){
                    navigation.stopControls();
                    head.barrier(command.optLong("seq"));
                    head.lease(0);
                    arms.lease(0);
                    arms.stop(false);
                    JSONObject args=command.optJSONObject("args");
                    if(remaining>0 && args!=null && "operator".equals(args.optString("reason"))){
                        armWaveReply="";
                        int sentStops=ArmWaveStop.request(sdk::send);
                        arms.stop(sentStops==2);
                        detail+=" ارسال درخواست‌های توقف حرکت تکراری بازو به SDK: "+sentStops+" از ۲.";
                        ok=ok && sentStops==2;
                    }
                    stopMedia("درخواست توقف و آزادکردن کنترل دریافت شد.");
                }
                detail+=" توقف فیزیکی تأیید نشده است.";
            }
            else if(remaining>0 && lease>0){
                if("face".equals(kind)){JSONObject args=command.optJSONObject("args");String mode=args==null?"":args.optString("expression");FaceListener next=faceListener;
                    ok=FaceMode.valid(mode)&&next!=null;if(ok){faceMode=mode;next.change(mode);}detail=ok?"درخواست نمایش چهرهٔ "+mode+" به صفحهٔ ربات ارسال شد.":"حالت چهره معتبر نیست.";}
                else if("nav_room".equals(kind)){
                    if(arms.active()){report(command,false,"آزمون بازو فعال است؛ اول آن را پایان بده.");continue;}
                    navigationCommand(command,SystemClock.elapsedRealtime()+remaining);continue;
                }
                else if("speak".equals(kind)){JSONObject a=command.optJSONObject("args");String audio=a==null?"":a.optString("audio_id");
                    ok=audio.matches("[a-f0-9]{32}");if(ok)projectSpeech.play(activeBase,token,instance,audio,a.optString("project_request"),SystemClock.elapsedRealtime()+remaining);detail="درخواست پخش پاسخ به پخش‌کنندهٔ ربات ارسال شد.";}
                else if("drive".equals(kind)){if(navigation.busy() || arms.active()){report(command,false,"ابتدا پایان ناوبری و آزمون بازو را بررسی کن.");continue;}navigation.manual();JSONObject args=command.optJSONObject("args");String direction=args==null?"":args.optString("direction");ok=drive.drive(direction,command.optLong("seq"),SystemClock.elapsedRealtime()+remaining);detail=ok?"فرمان "+direction+" به SDK ارسال شد.":"فرمان جهت منقضی یا توسط کنترل حرکت رد شد.";}
                else if("head_step".equals(kind) || "head_reset".equals(kind)){
                    JSONObject args=command.optJSONObject("args");String direction="head_reset".equals(kind)?"center":args==null?"":args.optString("direction");
                    ok=sdk.ready() && head.command(direction,command.optLong("seq"),SystemClock.elapsedRealtime()+remaining);
                    detail=ok?"هدف کوتاه سر به SDK ارسال شد؛ موقعیت فیزیکی هنوز تأیید نشده است.":"کنترل سر پشتیبانی نمی‌شود، به حد هدف رسیده یا مهلت/فاصلهٔ فرمان رعایت نشده است.";
                }
                else if("arm_range".equals(kind)){
                    JSONObject a=command.optJSONObject("args");
                    String result=null;
                    if(a!=null && running && sdk.ready() && head.coupled()){
                        String action=a.optString("action");
                        Object goal=a.opt("goal");
                        boolean finish="finish".equals(action);
                        boolean armMotion=drive.settled() && navigation.ready() && ("begin".equals(action)
                                || ("move".equals(action) && goal instanceof Integer) || "rest".equals(action));
                        if(finish || armMotion){
                            result=arms.apply(action,a.optString("side"),"rest".equals(action)?0:a.optInt("goal",-1),
                                Boolean.TRUE.equals(a.opt("confirmed")),command.optLong("seq"),SystemClock.elapsedRealtime()+remaining);
                        }
                    }
                    ok=result!=null;
                    detail=ok?result:"درخواست بازو پذیرفته نشد. وضعیت ربات، مهلت و تأیید اپراتور را بررسی کن.";
                }
                else if("camera_on".equals(kind) || "camera_off".equals(kind) || "mic_on".equals(kind) || "mic_off".equals(kind)){
                    sensorCommand(command,kind,SystemClock.elapsedRealtime()+remaining);continue;
                }
            }else detail="مهلت فرمان یا اختیار کنترل منقضی شده است.";
            report(command,ok,detail);
        }catch(Exception e){if(!running)break;status="ارتباط پنل قطع است: "+e.getClass().getSimpleName();Log.w("TIMO_REMOTE_NET",status);
            synchronized(leaseLock){drive.lease(0);head.lease(0);arms.lease(0);arms.stop(false);speaker.lease(0);projectSpeech.lease(0);navigation.lease(0);leaseUntil=0;hadLease=false;stopMedia(status);}sleep(350);}}
    }
    private void sdkFeedback(String raw){
        if(!running || raw==null || raw.length()>16384)return;
        try{JSONObject e=new JSONObject(raw);String id=e.optString("msg_id");
            if("ROBOT_ARM_LOOP_STOP_RSP".equals(id)){
                armWaveReply="آخرین پاسخ توقف تکرار بازو از SDK · error_code="+(e.has("error_code")?e.optInt("error_code",-1):"نامشخص");
            }
            if(id.startsWith("NAVI_"))Log.i("TIMO_REMOTE_NAV","rx: "+raw);
            if("NAVI_GET_STATUS_RSP".equals(id))navigation.statusResponse(e.opt("error_code"),e.opt("state"));
            else if("NAVI_ROBOT_MOVE_TO_NTF".equals(id))navigation.moveNotification(e.optInt("error_code",-1));
            else if("NAVI_ROBOT_MOVE_TO_RSP".equals(id))navigation.moveResponse(e.optInt("error_code",-1));
        }catch(Exception ignored){}
    }
    private JSONObject navigationSnapshot(){
        JSONObject value=new JSONObject();try{value.put("state",navigation.state()).put("busy",navigation.busy()).put("ready",navigation.ready())
            .put("request_id",navigation.request()).put("message",navigation.message()).put("generation",navigation.generation());}catch(Exception ignored){}return value;
    }
    private void navigationCommand(JSONObject command,long validUntil){
        try{navigationWorker.execute(()->{
            boolean accepted=false;String detail="فرمان مقصد پیش از ارسال منقضی یا رد شد.";
            try{
                if(!running || SystemClock.elapsedRealtime()>=validUntil || !drive.settled() || arms.active() || SystemClock.elapsedRealtime()>=leaseUntil)throw new IllegalStateException("فرمان تازه یا توقف حرکت دستی تأیید نشده است.");
                JSONObject a=json("/api/agent/navigation/validate",new JSONObject().put("command_id",command.optString("id")));
                JSONObject raw=a.getJSONObject("pose"),pose=new JSONObject();
                for(String k:new String[]{"x","y","z","rotation"}){double n=raw.getDouble(k);if(Double.isNaN(n)||Double.isInfinite(n)||Math.abs(n)>("rotation".equals(k)?Math.PI*2:10000))throw new IllegalStateException("مختصات معتبر نیست.");pose.put(k,n);}
                if(!running || SystemClock.elapsedRealtime()>=validUntil || SystemClock.elapsedRealtime()>=leaseUntil || !sdk.ready() || arms.active())throw new IllegalStateException("مهلت فرمان یا اتصال SDK پایان یافت.");
                accepted=navigation.begin(pose.toString(),a.getString("name"),a.getString("project_request"),command.optLong("seq"),validUntil,drive.settled());
                detail=accepted?navigation.message():"SDK برای مقصد آماده نیست؛ فرمان اجرا نشد.";
            }catch(Exception e){detail=e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();}
            report(command,accepted,detail);
        });}catch(java.util.concurrent.RejectedExecutionException e){report(command,false,"اتصال اپ ربات پایان یافته است.");}
    }
    private void frames(){while(running){try{RemoteCamera.Frame f=camera.take();if(f!=null && SystemClock.elapsedRealtime()-f.at<400)request("/api/agent/frame",f.bytes,"image/jpeg");else sleep(60);}catch(Exception e){sleep(150);}}}
    private void audio(){while(running){try{RemoteMicrophone.Packet p=mic.take();if(!speaker.mutesMicrophone() && !projectSpeech.muted() && p!=null && SystemClock.elapsedRealtime()-p.at<250)request("/api/agent/audio",p.bytes,"application/octet-stream");else sleep(20);}catch(Exception e){sleep(100);}}}
    private void talkAudio(){
        String stream="";long sequence=0;
        try{while(running){
            HttpURLConnection c=null;
            try{
                if(SystemClock.elapsedRealtime()>=leaseUntil){speaker.stop();speaker.releaseRetired();sleep(60);continue;}
                long began=SystemClock.elapsedRealtime();
                c=(HttpURLConnection)new URL(activeBase+"/api/agent/talk?after="+sequence).openConnection();connections.add(c);
                c.setInstanceFollowRedirects(false);c.setConnectTimeout(700);c.setReadTimeout(700);
                c.setRequestProperty("Authorization","Bearer "+token);c.setRequestProperty("X-Agent-Instance",instance);c.setRequestProperty("X-Talk-Stream",stream);
                int code=c.getResponseCode();String id=c.getHeaderField("X-Talk-Stream");
                if(!"1".equals(c.getHeaderField("X-Talk-Active"))){speaker.stop();stream="";sequence=0;}
                else if(code==200){
                    if(id==null || !id.matches("[a-f0-9]{32}"))throw new IllegalStateException("Invalid talk stream");
                    if(!id.equals(stream)){stream=id;sequence=0;}
                    long next=Long.parseLong(c.getHeaderField("X-Audio-Sequence"));long age=Long.parseLong(c.getHeaderField("X-Audio-Age-Ms"));
                    ByteArrayOutputStream out=new ByteArrayOutputStream();
                    try(java.io.InputStream in=c.getInputStream()){byte[] buf=new byte[3200];int n;while((n=in.read(buf))>=0){if(out.size()+n>6400)throw new IllegalStateException("Talk packet too large");out.write(buf,0,n);}}
                    if(running && next>sequence){sequence=next;projectSpeech.stop();long valid=500-Math.max(0,age)-(SystemClock.elapsedRealtime()-began);speaker.feed(stream,sequence,out.toByteArray(),valid);}
                }else if(code!=204)throw new IllegalStateException("Talk HTTP "+code);
                talkError="";speaker.releaseRetired();sleep(code==200?10:40);
            }catch(Exception exc){talkError=exc.getClass().getSimpleName()+": "+exc.getMessage();speaker.stop();speaker.releaseRetired();if(running)Log.w("TIMO_REMOTE_TALK",exc.getClass().getSimpleName()+": "+exc.getMessage());sleep(100);}
            finally{if(c!=null){connections.remove(c);c.disconnect();}}
        }}finally{speaker.closeWorker();}
    }
    private static void sleep(long ms){try{Thread.sleep(ms);}catch(InterruptedException ignored){}}
    public void stop(Runnable afterStop){faceListener=null;running=false;navigation.close();sdk.clearReceiver(feedback);navigationWorker.shutdownNow();projectSpeech.stop();head.lease(0);arms.lease(0);arms.stop(false);speaker.lease(0);mediaGeneration.incrementAndGet();connections.forEach(HttpURLConnection::disconnect);camera.stop();mic.stop();watchdog.shutdownNow();reports.shutdownNow();sensors.shutdownNow();
        new Thread(()->{try{drive.close();for(int i=0;i<4;i++){sleep(110);drive.tick();}}finally{afterStop.run();}},"TimoRemoteStop").start();}
}
