package com.htnhome.timoremote.robot;

/** ماشین حالت ناوبری. چون پاسخ وضعیت شناسه ندارد، هم‌زمان فقط یک استعلام باز می‌ماند. */
public final class NavigationControl {
    public interface Sender { boolean send(String json); }
    public interface Clock { long now(); }
    public interface Persistence { void pending(boolean value); }
    private final Sender sender; private final Clock clock; private final Persistence persistence;
    private String state="checking",request="",message="در انتظار دو پاسخ بیکار از SDK";
    private boolean external=false,busy=false,ready=false,arrived=false,stopping=false,query=false,needCancel=false;
    private int idle=0; private long lease=0,deadline=0,queryAt=0,nextQuery=0,lastIdle=-10000,nextCancel=0,generation=1,lastSequence=0;
    public NavigationControl(Sender s,Clock c,Persistence p,boolean recovering){sender=s;clock=c;persistence=p;
        if(recovering){busy=true;stopping=true;needCancel=true;state="uncertain";message="حرکت اجرای قبلی تأیید نشده؛ بررسی و لغو SDK در حال انجام است.";}}
    public synchronized void lease(long ms){lease=clock.now()+Math.max(0,Math.min(1600,ms));}
    public synchronized boolean busy(){return busy || external;}
    public synchronized boolean ready(){return ready && !busy && !external && clock.now()-lastIdle<3000;}
    public synchronized String state(){return state;}
    public synchronized String request(){return request;}
    public synchronized String message(){return message;}
    public synchronized long generation(){return generation;}
    public synchronized void manual(){if(busy)return;ready=false;idle=0;query=false;nextQuery=0;state="checking";message="پس از حرکت دستی، وضعیت SDK دوباره بررسی می‌شود.";}
    public synchronized boolean begin(String pose,String name,String id,long seq,long validUntil,boolean manualQuiet){
        long now=clock.now();
        if(!ready() || !manualQuiet || now>=lease || now>=validUntil || seq<=lastSequence)return false;
        lastSequence=seq;generation++;request=id;busy=true;ready=false;arrived=false;stopping=false;needCancel=false;
        query=false;idle=0;deadline=now+180000;persistence.pending(true);
        state="submitted";message="فرمان حرکت به «"+name+"» به SDK ارسال شد؛ رسیدن هنوز تأیید نشده است.";
        if(!sender.send("{\"msg_id\":\"NAVI_ROBOT_MOVE_TO_REQ\",\"pos\":"+pose+"}")){
            state="uncertain";message="ارسال مقصد ناموفق یا نامشخص بود؛ لغو و بررسی وضعیت لازم است.";stopping=true;needCancel=true;
        }
        return true; // Accepted/latched, even if transport outcome is uncertain.
    }
    public synchronized void cancel(){
        generation++;busy=true;ready=false;arrived=false;stopping=true;needCancel=true;query=false;idle=0;nextQuery=0;nextCancel=0;
        state="stopping";message="لغو مسیر درخواست شد؛ منتظر دو پاسخ بیکار از SDK.";persistence.pending(true);
    }
    public synchronized void stopControls(){
        if(busy()){
            cancel();
        }else{
            // توقف عمومی وضعیت را تازه می‌کند. فقط مسیر واقعاً فعال به حالت لغو می‌رود.
            manual();
            sender.send("{\"msg_id\":\"NAVI_ROBOT_CANCEL_REQ\"}");
        }
    }
    public synchronized void moveResponse(int error){
        if(!busy || stopping)return;
        if(error!=0){state="uncertain";message="SDK فرمان مقصد را با خطا گزارش کرد؛ لغو و بررسی در حال انجام است.";stopping=true;needCancel=true;query=false;idle=0;}
    }
    public synchronized void moveNotification(int error){
        if(!busy || stopping || arrived)return;
        if(error!=0){moveResponse(error);return;}
        arrived=true;query=false;idle=0;nextQuery=clock.now()+150;state="verifying";message="پیام پایان مسیر رسید؛ در حال تأیید وضعیت بیکار SDK.";
    }
    private static int responseInteger(Object value){
        if(value instanceof Number){
            double number=((Number)value).doubleValue();
            int integer=(int)number;
            return number==integer?integer:-1;
        }
        // SDK ممکن است رقم‌های عددی را با زبان دستگاه تولید کند.
        if(value instanceof String)try{return Integer.parseInt(((String)value).trim());}
        catch(NumberFormatException ignored){return -1;}
        return -1;
    }
    public synchronized void statusResponse(Object errorCode,Object stateValue){
        if(!query)return;query=false;long now=clock.now();nextQuery=now+500;
        int error=responseInteger(errorCode),value=responseInteger(stateValue);
        if(error!=0 || (value!=0 && value!=1)){idle=0;ready=false;return;}
        if(value!=0){idle=0;ready=false;if(!busy){external=true;state="checking";message="SDK یک ناوبری دیگر را فعال گزارش می‌کند؛ منتظر پایان آن بمان.";}if(busy && !stopping && !arrived){state="navigating";message="SDK ناوبری فعال گزارش می‌کند.";}return;}
        lastIdle=now;
        if(busy && !arrived && !stopping)return; // رسیدن به مقصد به اعلان جداگانه نیاز دارد.
        if(!busy && ready && !external){nextQuery=now+1200;return;}
        // دو پاسخ بیکار لازم است تا مسیر قبلی از حالت معلق خارج شود.
        idle++;
        if(idle<2)return;
        ready=true;busy=false;external=false;query=false;needCancel=false;persistence.pending(false);
        if(stopping){state="stopped";message="SDK در دو بررسی بیکار گزارش شد؛ آمادهٔ فرمان بعدی.";}
        else if(arrived){state="arrived";message="رسیدن با پیام پایان مسیر و دو بررسی بیکار SDK تأیید شد.";}
        else{state="ready";message="SDK در دو بررسی بیکار است؛ مقصد را انتخاب کن.";}
        stopping=false;arrived=false;deadline=0;nextQuery=now+1200;
    }
    public synchronized void tick(boolean sdkReady,boolean manualQuiet){
        long now=clock.now();
        if(busy && !stopping && (now>=lease || now>=deadline)){cancel();}
        if(!sdkReady){ready=false;return;}
        if(stopping && (needCancel || now>=nextCancel)){
            sender.send("{\"msg_id\":\"NAVI_ROBOT_CANCEL_REQ\"}");needCancel=false;nextCancel=now+2000;
        }
        if(!manualQuiet && !busy){ready=false;idle=0;query=false;return;}
        if(query && now-queryAt>=2500){query=false;idle=0;ready=false;nextQuery=now+500;}
        if(!query && now>=nextQuery){
            query=true;queryAt=now;nextQuery=now+2500;
            if(!sender.send("{\"msg_id\":\"NAVI_GET_STATUS_REQ\"}")){query=false;idle=0;ready=false;nextQuery=now+1000;}
        }
    }
    public synchronized void close(){if(busy){cancel();sender.send("{\"msg_id\":\"NAVI_ROBOT_CANCEL_REQ\"}");}ready=false;}
}
