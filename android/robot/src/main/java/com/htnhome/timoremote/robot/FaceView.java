package com.htnhome.timoremote.robot;

import android.content.Context;
import android.graphics.Color;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;

/** نمایش چهرهٔ SVG از فایل داخلی اپ در WebView آفلاین. */
public final class FaceView extends WebView {
    private String expression="normal";private boolean loaded=false,closed=false;
    public FaceView(Context context){super(context);
        setBackgroundColor(Color.rgb(27,27,27));setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
        setContentDescription("چهرهٔ تیمو: معمولی");
        getSettings().setJavaScriptEnabled(true);getSettings().setAllowFileAccess(false);getSettings().setAllowContentAccess(false);getSettings().setBlockNetworkLoads(true);getSettings().setDomStorageEnabled(false);
        setVerticalScrollBarEnabled(false);setHorizontalScrollBarEnabled(false);setOverScrollMode(OVER_SCROLL_NEVER);
        setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view,String url){return true;}
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest req){return true;}
            @Override public void onPageFinished(WebView view,String url){if(!closed){loaded=true;apply();}}
        });
        try(InputStream in=context.getAssets().open("face.html")){
            ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[4096];int n;
            while((n=in.read(b))!=-1)out.write(b,0,n);
            loadDataWithBaseURL("https://timo-face.invalid/",out.toString("UTF-8"),"text/html","UTF-8",null);
        }catch(Exception error){setContentDescription("فایل چهره بارگذاری نشد");}
    }
    public void expression(String value){if(closed||!FaceMode.valid(value))return;expression=value;setContentDescription("چهرهٔ تیمو: "+value);apply();}
    private void apply(){if(loaded&&!closed)evaluateJavascript("window.setTimoExpression('"+expression+"')",null);}
    public void close(){closed=true;stopLoading();destroy();}
}
