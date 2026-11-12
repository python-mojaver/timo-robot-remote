package com.htnhome.timoremote.robot;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class ArmWaveStopTest {
    public static void main(String[] args) {
        List<String> packets = new ArrayList<>();
        int delivered = ArmWaveStop.request(packet -> {
            packets.add(packet);
            return packets.size() == 2;
        });
        if (delivered != 1 || !packets.equals(Arrays.asList(
                "{\"msg_id\":\"ROBOT_ARM_LOOP_STOP_REQ\"}",
                "{\"msg_id\":\"ROBOT_ARM_LOOP_STOP_BY_MAIN_BORAD_REQ\"}"))) {
            throw new AssertionError("Both stop-only requests must be attempted exactly once");
        }
        if (ArmWaveStop.request(packet -> true) != 2 || ArmWaveStop.request(packet -> false) != 0) {
            throw new AssertionError("The result must count transport submissions");
        }
        System.out.println("Arm wave-stop requests verified with a simulated transport");
    }
}
