package com.htnhome.timoremote.robot;

/** کنترل وضعیت حرکت پایه با مهلت کوتاه فرمان و شمارهٔ ترتیب. */
public final class DriveGuard {
    public interface Sender {boolean send(String json);}
    public interface Clock {long now();}
    private final Sender sender;private final Clock clock;
    private long lease=0,deadline=0,lastSequence=0,nextStop=0;private int stopRepeats=0;private boolean moving=false,pendingStop=false;
    public static final String STOP="{\"msg_id\":\"NAVI_GET_CANCEL_REQ\"}";
    public DriveGuard(Sender sender,Clock clock){this.sender=sender;this.clock=clock;}
    public synchronized void lease(long remaining){lease=clock.now()+Math.max(0,Math.min(1600,remaining));}
    public synchronized boolean moving(){return moving;}
    public synchronized boolean settled(){return !moving && !pendingStop && stopRepeats==0;}
    public synchronized boolean drive(String direction,long sequence,long validUntil){
        if(sequence<=lastSequence || clock.now()>=validUntil || clock.now()>=lease || pendingStop)return false;
        int number;
        if("forward".equals(direction))number=0;
        else if("backward".equals(direction))number=1;
        else if("left".equals(direction))number=2;
        else if("right".equals(direction))number=3;
        else return false;
        lastSequence=sequence;stopRepeats=0;moving=true;deadline=Math.min(lease,clock.now()+550);
        boolean ok=sender.send("{\"msg_id\":\"NAVI_ROBOT_MOVE_REQ\",\"direction\":"+number+"}");
        if(!ok)stop();return ok;
    }
    public synchronized boolean stop(){
        deadline=0;boolean ok=sender.send(STOP);pendingStop=!ok;moving=!ok;stopRepeats=3;nextStop=clock.now()+100;return ok;
    }
    public synchronized boolean stopBarrier(long sequence){lastSequence=Math.max(lastSequence,sequence);return stop();}
    public synchronized void tick(){
        if(moving && (clock.now()>=deadline || clock.now()>=lease)){stop();return;}
        if(stopRepeats>0 && clock.now()>=nextStop){pendingStop=!sender.send(STOP);moving=pendingStop;stopRepeats--;nextStop=clock.now()+100;}
    }
    public synchronized void close(){lease=0;if(moving || pendingStop)stop();}
}
