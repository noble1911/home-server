package uk.noblehaus.butler;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

/** Restart the notification connection after a reboot or an app update. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context ctx, Intent intent) {
        String action = intent.getAction();
        boolean relevant = Intent.ACTION_BOOT_COMPLETED.equals(action)
                || Intent.ACTION_MY_PACKAGE_REPLACED.equals(action);
        if (relevant && ButlerConfig.enabled(ctx)) {
            try {
                NotificationService.start(ctx);
            } catch (RuntimeException e) {
                Log.w("ButlerNotify", "Couldn't start the notification service after " + action, e);
            }
        }
    }
}
