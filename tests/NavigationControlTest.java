import com.htnhome.timoremote.robot.NavigationControl;
import java.util.*;

public class NavigationControlTest {
    static int checks=0;
    static void check(boolean value,String message){checks++;if(!value)throw new AssertionError(message);}
    static class Harness {
        long now=100;List<String> sent=new ArrayList<>();List<Boolean> saved=new ArrayList<>();
        NavigationControl n;
        Harness(boolean recovery){n=new NavigationControl(j->{sent.add(j);return true;},()->now,v->saved.add(v),recovery);}
        void idle(){status(0,0);}
        void status(Object error,Object state){now+=600;n.lease(1600);n.tick(true,true);n.statusResponse(error,state);}
        void ready(){idle();check(!n.ready(),"one idle is insufficient");idle();check(n.ready(),"two idle readings enable navigation");}
        boolean begin(long seq){n.lease(1600);return n.begin("{\"x\":1,\"y\":2,\"z\":0,\"rotation\":0}","test","request_"+seq,seq,now+1200,true);}
        long poses(){return sent.stream().filter(x->x.contains("MOVE_TO_REQ")).count();}
    }
    public static void main(String[] args){
        Harness h=new Harness(false);check(!h.n.ready(),"initially unverified");check(!h.begin(1),"cannot start before status feedback");
        h.ready();check(h.begin(2),"first destination accepted");check(h.n.busy(),"navigation blocks manual drive");check(h.poses()==1,"one pose only");
        check(!h.begin(3),"second destination while busy rejected");h.n.moveResponse(0);h.idle();h.idle();check(h.n.busy(),"send ACK and idle do not imply arrival");
        h.n.moveNotification(0);h.idle();check(h.n.busy(),"NTF plus one idle is insufficient");h.idle();check(!h.n.busy() && h.n.state().equals("arrived"),"arrival unlocked automatically");
        check(h.begin(3),"second destination without app restart accepted");check(h.poses()==2,"no replay");
        h.n.lease(0);h.n.tick(true,true);check(h.n.state().equals("stopping"),"lost lease cancels");check(h.sent.stream().anyMatch(x->x.contains("NAVI_ROBOT_CANCEL_REQ")),"cancel submitted");
        h.n.moveNotification(0);check(!h.n.state().equals("arrived"),"late NTF during cancellation cannot arrive");h.idle();h.idle();check(h.n.ready() && h.n.state().equals("stopped"),"two idle checks release stop");
        h.n.manual();check(!h.n.ready(),"manual drive invalidates idle proof");h.ready();h.n.lease(1600);
        check(!h.n.begin("{}","x","x",4,h.now+1200,false),"manual stop repeats must settle");
        check(!h.n.begin("{}","x","x",4,h.now-1,true),"expired destination rejected");
        Harness recovered=new Harness(true);check(recovered.n.busy(),"pending process restart remains blocked");recovered.n.tick(true,true);check(recovered.poses()==0,"restart never replays pose");recovered.idle();recovered.idle();check(recovered.n.ready(),"restart recovers only from idle proof");
        Harness other=new Harness(false);other.ready();other.now+=1500;other.n.tick(true,true);other.n.statusResponse(0,1);check(other.n.busy(),"external SDK navigation blocks own manual drive");
        long cancels=other.sent.stream().filter(x->x.contains("CANCEL")).count();other.now+=5000;other.n.tick(true,true);check(other.sent.stream().filter(x->x.contains("CANCEL")).count()==cancels,"observer does not cancel external route automatically");
        other.idle();other.idle();check(!other.n.busy() && other.n.ready(),"external route ends with idle proof");
        Harness failed=new Harness(false);failed.ready();failed.begin(1);failed.n.moveResponse(9);check(failed.n.busy() && !failed.n.ready(),"SDK error retains interlock");check(!failed.n.state().equals("arrived"),"error never becomes success");
        failed.n.close();check(failed.poses()==1,"close never resends pose");
        Harness stale=new Harness(false);stale.n.statusResponse(0,0);stale.n.statusResponse(0,0);check(!stale.n.ready(),"unsolicited idle data rejected");
        stale.n.tick(true,true);stale.now+=2600;stale.n.tick(true,true);stale.n.statusResponse(0,0);check(!stale.n.ready(),"timed-out response rejected");
        Harness manual=new Harness(false);manual.n.stopControls();
        check(!manual.n.busy() && manual.saved.isEmpty(),"ordinary stop never creates a pending navigation");
        check(manual.sent.stream().anyMatch(x->x.contains("NAVI_ROBOT_CANCEL_REQ")),"ordinary stop still requests cancel");
        check(!manual.begin(1),"navigation still requires fresh idle status");
        manual.ready();check(manual.begin(2),"verified navigation accepted");
        manual.n.stopControls();
        check(manual.n.busy() && manual.n.state().equals("stopping"),"active route remains locked");
        manual.idle();check(manual.n.busy(),"one idle report does not release an active route");
        manual.idle();check(!manual.n.busy(),"verified stop releases manual drive");
        Harness localized=new Harness(true);
        localized.status(0,"۰");
        check(localized.n.busy(),"one localized idle does not release a recovered route");
        localized.status(0,0.1);
        localized.status(0,"۰");
        check(localized.n.busy(),"fractional states invalidate prior idle evidence");
        localized.status("٠","٠");
        check(localized.n.ready() && !localized.n.busy(),"Persian and Arabic-Indic integers count as idle");
        Harness localizedMoving=new Harness(false);
        localizedMoving.status(0,"۱");
        check(localizedMoving.n.busy(),"localized moving state blocks manual drive");
        System.out.println("NavigationControl: "+checks+" checks passed");
    }
}
