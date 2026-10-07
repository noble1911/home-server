package uk.noblehaus.butler;

import android.app.Notification;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.net.ConnectivityManager;
import android.net.Network;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

/**
 * Keeps a WebSocket open to Butler (/api/notifications/ws) and shows what it sends.
 *
 * This replaces Firebase: Butler pushes notifications down this connection
 * itself. Android only lets an app keep a connection while it runs a
 * foreground service, hence the (minimised) "Butler connection" notification.
 * Reconnects with backoff, immediately when the network comes back, and after
 * reboot (BootReceiver). Missed notifications are fetched on reconnect via `since`.
 */
public class NotificationService extends Service {
    private static final String TAG = "ButlerNotify";
    private static final long MIN_BACKOFF_MS = 2_000;
    private static final long MAX_BACKOFF_MS = 5 * 60_000;

    static volatile boolean connected = false;
    static volatile String lastError = null;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable reconnect = this::connect;
    private OkHttpClient client;
    private WebSocket socket;
    private long backoffMs = MIN_BACKOFF_MS;
    private boolean stopping = false;
    private ConnectivityManager.NetworkCallback networkCallback;

    static void start(Context ctx) {
        ContextCompat.startForegroundService(ctx, new Intent(ctx, NotificationService.class));
    }

    static void stop(Context ctx) {
        ctx.stopService(new Intent(ctx, NotificationService.class));
    }

    @Override
    public void onCreate() {
        super.onCreate();
        Notifications.ensureChannels(this);
        goForeground("Connecting…");
        // OkHttp sends a WebSocket ping every 30 s; Butler adds a keepalive every 45 s.
        // Both keep Cloudflare (100 s idle limit) and home routers from dropping it.
        client = new OkHttpClient.Builder()
                .pingInterval(30, TimeUnit.SECONDS)
                .connectTimeout(20, TimeUnit.SECONDS)
                .readTimeout(0, TimeUnit.MILLISECONDS)
                .build();
        ConnectivityManager cm = getSystemService(ConnectivityManager.class);
        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(@NonNull Network network) {
                handler.post(() -> {
                    if (!connected && !stopping) {
                        backoffMs = MIN_BACKOFF_MS;
                        reconnectNow();
                    }
                });
            }
        };
        try {
            cm.registerDefaultNetworkCallback(networkCallback);
        } catch (RuntimeException e) {
            networkCallback = null;
        }
    }

    private void goForeground(String text) {
        Notification n = Notifications.connection(this, text);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(Notifications.CONNECTION_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(Notifications.CONNECTION_ID, n);
        }
    }

    private void showStatus(String text) {
        try {
            NotificationManagerCompat.from(this).notify(Notifications.CONNECTION_ID, Notifications.connection(this, text));
        } catch (SecurityException ignored) {
            // No notification permission: the service still runs.
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (!ButlerConfig.enabled(this)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        stopping = false;
        if (socket == null) {
            connect();
        }
        return START_STICKY;
    }

    private void reconnectNow() {
        handler.removeCallbacks(reconnect);
        if (socket != null) {
            socket.cancel();
            socket = null;
        }
        connect();
    }

    private void connect() {
        if (stopping || !ButlerConfig.enabled(this)) return;
        String base = ButlerConfig.baseUrl(this);
        String url = base.replaceFirst("^http", "ws") + "/api/notifications/ws?since=" + ButlerConfig.sinceId(this);
        Request request = new Request.Builder()
                .url(url)
                .header("Authorization", "Device " + ButlerConfig.token(this))
                .build();
        socket = client.newWebSocket(request, new Listener());
    }

    private void scheduleReconnect() {
        if (stopping) return;
        handler.removeCallbacks(reconnect);
        handler.postDelayed(reconnect, backoffMs);
        backoffMs = Math.min(backoffMs * 2, MAX_BACKOFF_MS);
    }

    private class Listener extends WebSocketListener {
        @Override
        public void onOpen(@NonNull WebSocket ws, @NonNull Response response) {
            handler.post(() -> {
                if (ws != socket) return;
                connected = true;
                lastError = null;
                backoffMs = MIN_BACKOFF_MS;
                showStatus("Connected to your home server");
            });
        }

        @Override
        public void onMessage(@NonNull WebSocket ws, @NonNull String text) {
            try {
                JSONObject msg = new JSONObject(text);
                if ("notification".equals(msg.optString("type"))) {
                    Notifications.show(NotificationService.this, msg);
                    ButlerConfig.saveSince(NotificationService.this, msg.optLong("id"));
                }
            } catch (JSONException e) {
                Log.w(TAG, "Ignoring a message that isn't JSON");
            }
        }

        @Override
        public void onClosing(@NonNull WebSocket ws, int code, @NonNull String reason) {
            // Butler closed it (e.g. restarting). Answer now and reconnect, rather
            // than sitting half-closed until the next ping times out (~30 s).
            ws.close(1000, null);
            dropped(ws, "server closed (" + code + ")");
        }

        @Override
        public void onClosed(@NonNull WebSocket ws, int code, @NonNull String reason) {
            dropped(ws, "closed (" + code + ")");
        }

        @Override
        public void onFailure(@NonNull WebSocket ws, @NonNull Throwable t, @Nullable Response response) {
            String why = response != null ? "HTTP " + response.code() : t.getClass().getSimpleName();
            if (response != null && (response.code() == 401 || response.code() == 403)) {
                why = "not authorised — turn phone notifications off and on again in Butler";
            }
            dropped(ws, why);
        }

        private void dropped(WebSocket ws, String why) {
            handler.post(() -> {
                if (ws != socket) return;  // an old socket we already replaced
                socket = null;
                connected = false;
                lastError = why;
                Log.i(TAG, "Connection lost: " + why + "; retrying in " + backoffMs / 1000 + " s");
                showStatus("Reconnecting…");
                scheduleReconnect();
            });
        }
    }

    @Override
    public void onDestroy() {
        stopping = true;
        handler.removeCallbacksAndMessages(null);
        if (socket != null) {
            socket.close(1000, "stopped");
            socket = null;
        }
        connected = false;
        if (networkCallback != null) {
            try {
                getSystemService(ConnectivityManager.class).unregisterNetworkCallback(networkCallback);
            } catch (RuntimeException ignored) {
                // already gone
            }
        }
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
