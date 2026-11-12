package com.htnhome.timoremote.robot;

/** مهلت دریافتی با درنظرگرفتن زمان رفت‌وبرگشت درخواست محاسبه می‌شود. */
public final class ControlTiming {
    private ControlTiming() {}
    public static long remaining(long advertised,long roundTrip,long serverWait) {
        long elapsed=Math.max(0,roundTrip);
        // فقط انتظار اندازه‌گیری‌شدهٔ سرور از زمان درخواست کم می‌شود.
        long wait=Math.min(elapsed,Math.max(0,Math.min(1000,serverWait)));
        return Math.max(0,advertised-(elapsed-wait));
    }
}
