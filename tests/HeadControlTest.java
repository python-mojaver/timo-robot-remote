package com.htnhome.timoremote.robot;
import java.util.ArrayList;

public final class HeadControlTest {
    static final class Time implements HeadControl.Clock {long now=1000;public long now(){return now;}}
    static final class Transport implements HeadControl.Sender {
        ArrayList<String> sent=new ArrayList<>();boolean ok=true;
        public boolean send(String text){sent.add(text);return ok;}
    }
    static int checks=0;
    static void check(boolean ok,String message){checks++;if(!ok)throw new AssertionError(message);}
    public static void main(String[] args){
        Time t=new Time();Transport s=new Transport();
        for(String profile:new String[]{"","robot_action_old","other"}){
            HeadControl unsupported=new HeadControl(s,t,profile);unsupported.lease(1600);
            check(!unsupported.supported(),"unknown/combined/legacy controller disabled");
            check(!unsupported.command("left",1,3000),"unsupported cannot send");
        }
        check(s.sent.isEmpty(),"no automatic command during detection/construction");
        HeadControl h=new HeadControl(s,t,"robot_action_new");
        check(h.supported(),"known head-only packet profile");
        check(!h.command("left",1,3000),"no owner cannot turn head");h.lease(1600);
        check(!h.command("invalid",1,3000),"invalid direction rejected");
        check(!h.command("left",1,t.now),"expired command rejected");
        check(h.command("left",1,3000),"finite head command accepted");
        check(s.sent.get(0).contains("\"part\":2,\"direction\":1,\"angle\":5,\"speed\":3"),"left uses head yaw only");
        check(!h.command("right",2,3000),"rapid requests cannot accumulate");
        t.now+=701;h.lease(1600);
        check(!h.command("left",1,4000),"duplicate sequence cannot replay");
        check(h.command("up",2,4000),"pitch command accepted");
        check(s.sent.get(1).contains("\"part\":1,\"direction\":1,\"angle\":3"),"up uses head pitch only");
        t.now+=701;h.lease(1600);
        check(h.command("left",3,5000),"second requested yaw target");
        t.now+=701;h.lease(1600);check(h.command("left",4,6000),"third requested yaw target");
        t.now+=701;h.lease(1600);int count=s.sent.size();
        check(!h.command("left",5,7000),"requested target bounded at 15");
        check(s.sent.size()==count,"endpoint does not emit movement");
        h.barrier(10);check(!h.command("right",9,7000),"pre-stop head command invalidated");
        check(h.command("center",11,7000),"head-only neutral targets");
        check(s.sent.get(s.sent.size()-2).contains("\"part\":2"),"neutral yaw");
        check(s.sent.get(s.sent.size()-1).contains("\"part\":1"),"neutral pitch");
        for(String text:s.sent){
            check(text.contains("ROBOT_BODY_CTRL_CMD"),"no navigation/full-body-reset packet");
            check(!text.contains("ctrl_angles") && !text.contains("body_part"),"no arm or legacy action packet");
        }
        t.now+=701;h.lease(0);check(!h.command("down",12,9000),"lost lease disables head");
        h.lease(1600);s.ok=false;check(!h.command("down",12,9000),"failed transport reported");
        check(h.diagnostic().contains("pitch=0"),"failed submission does not advance requested target");
        Time ct=new Time();Transport cs=new Transport();HeadControl combined=new HeadControl(cs,ct,"robot_action_ctrl_x");
        check(!combined.supported() && combined.coupled(),"ctrl_x is recognized and blocked");
        combined.lease(1600);
        for(String direction:new String[]{"left","right","up","down","center"}){
            check(!combined.command(direction,1,3000),"ctrl_x cannot send "+direction);
        }
        check(cs.sent.isEmpty(),"no combined head or arm packet");
        check(combined.notice().contains("غیرفعال"),"the operator sees why head control is unavailable");
        System.out.println("HeadControl: "+checks+" checks passed (fake transport; no hardware)");
    }
}
