package uk.noblehaus.butler;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;

import org.json.JSONObject;

import java.time.OffsetDateTime;

/**
 * Android notification channels (one per Butler category, so each can be tuned in
 * Android settings) and how Butler's notifications are shown.
 */
final class Notifications {
    static final String CONNECTION = "connection";
    static final int CONNECTION_ID = 1;
    private static final String TAG = "ButlerNotify";

    private Notifications() {}

    static void ensureChannels(Context ctx) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        create(nm, "approval", "Approvals", NotificationManager.IMPORTANCE_HIGH,
                "Emails and calendar changes waiting for your OK");
        create(nm, "reminder", "Reminders", NotificationManager.IMPORTANCE_HIGH, "Reminders you asked Butler for");
        create(nm, "alert", "Server alerts", NotificationManager.IMPORTANCE_HIGH, "Problems with the home server");
        create(nm, "calendar", "Calendar", NotificationManager.IMPORTANCE_DEFAULT, "Calendar updates");
        create(nm, "download", "Downloads", NotificationManager.IMPORTANCE_DEFAULT, "Films, shows and books finishing");
        create(nm, "smart_home", "Smart home", NotificationManager.IMPORTANCE_DEFAULT, "Home Assistant events");
        create(nm, "weather", "Weather", NotificationManager.IMPORTANCE_LOW, "Weather updates");
        create(nm, "general", "General", NotificationManager.IMPORTANCE_DEFAULT, "Everything else from Butler");
        create(nm, CONNECTION, "Butler connection", NotificationManager.IMPORTANCE_MIN,
                "Keeps the connection to your home server open. You can turn this one off.");
    }

    private static void create(NotificationManager nm, String id, String name, int importance, String description) {
        NotificationChannel channel = new NotificationChannel(id, name, importance);
        channel.setDescription(description);
        if (CONNECTION.equals(id)) {
            channel.setShowBadge(false);
        }
        nm.createNotificationChannel(channel);
    }

    static String channelFor(String category) {
        switch (category == null ? "" : category) {
            case "approval":
            case "reminder":
            case "alert":
            case "calendar":
            case "download":
            case "smart_home":
            case "weather":
                return category;
            default:
                return "general";
        }
    }

    static PendingIntent openApp(Context ctx, String url, int requestCode) {
        Intent intent = new Intent(ctx, MainActivity.class)
                .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP)
                .putExtra(MainActivity.EXTRA_URL, url);
        return PendingIntent.getActivity(ctx, requestCode, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    /** The foreground service's own (silent, minimised) notification. */
    static Notification connection(Context ctx, String text) {
        return new NotificationCompat.Builder(ctx, CONNECTION)
                .setSmallIcon(R.drawable.ic_stat_butler)
                .setContentTitle("Butler")
                .setContentText(text)
                .setOngoing(true)
                .setShowWhen(false)
                .setSilent(true)
                .setPriority(NotificationCompat.PRIORITY_MIN)
                .setContentIntent(openApp(ctx, "/settings", 0))
                .build();
    }

    /** Show one of Butler's notifications: {id, title, body, url, category, silent, createdAt}. */
    static void show(Context ctx, JSONObject n) {
        long id = n.optLong("id");
        String category = n.optString("category", "general");
        String body = n.optString("body", "");
        NotificationCompat.Builder b = new NotificationCompat.Builder(ctx, channelFor(category))
                .setSmallIcon(R.drawable.ic_stat_butler)
                .setContentTitle(n.optString("title", "Butler"))
                .setContentText(body)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
                .setAutoCancel(true)
                .setGroup(category)
                .setSilent(n.optBoolean("silent", false))
                .setContentIntent(openApp(ctx, n.optString("url", "/"), (int) (id % Integer.MAX_VALUE)));
        String created = n.optString("createdAt", "");
        if (!created.isEmpty() && Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            try {
                b.setWhen(OffsetDateTime.parse(created).toInstant().toEpochMilli());
            } catch (Exception ignored) {
                // keep "now"
            }
        }
        try {
            // Id 1 is the connection notification; Butler ids start at 1, so offset them.
            NotificationManagerCompat.from(ctx).notify((int) (1000 + id % 1_000_000), b.build());
        } catch (SecurityException e) {
            Log.w(TAG, "Notification permission not granted", e);
        }
    }
}
