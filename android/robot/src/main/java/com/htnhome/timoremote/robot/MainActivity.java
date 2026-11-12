package com.htnhome.timoremote.robot;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.text.InputType;
import android.view.View;
import android.view.WindowManager;
import android.widget.*;
import java.net.URI;

/** چرخهٔ عمر اپ همراه و تنظیمات اتصال ذخیره‌شده روی ربات. */
public class MainActivity extends Activity {
    private FaceView face;private FrameLayout screen;private ScrollView setupPanel;private boolean showingSetup=false;
    private SdkBridge sdk;private RobotAgent agent;private EditText address,token,cameraId;
    private TextView status;private Button connect;private boolean pendingPermission=false;
    private final Handler ui=new Handler();
    private volatile boolean foreground=false;
    private boolean pausedByUser=false,permissionAsked=false;private LinearLayout advanced;
    private final java.util.concurrent.atomic.AtomicInteger stopping=new java.util.concurrent.atomic.AtomicInteger();
    @Override public void onCreate(Bundle saved){super.onCreate(saved);sdk=new SdkBridge(this);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        ScrollView scroll=new ScrollView(this);LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(48,36,48,36);box.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);scroll.addView(box);box.setBackgroundColor(Color.rgb(242,247,250));
        TextView title=new TextView(this);title.setText("تیمو ریموت · اتصال ربات");title.setTextSize(26);title.setTextColor(Color.rgb(18,70,89));box.addView(title);
        TextView help=new TextView(this);help.setText("برای راه‌اندازی، در برنامهٔ ویندوز «اتصال ربات» را بزن. تنظیمات خودکار ارسال و ذخیره می‌شوند. دفعات بعد با بازکردن این اپ، اتصال دوباره برقرار می‌شود.");help.setPadding(0,16,0,20);box.addView(help);
        Button settings=new Button(this);settings.setText("تنظیمات پیشرفته");box.addView(settings);
        advanced=new LinearLayout(this);advanced.setOrientation(LinearLayout.VERTICAL);box.addView(advanced);advanced.setVisibility(View.GONE);
        settings.setOnClickListener(v->advanced.setVisibility(advanced.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE));
        address=field(advanced,"آدرس سرویس کنترل","تنظیم خودکار از ویندوز",false);
        token=field(advanced,"Robot Token","تنظیم خودکار از ویندوز",true);
        cameraId=field(advanced,"شناسهٔ دوربین (اختیاری)","خالی = انتخاب خودکار دوربین",false);
        android.content.SharedPreferences prefs=getPreferences(MODE_PRIVATE);
        address.setText(prefs.getString("url",""));token.setText(prefs.getString("token",""));cameraId.setText(prefs.getString("camera",""));
        connect=new Button(this);connect.setText("اتصال ربات به ریموت");box.addView(connect);
        connect.setOnClickListener(v->{if(agent!=null){pausedByUser=true;disconnect();return;}pausedByUser=false;startConnection();});
        Button backToFace=new Button(this);backToFace.setText("بازگشت به چهرهٔ تیمو");box.addView(backToFace);backToFace.setOnClickListener(v->showSetup(false));
        status=new TextView(this);status.setPadding(0,24,0,24);status.setTextIsSelectable(true);box.addView(status);
        screen=new FrameLayout(this);screen.setBackgroundColor(Color.rgb(27,27,27));face=new FaceView(this);
        screen.addView(face,new FrameLayout.LayoutParams(-1,-1));setupPanel=scroll;screen.addView(scroll,new FrameLayout.LayoutParams(-1,-1));scroll.setVisibility(View.GONE);
        Button gear=new Button(this);gear.setText("⚙");gear.setTextSize(23);gear.setTextColor(Color.rgb(123,147,159));gear.setBackgroundColor(Color.TRANSPARENT);gear.setContentDescription("تنظیمات اتصال ربات");
        int side=(int)(56*getResources().getDisplayMetrics().density);FrameLayout.LayoutParams gearLayout=new FrameLayout.LayoutParams(side,side,android.view.Gravity.TOP|android.view.Gravity.END);screen.addView(gear,gearLayout);gear.setOnClickListener(v->showSetup(!showingSetup));
        setContentView(screen);immersive();
        ui.post(new Runnable(){@Override public void run(){status.setText(agent!=null?agent.status:("SDK: "+sdk.lastMessage+"\n"+(hasSettings()?"اتصال آماده است؛ دوربین و میکروفون خاموش‌اند.":"در ویندوز دکمهٔ اتصال ربات را بزن.")));ui.postDelayed(this,1000);}});
    }
    private EditText field(LinearLayout box,String label,String hint,boolean secret){
        TextView text=new TextView(this);text.setText(label);text.setPadding(0,12,0,4);box.addView(text);
        EditText edit=new EditText(this);edit.setSingleLine(true);edit.setHint(hint);edit.setTextDirection(View.TEXT_DIRECTION_LTR);
        edit.setInputType(InputType.TYPE_CLASS_TEXT|(secret?InputType.TYPE_TEXT_VARIATION_PASSWORD:InputType.TYPE_TEXT_VARIATION_URI));box.addView(edit);return edit;
    }
    public static boolean validOrigin(String value){
        try{URI u=new URI(value);String scheme=u.getScheme(),host=u.getHost();
            if(host==null || u.getUserInfo()!=null || u.getQuery()!=null || u.getFragment()!=null || (u.getPath()!=null && !u.getPath().isEmpty() && !"/".equals(u.getPath())))return false;
            if("https".equals(scheme))return true;if(!"http".equals(scheme))return false;
            if("localhost".equals(host))return true;
            String[] a=host.split("\\.");if(a.length!=4)return false;int[] ip=new int[4];
            for(int i=0;i<4;i++){if(!a[i].matches("[0-9]{1,3}"))return false;ip[i]=Integer.parseInt(a[i]);if(ip[i]>255)return false;}
            return ip[0]==10 || ip[0]==127 || (ip[0]==192 && ip[1]==168) || (ip[0]==172 && ip[1]>=16 && ip[1]<=31);
        }catch(Exception e){return false;}
    }
    private void startConnection(){
        if(agent!=null || pendingPermission)return;
        if(stopping.get()>0){Toast.makeText(this,"در حال پایان‌دادن به اتصال قبلی؛ لحظه‌ای صبر کن.",Toast.LENGTH_SHORT).show();return;}
        String url=address.getText().toString().trim().replaceAll("/+$","");String secret=token.getText().toString().trim();
        if(!validOrigin(url) || !secret.matches("[A-Za-z0-9_-]{24,200}")){Toast.makeText(this,"در برنامهٔ ویندوز، اتصال ربات را بزن.",Toast.LENGTH_LONG).show();return;}
        if(!permissionAsked && (checkSelfPermission(Manifest.permission.CAMERA)!=PackageManager.PERMISSION_GRANTED || checkSelfPermission(Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED)){
            permissionAsked=true;pendingPermission=true;requestPermissions(new String[]{Manifest.permission.CAMERA,Manifest.permission.RECORD_AUDIO},105);return;
        }
        connectNow(url,secret);
    }
    private void connectNow(String url,String secret){
        getPreferences(MODE_PRIVATE).edit().putString("url",url).putString("token",secret).putString("camera",cameraId.getText().toString().trim()).apply();
        sdk.connect();agent=new RobotAgent(this,url,secret,cameraId.getText().toString().trim(),sdk,getPreferences(MODE_PRIVATE).getString("fallback",""));RobotAgent connected=agent;agent.setFaceListener(value->runOnUiThread(()->{if(agent==connected && foreground)face.expression(value);}));agent.start();connect.setText("قطع اتصال ریموت");address.setEnabled(false);token.setEnabled(false);cameraId.setEnabled(false);
    }
    @Override public void onRequestPermissionsResult(int code,String[] permissions,int[] grants){
        super.onRequestPermissionsResult(code,permissions,grants);
        if(code==105 && pendingPermission){pendingPermission=false;
            // رد مجوز یک حسگر، اتصال و استفاده از کنترل‌های دیگر را مختل نمی‌کند.
            if(foreground)startConnection();}
    }
    private void disconnect(){if(face!=null)face.expression("normal");if(agent!=null){RobotAgent old=agent;agent=null;stopping.incrementAndGet();old.stop(()->{if(stopping.decrementAndGet()==0 && !foreground)sdk.close();});}connect.setText("اتصال ربات به ریموت");address.setEnabled(true);token.setEnabled(true);cameraId.setEnabled(true);}
    private boolean hasSettings(){return validOrigin(address.getText().toString().trim()) && token.getText().toString().trim().matches("[A-Za-z0-9_-]{24,200}");}
    private void autoConnect(){
        if(!foreground || pausedByUser || agent!=null || pendingPermission || !hasSettings())return;
        if(stopping.get()>0){ui.postDelayed(this::autoConnect,150);return;}startConnection();
    }
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);
        if("com.htnhome.timoremote.robot.RECONNECT".equals(intent.getAction())){
            pausedByUser=false;disconnect();android.content.SharedPreferences prefs=getPreferences(MODE_PRIVATE);
            address.setText(prefs.getString("url",""));token.setText(prefs.getString("token",""));ui.postDelayed(this::autoConnect,650);
        }
    }
    private void immersive(){getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_LAYOUT_STABLE);}
    private void showSetup(boolean value){showingSetup=value;setupPanel.setVisibility(value?View.VISIBLE:View.GONE);immersive();}
    @Override public void onBackPressed(){if(showingSetup)showSetup(false);else super.onBackPressed();}
    @Override public void onWindowFocusChanged(boolean focus){super.onWindowFocusChanged(focus);if(focus)immersive();}
    @Override protected void onResume(){super.onResume();if(face!=null)face.onResume();immersive();foreground=true;sdk.connect();ui.postDelayed(this::autoConnect,200);}
    @Override protected void onPause(){if(face!=null)face.onPause();foreground=false;disconnect();if(stopping.get()==0)sdk.close();super.onPause();}
    @Override protected void onDestroy(){if(face!=null){screen.removeView(face);face.close();}ui.removeCallbacksAndMessages(null);if(stopping.get()==0)sdk.close();super.onDestroy();}
}
