package com.htnhome.timoremote.robot;

public final class ControlTimingTest {
    private static int count=0;
    private static void check(long actual,long expected,String text){count++;if(actual!=expected)throw new AssertionError(text+": "+actual);}
    public static void main(String[] args){
        // The server advertises a budget AFTER waiting 650ms. Deducting this
        // wait again leaves 300ms, less than the next long poll, and kills media.
        check(ControlTiming.remaining(1100,800,650),950,"server wait is not charged twice");
        check(ControlTiming.remaining(1100,800,0),300,"older gateway remains conservative");
        check(ControlTiming.remaining(1200,800,650),1050,"command TTL uses the same reply-time origin");
        check(ControlTiming.remaining(500,800,150),0,"actual network delay can still expire a lease");
        check(ControlTiming.remaining(0,100,100),0,"no owner cannot gain a lease");
        check(ControlTiming.remaining(1200,50,500),1200,"wait cannot exceed round trip");
        check(ControlTiming.remaining(1200,1500,99999),700,"untrusted wait is bounded");
        check(ControlTiming.remaining(1200,200,-1),1000,"negative wait ignored");
        check(ControlTiming.remaining(1200,-1,0),1200,"negative elapsed clamped");
        check(ControlTiming.remaining(-100,0,0),0,"negative advertised budget clamped");
        System.out.println("ControlTiming: "+count+" checks passed (fake timing; no hardware)");
    }
}
