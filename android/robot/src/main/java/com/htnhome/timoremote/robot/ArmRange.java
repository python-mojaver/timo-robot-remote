package com.htnhome.timoremote.robot;

/** هر درخواست تأییدشده یک گام در دامنهٔ آزمایشی ۲۵ تا ۱۰۰ SDK می‌فرستد. */
final class ArmRange {
    private final HeadControl.Sender sender;
    private final HeadControl.Clock clock;
    private long leaseUntil, nextCommand, lastSequence;
    private int left, right;
    private boolean armed, stopSubmitted, uncertain;

    ArmRange(HeadControl.Sender sender, HeadControl.Clock clock) {
        this.sender = sender;
        this.clock = clock;
    }

    synchronized void lease(long remaining) {
        long now = clock.now();
        if (remaining <= 0 || now >= leaseUntil) armed = false;
        leaseUntil = now + Math.max(0, Math.min(1600, remaining));
    }

    synchronized void stop(boolean submitted) {
        armed = false;
        stopSubmitted = submitted;
    }

    synchronized boolean active() { return armed || uncertain || left != 0 || right != 0; }
    synchronized boolean armed() { return armed && clock.now() < leaseUntil; }
    synchronized boolean canBegin() { return stopSubmitted && !armed; }
    synchronized boolean canFinish() {
        return active() && clock.now() >= nextCommand
                && (armed() ? !uncertain && left == 0 && right == 0 : stopSubmitted);
    }
    synchronized int left() { return left; }
    synchronized int right() { return right; }

    synchronized String apply(String action, String side, int goal, boolean confirmed, long sequence, long deadline) {
        long now = clock.now();
        if (!confirmed || now >= leaseUntil || now >= deadline || sequence <= lastSequence) return null;
        if ("finish".equals(action)) {
            if (!canFinish()) return null;
            left = right = 0;
            uncertain = false;
            armed = false;
            stopSubmitted = false;
            lastSequence = sequence;
            return "استراحت هر دو بازو ثبت شد و آزمون پایان یافت.";
        }
        if ("begin".equals(action)) {
            if (!canBegin() || now < nextCommand) return null;
            left = right = 0;
            uncertain = false;
            armed = true;
            stopSubmitted = false;
            lastSequence = sequence;
            return "حالت استراحت با مشاهدهٔ اپراتور ثبت شد. آمادهٔ اولین گام ۲٪.";
        }
        boolean rest = "rest".equals(action);
        if (!armed || now < nextCommand || !(rest ? goal == 0 : "move".equals(action) && goal >= 2 && goal <= 100)) return null;
        if (!"left".equals(side) && !"right".equals(side)) return null;
        boolean isLeft = "left".equals(side);
        if ((isLeft ? right : left) != 0) return null;
        int current = isLeft ? left : right;
        if (current == goal) return null;
        int next = current == 0 ? 2 : Math.max(current - 8, Math.min(current + 8, goal));
        if (next == 1) next = 2;
        int nextLeft = isLeft ? next : left;
        int nextRight = isLeft ? right : next;
        lastSequence = sequence;
        nextCommand = now + 1500;
        if (target(current) == target(next)) {
            left = nextLeft;
            right = nextRight;
            return "هدف "+next+"٪ همان مقدار قبلی SDK است.";
        }
        String packet = "{\"msg_id\":\"ALICE_NEW_ACTION_CTRL_REQ\",\"ctrl_type\":\"customer\","
                + "\"ctrl_angle\":0,\"ctrl_angles\":\"[49,65," + target(nextLeft) + "," + target(nextRight) + "]\"}";
        if (!sender.send(packet)) {
            uncertain = true;
            armed = false;
            return null;
        }
        left = nextLeft;
        right = nextRight;
        return "هدف این گام "+next+"٪ به SDK ارسال شد. حرکت را روی ربات بررسی کن.";
    }

    private static int target(int percent) {
        return 25 + (percent * 75 + 50) / 100;
    }
}
