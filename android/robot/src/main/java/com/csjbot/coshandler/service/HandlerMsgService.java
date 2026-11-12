package com.csjbot.coshandler.service;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Binder;
import android.os.IBinder;
import android.os.Parcel;
import android.os.RemoteException;
import android.util.Log;
import com.htnhome.timoremote.robot.SdkBridge;

/** دریافت پاسخ SDK با نام سرویسی که سازنده برای Binder انتظار دارد. */
public class HandlerMsgService extends Service {
    private static final String TAG="TIMO_REMOTE_SDK";
    private static final String SDK_PACKAGE="com.csjbot.robotsdk.ten";

    private boolean isSdkCaller(int callerUid) {
        long identity=Binder.clearCallingIdentity();
        try {
            return getPackageManager().getPackageUid(SDK_PACKAGE,0)==callerUid;
        } catch(PackageManager.NameNotFoundException error) {
            Log.w(TAG,"SDK package UID unavailable");
            return false;
        } finally {
            Binder.restoreCallingIdentity(identity);
        }
    }

    private final Binder callback=new Binder(){
        @Override protected boolean onTransact(int code,Parcel data,Parcel reply,int flags) throws RemoteException {
            if(code==INTERFACE_TRANSACTION){reply.writeString("com.csjbot.sdkhandler.ISdkAppToAar");return true;}
            if(code==1 || code==2){
                int callerUid=Binder.getCallingUid();
                if(!isSdkCaller(callerUid)){
                    Log.w(TAG,"SDK callback rejected for UID "+callerUid);
                    throw new SecurityException("SDK callback only");
                }
                data.enforceInterface("com.csjbot.sdkhandler.ISdkAppToAar");
                if(code==1)SdkBridge.received(data.readString());
                // تراکنش ۲ فقط تأیید ثبت callback است و بدنهٔ پیام ندارد.
                else {
                    Log.i(TAG,"SDK callback registration succeeded");
                    SdkBridge.registered();
                }
                if(reply!=null)reply.writeNoException();return true;
            }
            return super.onTransact(code,data,reply,flags);
        }
    };
    @Override public void onCreate(){
        super.onCreate();String id="timo_remote_sdk";
        NotificationManager manager=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel(id,"Timo Remote SDK",NotificationManager.IMPORTANCE_LOW));
        startForeground(20,new Notification.Builder(this,id).setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentTitle("Timo Remote").setContentText("اتصال مستقل به سرویس ربات").build());
    }
    @Override public IBinder onBind(Intent intent){
        Log.i(TAG,"SDK callback service bound");
        return callback;
    }
    @Override public int onStartCommand(Intent intent,int flags,int id){return START_NOT_STICKY;}
}
