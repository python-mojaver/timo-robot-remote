package com.htnhome.timoremote.robot;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.graphics.ImageFormat;
import android.hardware.camera2.*;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.util.Size;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

/** دریافت فریم JPEG از Camera2 برای پنل ریموت. */
public final class RemoteCamera {
    public static final class Frame {public final byte[] bytes;public final long at;
        Frame(byte[] b){bytes=b;at=SystemClock.elapsedRealtime();}}
    private final Context context;private final CameraManager manager;private final String requested;
    private HandlerThread thread;private Handler handler;private CameraDevice device;
    private CameraCaptureSession session;private ImageReader reader;
    private volatile int generation=0;public volatile boolean active=false;public volatile String error="";
    private final AtomicReference<Frame> latest=new AtomicReference<>();
    public RemoteCamera(Context context,String requested){this.context=context;this.requested=requested;
        manager=(CameraManager)context.getSystemService(Context.CAMERA_SERVICE);}
    public boolean available(){try{return context.checkSelfPermission(Manifest.permission.CAMERA)==PackageManager.PERMISSION_GRANTED && manager.getCameraIdList().length>0;}catch(Exception e){return false;}}
    public String diagnostic(){try{return "Camera2 IDs: "+Arrays.toString(manager.getCameraIdList())+"; permission="+(context.checkSelfPermission(Manifest.permission.CAMERA)==PackageManager.PERMISSION_GRANTED);}catch(Exception e){return "Camera2: "+e.getClass().getSimpleName();}}
    public synchronized boolean start(){
        if(active)return true;if(!available()){error="دوربین در Camera2 دیده نمی‌شود یا مجوز دوربین داده نشده است.";return false;}
        stop();final int version=++generation;active=true;error="";
        thread=new HandlerThread("TimoRemoteCamera");thread.start();final Handler worker=new Handler(thread.getLooper());handler=worker;
        worker.post(()->{
            try{
                String[] ids=manager.getCameraIdList();String chosen=requested;
                if(chosen.isEmpty()){
                    chosen=ids[0];for(String id:ids){Integer facing=manager.getCameraCharacteristics(id).get(CameraCharacteristics.LENS_FACING);
                        if(facing!=null && facing==CameraCharacteristics.LENS_FACING_EXTERNAL){chosen=id;break;}}
                }
                Size[] sizes=manager.getCameraCharacteristics(chosen).get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP).getOutputSizes(ImageFormat.JPEG);
                if(sizes==null || sizes.length==0)throw new IllegalStateException("Camera has no JPEG output");
                Size best=sizes[0];long distance=Long.MAX_VALUE;
                for(Size size:sizes){long diff=Math.abs((long)size.getWidth()*size.getHeight()-640*480);if(diff<distance){distance=diff;best=size;}}
                final ImageReader images=ImageReader.newInstance(best.getWidth(),best.getHeight(),ImageFormat.JPEG,2);
                synchronized(RemoteCamera.this){if(version!=generation || !active){images.close();return;}reader=images;}
                images.setOnImageAvailableListener(source->{
                    Image image=null;try{image=source.acquireLatestImage();if(image!=null && active && version==generation){
                        java.nio.ByteBuffer bytes=image.getPlanes()[0].getBuffer();if(bytes.remaining()<=524288){byte[] jpeg=new byte[bytes.remaining()];bytes.get(jpeg);latest.set(new Frame(jpeg));}
                    }}catch(Exception ignored){}finally{if(image!=null)image.close();}
                },worker);
                manager.openCamera(chosen,new CameraDevice.StateCallback(){
                    @Override public void onOpened(CameraDevice camera){
                        synchronized(RemoteCamera.this){if(version!=generation || !active){camera.close();return;}device=camera;}
                        try{camera.createCaptureSession(Arrays.asList(images.getSurface()),new CameraCaptureSession.StateCallback(){
                            @Override public void onConfigured(CameraCaptureSession capture){
                                synchronized(RemoteCamera.this){if(version!=generation || !active){capture.close();return;}session=capture;}
                                try{CaptureRequest.Builder builder=camera.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE);
                                    builder.addTarget(images.getSurface());builder.set(CaptureRequest.JPEG_QUALITY,(byte)65);final CaptureRequest request=builder.build();
                                    worker.post(new Runnable(){@Override public void run(){
                                        if(version!=generation || !active)return;
                                        try{capture.capture(request,null,worker);worker.postDelayed(this,250);}
                                        catch(Exception e){fail(version,"Camera capture: "+e.getClass().getSimpleName());}
                                    }});
                                }catch(Exception e){fail(version,e.getClass().getSimpleName());}
                            }
                            @Override public void onConfigureFailed(CameraCaptureSession capture){capture.close();fail(version,"Camera session failed; camera may be busy");}
                        },worker);}catch(Exception e){fail(version,e.getClass().getSimpleName());}
                    }
                    @Override public void onDisconnected(CameraDevice camera){camera.close();fail(version,"Camera disconnected");}
                    @Override public void onError(CameraDevice camera,int code){camera.close();fail(version,"Camera error "+code);}
                },worker);
            }catch(Exception e){fail(version,e.getClass().getSimpleName()+": "+e.getMessage());}
        });return true;
    }
    private synchronized void fail(int version,String message){if(version==generation){error=message;stop();}}
    public Frame take(){return latest.getAndSet(null);}
    public synchronized void stop(){active=false;generation++;latest.set(null);if(handler!=null)handler.removeCallbacksAndMessages(null);
        try{if(session!=null)session.close();}catch(Exception ignored){}try{if(device!=null)device.close();}catch(Exception ignored){}
        try{if(reader!=null)reader.close();}catch(Exception ignored){}session=null;device=null;reader=null;handler=null;
        if(thread!=null)thread.quitSafely();thread=null;
    }
}
