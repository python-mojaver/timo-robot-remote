package com.htnhome.timoremote.robot;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** دریافت تنظیمات اتصال از ADB با مجوز DUMP اندروید. */
public final class SetupReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent){
        if(!"com.htnhome.timoremote.robot.CONFIGURE".equals(intent.getAction())){setResultCode(0);return;}
        String url=intent.getStringExtra("url"),token=intent.getStringExtra("token"),fallback=intent.getStringExtra("fallback");
        if(url==null || token==null || !MainActivity.validOrigin(url) || !token.matches("[A-Za-z0-9_-]{24,200}")){
            setResultCode(0);setResultData("invalid settings");return;
        }
        if(fallback==null || !fallback.matches("http://127\\.0\\.0\\.1:[0-9]{4,5}"))fallback="";
        String headProfile=intent.getStringExtra("head_profile");
        if(!"robot_action_new".equals(headProfile) && !"robot_action_old".equals(headProfile) && !"robot_action_ctrl_x".equals(headProfile))headProfile="";
        boolean stored=context.getSharedPreferences("MainActivity",Context.MODE_PRIVATE).edit()
            .putString("url",url).putString("token",token).putString("fallback",fallback).putString("head_profile",headProfile).commit();
        setResultCode(stored?1:0);setResultData(stored?"configured":"settings not saved");
    }
}
