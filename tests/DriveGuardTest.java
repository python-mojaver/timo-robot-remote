package com.htnhome.timoremote.robot;
import java.util.ArrayList;
public class DriveGuardTest {
    static class Time implements DriveGuard.Clock {long value=1000;public long now(){return value;}}
    static class Transport implements DriveGuard.Sender {
        ArrayList<String> sent=new ArrayList<>();boolean ok=true;
        public boolean send(String json){sent.add(json);return ok;}
    }
    static int count=0;
    static void check(boolean condition,String text){count++;if(!condition)throw new AssertionError(text);}
    public static void main(String[] args){
        Time t=new Time();Transport s=new Transport();DriveGuard g=new DriveGuard(s,t);
        check(!g.drive("forward",1,2000),"no lease no movement");g.lease(1500);
        String[] names={"forward","backward","left","right"};
        for(int i=0;i<4;i++){
            check(g.drive(names[i],i+1,2200),"direction accepted");
            check(s.sent.get(s.sent.size()-1).contains("\"direction\":"+i),"SDK mapping");
        }
        check(!g.drive("left",4,2200),"duplicate sequence rejected");
        check(!g.drive("invalid",5,2200),"invalid direction rejected");
        t.value+=551;g.tick();check(s.sent.get(s.sent.size()-1).equals(DriveGuard.STOP),"watchdog manual cancel");
        check(DriveGuard.STOP.contains("NAVI_GET_CANCEL_REQ"),"current action cancel");
        g.stopBarrier(10);check(!g.drive("forward",9,2200),"late pre-stop rejected");
        check(g.drive("forward",11,2200),"intentional new direction");int n=s.sent.size();
        t.value+=101;g.tick();check(s.sent.size()==n,"old stop retries do not cancel new drive");
        check(!g.drive("right",12,t.value),"expired command");
        g.lease(0);g.tick();check(s.sent.get(s.sent.size()-1).equals(DriveGuard.STOP),"lease loss cancels");
        g.lease(1500);s.ok=false;check(!g.drive("forward",13,3000),"failed transport");
        s.ok=true;t.value+=101;g.tick();check(s.sent.get(s.sent.size()-1).equals(DriveGuard.STOP),"failed stop retried");
        check(!g.moving(),"submission state cleared");
        System.out.println("DriveGuard: "+count+" checks passed (fake transport; no hardware)");
    }
}
