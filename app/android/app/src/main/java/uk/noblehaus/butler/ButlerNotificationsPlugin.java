package uk.noblehaus.butler;

import android.Manifest;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;

import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.pm.PackageInfoCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

/**
 * The web app's handle on native notifications (see app/src/native/butlerNative.ts).
 *
 * start/stop the notification service, report its status, ask for the
 * notification permission and the battery-optimisation exemption, and tell the
 * web app when the user opened a notification ("notificationOpened").
 */
@CapacitorPlugin(
        name = "ButlerNotifications",
        permissions = {@Permission(alias = "notifications", strings = {Manifest.permission.POST_NOTIFICATIONS})}
)
public class ButlerNotificationsPlugin extends Plugin {
    private static ButlerNotificationsPlugin instance;
    private static String pendingUrl;

    @Override
    public void load() {
        instance = this;
        if (pendingUrl != null) {
            emitOpened(pendingUrl);
            pendingUrl = null;
        }
    }

    /** Called by MainActivity when it was opened from one of our notifications. */
    static void openedFromNotification(String url) {
        if (instance != null) {
            instance.emitOpened(url);
        } else {
            pendingUrl = url;
        }
    }

    private void emitOpened(String url) {
        JSObject data = new JSObject();
        data.put("url", url);
        // Retained until the web app adds its listener (cold start from a notification).
        notifyListeners("notificationOpened", data, true);
    }

    @PluginMethod
    public void start(PluginCall call) {
        String baseUrl = call.getString("baseUrl");
        String token = call.getString("deviceToken");
        String deviceId = call.getString("deviceId");
        Double since = call.getDouble("sinceId", 0.0);
        if (baseUrl == null || token == null || deviceId == null) {
            call.reject("baseUrl, deviceToken and deviceId are required");
            return;
        }
        Context ctx = getContext();
        ButlerConfig.enable(ctx, baseUrl, token, deviceId, since == null ? 0 : since.longValue());
        try {
            NotificationService.start(ctx);
            call.resolve();
        } catch (RuntimeException e) {
            call.reject("Couldn't start the notification service: " + e.getMessage());
        }
    }

    @PluginMethod
    public void stop(PluginCall call) {
        Context ctx = getContext();
        NotificationService.stop(ctx);
        ButlerConfig.disable(ctx);
        NotificationManagerCompat.from(ctx).cancel(Notifications.CONNECTION_ID);
        call.resolve();
    }

    @PluginMethod
    public void status(PluginCall call) {
        Context ctx = getContext();
        JSObject result = new JSObject();
        result.put("enabled", ButlerConfig.enabled(ctx));
        result.put("connected", NotificationService.connected);
        result.put("lastError", NotificationService.lastError);
        result.put("deviceId", ButlerConfig.deviceId(ctx));
        result.put("notificationsAllowed", NotificationManagerCompat.from(ctx).areNotificationsEnabled());
        PowerManager pm = ctx.getSystemService(PowerManager.class);
        result.put("batteryOptimized", pm != null && !pm.isIgnoringBatteryOptimizations(ctx.getPackageName()));
        result.put("deviceName", (Build.MANUFACTURER + " " + Build.MODEL).trim());
        try {
            PackageInfo info = ctx.getPackageManager().getPackageInfo(ctx.getPackageName(), 0);
            result.put("versionName", info.versionName);
            result.put("versionCode", PackageInfoCompat.getLongVersionCode(info));
        } catch (Exception e) {
            result.put("versionName", "unknown");
            result.put("versionCode", 0);
        }
        call.resolve(result);
    }

    @PluginMethod
    public void requestNotificationPermission(PluginCall call) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU
                || getPermissionState("notifications") == PermissionState.GRANTED) {
            resolveGranted(call);
        } else {
            requestPermissionForAlias("notifications", call, "notificationPermissionResult");
        }
    }

    @PermissionCallback
    private void notificationPermissionResult(PluginCall call) {
        resolveGranted(call);
    }

    private void resolveGranted(PluginCall call) {
        JSObject result = new JSObject();
        result.put("granted", NotificationManagerCompat.from(getContext()).areNotificationsEnabled());
        call.resolve(result);
    }

    /** Ask to be exempt from battery optimisation, or Android drops the connection in Doze. */
    @PluginMethod
    public void openBatterySettings(PluginCall call) {
        Context ctx = getContext();
        Intent ask = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                Uri.parse("package:" + ctx.getPackageName())).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            ctx.startActivity(ask);
        } catch (ActivityNotFoundException e) {
            ctx.startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        }
        call.resolve();
    }

    @PluginMethod
    public void openNotificationSettings(PluginCall call) {
        Context ctx = getContext();
        Intent intent = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                .putExtra(Settings.EXTRA_APP_PACKAGE, ctx.getPackageName())
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        ctx.startActivity(intent);
        call.resolve();
    }
}
