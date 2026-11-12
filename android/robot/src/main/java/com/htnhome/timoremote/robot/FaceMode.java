package com.htnhome.timoremote.robot;

/** حالت‌های مجاز برای نمایشگر چهره. */
public final class FaceMode {
    private FaceMode(){}
    public static boolean valid(String value){
        return "normal".equals(value)||"happy".equals(value)||"sad".equals(value)||"upset".equals(value)||"surprised".equals(value);
    }
}
