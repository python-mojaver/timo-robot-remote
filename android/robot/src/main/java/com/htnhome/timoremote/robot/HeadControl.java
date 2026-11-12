package com.htnhome.timoremote.robot;

/** هدف‌های محدود حرکت سر برای پروفایل robot_action_new. مقدارها هدف فرمان‌اند. */
public final class HeadControl {
    public interface Sender {boolean send(String json);}
    public interface Clock {long now();}
    private final Sender sender;private final Clock clock;private final String profile;
    private int yaw=0,pitch=0;private long lease=0,lastSequence=0,nextCommand=0;
    private boolean hasRequest=false;
    public HeadControl(Sender sender,Clock clock,String profile){this.sender=sender;this.clock=clock;this.profile=profile==null?"":profile;}
    public boolean coupled(){return "robot_action_ctrl_x".equals(profile);}
    public boolean supported(){return "robot_action_new".equals(profile);}
    public synchronized void lease(long remaining){lease=clock.now()+Math.max(0,Math.min(1600,remaining));}
    public synchronized void barrier(long sequence){lastSequence=Math.max(lastSequence,sequence);}
    public synchronized boolean command(String direction,long sequence,long validUntil){
        if(!supported() || sequence<=lastSequence || clock.now()>=lease || clock.now()>=validUntil || clock.now()<nextCommand)return false;
        int newYaw=yaw,newPitch=pitch;
        if("left".equals(direction))newYaw=Math.max(-15,yaw-5);
        else if("right".equals(direction))newYaw=Math.min(15,yaw+5);
        else if("up".equals(direction))newPitch=Math.max(-6,pitch-3);
        else if("down".equals(direction))newPitch=Math.min(6,pitch+3);
        else if("center".equals(direction)){newYaw=0;newPitch=0;}
        else return false;
        // هر کلیک یک گام دارد. در انتهای دامنه فرمان تکراری ارسال نمی‌شود.
        if(!"center".equals(direction) && newYaw==yaw && newPitch==pitch)return false;
        lastSequence=sequence;nextCommand=clock.now()+700;
        if("center".equals(direction)){
            // فرمان بازنشانی عمومی بازوها را هم حرکت می‌دهد. اینجا فقط دو محور سر را تنظیم می‌کنیم.
            if(!sender.send(packet(2,0)))return false;
            yaw=0;hasRequest=true;
            if(clock.now()>=lease || clock.now()>=validUntil || !sender.send(packet(1,0)))return false;
            pitch=0;return true;
        }
        boolean horizontal="left".equals(direction)||"right".equals(direction);
        if(!sender.send(packet(horizontal?2:1,horizontal?newYaw:newPitch)))return false;
        yaw=newYaw;pitch=newPitch;hasRequest=true;return true;
    }
    private static String packet(int part,int target){
        // مقادیر بخش، جهت و سرعت با نگاشت کنترل سر در SDK یکسان‌اند.
        return "{\"msg_id\":\"ROBOT_BODY_CTRL_CMD\",\"part\":"+part+",\"direction\":"+(target<=0?1:2)+",\"angle\":"+Math.abs(target)+",\"speed\":3}";
    }
    public synchronized String diagnostic(){return "Head profile="+(profile.isEmpty()?"unknown":profile)+"; requested yaw="+yaw+", pitch="+pitch+"; requested="+hasRequest+"; physical position not measured";}
    public String notice(){
        if(coupled())return "کنترل سر در پروفایل ctrl_x غیرفعال است. فرمان این پروفایل بازوها را هم حرکت می‌دهد.";
        if(supported())return "هر کلیک یک تغییر کوتاه در هدف سر؛ دکمه را نگه ندار.";
        if(profile.isEmpty())return "نوع کنترل سر شناسایی نشده؛ با ADB متصل، اتصال ربات را دوباره بزن.";
        return "نوع کنترل سر این دستگاه هنوز پشتیبانی نمی‌شود؛ گزارش وضعیت را بفرست.";
    }
}
