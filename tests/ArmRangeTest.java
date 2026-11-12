package com.htnhome.timoremote.robot;

import java.util.ArrayList;
import java.util.List;

public final class ArmRangeTest {
    private static void check(boolean result) {
        if (!result) throw new AssertionError();
    }

    public static void main(String[] args) {
        long[] now = {100};
        List<String> packets = new ArrayList<>();
        ArmRange range = new ArmRange(packet -> packets.add(packet), () -> now[0]);
        range.lease(1600);
        check(range.apply("begin", "", -1, true, 1, 1000) == null);
        range.stop(true);
        check(range.apply("begin", "", -1, false, 1, 1000) == null);
        check(range.apply("begin", "", -1, true, 1, 1000) != null && packets.isEmpty());
        check(range.apply("move", "right", 100, true, 2, 1000) != null);
        check(range.right() == 2 && packets.get(0).contains("[49,65,25,27]"));
        check(range.apply("move", "right", 100, true, 3, 1000) == null);
        for (int i = 3; range.right() < 100; i++) {
            int before = range.right();
            now[0] += 1500;
            range.lease(1600);
            check(range.apply("move", "left", 90, true, i, now[0]+500) == null);
            check(range.apply("move", "right", 101, true, i, now[0]+500) == null);
            check(range.apply("move", "right", 100, false, i, now[0]+500) == null);
            check(range.apply("move", "right", 100, true, i, now[0]+500) != null);
            check(range.right() > before && range.right() - before <= 8);
        }
        check(packets.get(packets.size()-1).contains("[49,65,25,100]"));
        range.stop(true);
        check(range.active() && !range.armed());
        check(range.apply("rest", "right", 0, true, 99, now[0]+500) == null);
        now[0] += 1500;
        range.lease(1600);
        check(range.apply("begin", "", -1, true, 99, now[0]+500) != null);
        check(range.apply("move", "left", 3, true, 100, now[0]+500) != null);
        int count = packets.size();
        now[0] += 1500;
        range.lease(1600);
        check(range.apply("move", "left", 3, true, 101, now[0]+500) != null);
        check(packets.size() == count && range.left() == 3);
        range.lease(0);
        check(range.apply("rest", "left", 0, true, 102, now[0]+500) == null);
        range.lease(1600);
        check(!range.canFinish() && range.active());
        range.stop(true);
        now[0] += 1500;
        range.lease(1600);
        check(range.canFinish());
        check(range.apply("finish", "", -1, false, 102, now[0]+500) == null);
        check(range.apply("finish", "", -1, true, 102, now[0]+500) != null);
        check(!range.active() && range.left() == 0 && range.right() == 0 && packets.size() == count);
        range.stop(true);
        check(range.apply("begin", "", -1, true, 103, now[0]+500) != null);
        check(range.canFinish() && range.active());
        check(range.apply("finish", "", -1, true, 104, now[0]+500) != null && !range.active());
        System.out.println("Arm range: stop, confirmation, 2–100, bounded steps, side lock, SDK mapping and lease verified.");
    }
}
