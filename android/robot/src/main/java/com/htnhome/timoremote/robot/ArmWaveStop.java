package com.htnhome.timoremote.robot;

/** درخواست توقف تکرار حرکت بازو با دو فرمان شناخته‌شدهٔ SDK. */
final class ArmWaveStop {
    static int request(HeadControl.Sender send) {
        boolean sdkLoop = send.send("{\"msg_id\":\"ROBOT_ARM_LOOP_STOP_REQ\"}");
        boolean boardLoop = send.send("{\"msg_id\":\"ROBOT_ARM_LOOP_STOP_BY_MAIN_BORAD_REQ\"}");
        return (sdkLoop ? 1 : 0) + (boardLoop ? 1 : 0);
    }
}
