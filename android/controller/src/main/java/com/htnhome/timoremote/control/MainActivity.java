package com.htnhome.timoremote.control;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.webkit.CookieManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/** پنل اندروید با ضبط صدا هنگام نگه‌داشتن دکمه در پیش‌زمینه. */
public class MainActivity extends Activity {
    private WebView browser;
    private Uri origin;private volatile boolean foreground=false;private volatile String talkId="";
    private final TalkMicrophone microphone=new TalkMicrophone(new TalkMicrophone.Sink(){
        public void pcm(String id,byte[] data){runOnUiThread(()->{if(foreground && id.equals(talkId) && trusted())browser.evaluateJavascript("window.timoTalkPCM("+org.json.JSONObject.quote(id)+","+org.json.JSONObject.quote(android.util.Base64.encodeToString(data,android.util.Base64.NO_WRAP))+");",null);});}
        public void error(String id,String text){runOnUiThread(()->{if(id.equals(talkId) && trusted())browser.evaluateJavascript("window.timoTalkError("+org.json.JSONObject.quote(id)+","+org.json.JSONObject.quote(text)+");",null);});}
    });
    private boolean trusted(){
        if(browser==null || origin==null)return false;
        Uri next=Uri.parse(browser.getUrl()==null?"":browser.getUrl());
        return origin.getScheme().equals(next.getScheme()) && origin.getHost().equals(next.getHost()) && origin.getPort()==next.getPort();
    }
    private void stopTalk(){talkId="";microphone.stop();}
    public final class TalkBridge {
        @android.webkit.JavascriptInterface public void start(String id){
            if(id==null || !id.matches("[a-f0-9]{32}"))return;
            runOnUiThread(()->{
                if(!foreground || !trusted())return;stopTalk();talkId=id;
                if(checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)!=android.content.pm.PackageManager.PERMISSION_GRANTED){
                    browser.evaluateJavascript("window.timoTalkError("+org.json.JSONObject.quote(id)+",\"مجوز میکروفون را تأیید کن؛ سپس دوباره کنترل را فعال و دکمه را نگه دار.\");",null);
                    requestPermissions(new String[]{android.Manifest.permission.RECORD_AUDIO},206);
                }else microphone.start(id);
            });
        }
        @android.webkit.JavascriptInterface public void stop(){runOnUiThread(()->stopTalk());}
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(16,24,32));
        getWindow().setNavigationBarColor(Color.rgb(16,24,32));
        showAddress();
    }

    private void showAddress() {
        stopTalk();
        if (browser != null) { browser.destroy(); browser = null; }
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(36,60,36,36);
        layout.setGravity(Gravity.CENTER_VERTICAL);
        layout.setBackgroundColor(Color.rgb(16,24,32));
        TextView title = new TextView(this);
        title.setText("کنترل تیمو"); title.setTextColor(Color.rgb(101,214,187)); title.setTextSize(28);
        layout.addView(title);
        TextView hint = new TextView(this);
        hint.setText("آدرس سرویس مستقل ریموت روی لپ‌تاپ را وارد کن؛ مثل http://192.168.1.50:8765");
        hint.setTextColor(Color.LTGRAY); hint.setPadding(0,20,0,24);layout.addView(hint);
        EditText address = new EditText(this);
        address.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        address.setSingleLine(true); address.setTextColor(Color.WHITE);
        address.setHint("http://192.168.1.50:8765");address.setHintTextColor(Color.GRAY);
        address.setText(getPreferences(MODE_PRIVATE).getString("url", ""));layout.addView(address);
        Button connect = new Button(this);connect.setText("بازکردن پنل کنترل");layout.addView(connect);
        connect.setOnClickListener(view -> {
            Uri uri = Uri.parse(address.getText().toString().trim());
            if (!validOrigin(uri.toString())) {
                address.setError("آدرس HTTPS یا HTTP با IP داخلی، بدون مسیر وارد کن.");return;
            }
            getPreferences(MODE_PRIVATE).edit().putString("url",uri.toString()).apply();
            open(uri);
        });
        setContentView(layout);
    }

    public static boolean validOrigin(String value){
        try{java.net.URI u=new java.net.URI(value);String scheme=u.getScheme(),host=u.getHost();
            if(host==null || u.getUserInfo()!=null || u.getQuery()!=null || u.getFragment()!=null || (u.getPath()!=null && !u.getPath().isEmpty() && !"/".equals(u.getPath())))return false;
            if("https".equals(scheme))return true;if(!"http".equals(scheme))return false;
            if("localhost".equals(host))return true;
            String[] a=host.split("\\.");if(a.length!=4)return false;int[] ip=new int[4];
            for(int i=0;i<4;i++){if(!a[i].matches("[0-9]{1,3}"))return false;ip[i]=Integer.parseInt(a[i]);if(ip[i]>255)return false;}
            return ip[0]==10 || ip[0]==127 || (ip[0]==192 && ip[1]==168) || (ip[0]==172 && ip[1]>=16 && ip[1]<=31);
        }catch(Exception e){return false;}
    }

    private void open(Uri address) {
        origin = address;
        browser = new WebView(this);
        WebSettings settings = browser.getSettings();
        settings.setJavaScriptEnabled(true);settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        settings.setSafeBrowsingEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(browser,false);
        browser.addJavascriptInterface(new TalkBridge(),"TimoTalk");
        browser.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri next = request.getUrl();
                if(request.isForMainFrame() && (!origin.getScheme().equals(next.getScheme()) || !origin.getHost().equals(next.getHost()) || origin.getPort()!=next.getPort()))stopTalk();
                return !origin.getScheme().equals(next.getScheme()) ||
                    !origin.getHost().equals(next.getHost()) || origin.getPort() != next.getPort();
            }
            // خطای گواهی با قواعد پیش‌فرض TLS بررسی می‌شود.
        });
        setContentView(browser);
        browser.loadUrl(address.toString());
    }

    @Override protected void onPause() {
        foreground=false;stopTalk();
        if (browser != null) {
            browser.evaluateJavascript("window.dispatchEvent(new Event('pagehide'));",null);
            browser.onPause(); browser.pauseTimers();
        }
        super.onPause();
    }
    @Override protected void onResume() {
        super.onResume();foreground=true;
        if (browser != null) { browser.onResume();browser.resumeTimers(); }
    }
    @Override public void onBackPressed() {
        if (browser == null) { super.onBackPressed();return; }
        browser.evaluateJavascript("window.dispatchEvent(new Event('pagehide'));",null);
        new AlertDialog.Builder(this).setMessage("بازگشت به تنظیم آدرس پنل؟ کنترل ربات آزاد می‌شود.")
            .setPositiveButton("تنظیم آدرس",(dialog,which)->showAddress())
            .setNegativeButton("بستن",(dialog,which)->finish()).show();
    }
    @Override protected void onDestroy() {
        stopTalk();
        if (browser != null) {browser.destroy();browser=null;}
        super.onDestroy();
    }
}
