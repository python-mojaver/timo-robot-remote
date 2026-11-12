package com.htnhome.timoremote.robot;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.os.IBinder;
import android.os.Parcel;
import android.util.Log;

/** پل Binder میان اپ همراه و سرویس SDK نصب‌شده روی ربات. */
public final class SdkBridge {
    private final Context context;
    public interface Receiver {void receive(String raw);}
    private volatile Receiver receiver;
    public void setReceiver(Receiver value){receiver=value;}
    public void clearReceiver(Receiver value){if(receiver==value)receiver=null;}
    private volatile IBinder binder;
    private boolean bound;
    public volatile String lastMessage = "SDK not connected";
    public static volatile SdkBridge current;
    public SdkBridge(Context context) {this.context=context;current=this;}
    private final ServiceConnection connection = new ServiceConnection() {
        @Override public void onServiceConnected(ComponentName name, IBinder service) {
            binder=service;
            if (!call(1,context.getPackageName())) binder=null;
            lastMessage=ready()?"SDK connected":"SDK handshake failed";
        }
        @Override public void onServiceDisconnected(ComponentName name) {binder=null;lastMessage="SDK disconnected";}
    };
    public void connect() {
        current=this;if(bound)return;
        try {bound=context.bindService(new Intent().setComponent(new ComponentName("com.csjbot.robotsdk.ten",
            "com.csjbot.robotsdk.service.RobotSdkService")),connection,Context.BIND_AUTO_CREATE);}
        catch(Exception e){lastMessage=e.getClass().getSimpleName();}
    }
    public boolean ready(){IBinder b=binder;return b!=null && b.isBinderAlive();}
    private boolean call(int transaction,String value) {
        IBinder b=binder;if(b==null)return false;
        Parcel in=Parcel.obtain(),out=Parcel.obtain();
        try {in.writeInterfaceToken("com.csjbot.sdkhandler.IAarToSdkApp");in.writeString(value);
            if(!b.transact(transaction,in,out,0))return false;out.readException();return true;}
        catch(Exception e){lastMessage="SDK: "+e.getClass().getSimpleName();return false;}
        finally{in.recycle();out.recycle();}
    }
    public boolean send(String json){return ready() && call(2,json);}
    public static void registered(){
        SdkBridge instance=current;
        if(instance!=null)instance.lastMessage="SDK callback registration succeeded";
    }
    public static void received(String text){
        if(text==null)return;
        SdkBridge instance=current;
        Receiver next=instance==null?null:instance.receiver;
        if(instance!=null){
            instance.lastMessage=text.length()>400?text.substring(0,400):text;
            Log.i("TIMO_REMOTE_SDK",instance.lastMessage);
        }
        if(next!=null)next.receive(text);
        else if(text.contains("NAVI_GET_STATUS_RSP")){
            Log.w("TIMO_REMOTE_SDK","Navigation status callback arrived without an active receiver");
        }
    }
    public void close(){if(bound)try{context.unbindService(connection);}catch(Exception ignored){}bound=false;binder=null;if(current==this)current=null;}
}
