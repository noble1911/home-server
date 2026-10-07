package uk.noblehaus.butler;

import android.content.Intent;
import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    static final String EXTRA_URL = "uk.noblehaus.butler.URL";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(ButlerNotificationsPlugin.class);
        super.onCreate(savedInstanceState);
        handleNotificationTap(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleNotificationTap(intent);
    }

    /** Opened from a Butler notification: tell the web app which page to show. */
    private void handleNotificationTap(Intent intent) {
        if (intent == null) return;
        String url = intent.getStringExtra(EXTRA_URL);
        if (url != null) {
            intent.removeExtra(EXTRA_URL);
            ButlerNotificationsPlugin.openedFromNotification(url);
        }
    }
}
