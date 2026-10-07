package uk.noblehaus.butler;

import android.content.Context;
import android.content.SharedPreferences;

/** Where the notification service connects, and with which device credential. */
final class ButlerConfig {
    private static final String PREFS = "butler_notifications";

    private ButlerConfig() {}

    private static SharedPreferences prefs(Context ctx) {
        return ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static boolean enabled(Context ctx) {
        SharedPreferences p = prefs(ctx);
        return p.getBoolean("enabled", false) && p.getString("token", null) != null && p.getString("baseUrl", null) != null;
    }

    static String baseUrl(Context ctx) {
        return prefs(ctx).getString("baseUrl", null);
    }

    static String token(Context ctx) {
        return prefs(ctx).getString("token", null);
    }

    static String deviceId(Context ctx) {
        return prefs(ctx).getString("deviceId", null);
    }

    /** Highest notification id shown, so a reconnect only fetches newer ones. */
    static long sinceId(Context ctx) {
        return prefs(ctx).getLong("sinceId", 0);
    }

    static synchronized void saveSince(Context ctx, long id) {
        if (id > sinceId(ctx)) {
            prefs(ctx).edit().putLong("sinceId", id).apply();
        }
    }

    static void enable(Context ctx, String baseUrl, String token, String deviceId, long sinceId) {
        prefs(ctx).edit()
                .putBoolean("enabled", true)
                .putString("baseUrl", baseUrl.replaceAll("/+$", ""))
                .putString("token", token)
                .putString("deviceId", deviceId)
                .putLong("sinceId", sinceId)
                .commit();
    }

    static void disable(Context ctx) {
        prefs(ctx).edit().clear().commit();
    }
}
