package unknown.none.nx2android;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import java.io.File;

public class MainActivity extends Activity {
    private WebView web;
    private TextView logView;
    private ScrollView scroll;
    private final Handler h = new Handler(Looper.getMainLooper());
    private String loadedToken = "";

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(0xFF0D0D10);

        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(32, 72, 32, 32);
        TextView title = new TextView(this);
        title.setText("nx2android: setting up");
        title.setTextColor(0xFFECECF1);
        title.setTextSize(18);
        col.addView(title);
        scroll = new ScrollView(this);
        logView = new TextView(this);
        logView.setTextColor(0xFFBBBBCC);
        logView.setTextSize(11);
        logView.setTypeface(Typeface.MONOSPACE);
        scroll.addView(logView);
        col.addView(scroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        LinearLayout bar = new LinearLayout(this);
        Button copy = new Button(this);
        copy.setText("Copy log");
        copy.setOnClickListener(v -> {
            ((ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE)).setPrimaryClip(ClipData.newPlainText("nx2android log", ProotService.snapshot()));
            Toast.makeText(this, "Log copied", Toast.LENGTH_SHORT).show();
        });
        Button retry = new Button(this);
        retry.setText("Retry");
        retry.setOnClickListener(v -> {
            Intent i = new Intent(this, ProotService.class);
            stopService(i);
            startForegroundService(i);
        });
        bar.addView(copy, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        bar.addView(retry, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        col.addView(bar);
        root.addView(col);

        web = new WebView(this);
        web.setVisibility(View.GONE);
        web.setBackgroundColor(0xFF0D0D10);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        web.setWebViewClient(new WebViewClient());
        web.addJavascriptInterface(new Bridge(), "NX2A");
        root.addView(web, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);

        startForegroundService(new Intent(this, ProotService.class));
        if (Build.VERSION.SDK_INT >= 23 && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.READ_EXTERNAL_STORAGE, Manifest.permission.WRITE_EXTERNAL_STORAGE}, 1);
        } else {
            askBattery();
        }
        h.post(tick);
    }

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (ProotService.ready) {
                if (!loadedToken.equals(ProotService.token)) {
                    loadedToken = ProotService.token;
                    web.loadUrl("http://127.0.0.1:" + ProotService.PORT + "/?t=" + loadedToken);
                    web.setVisibility(View.VISIBLE);
                }
            } else {
                if (!loadedToken.isEmpty()) { loadedToken = ""; web.setVisibility(View.GONE); }
                logView.setText(ProotService.snapshot());
                scroll.post(() -> scroll.fullScroll(View.FOCUS_DOWN));
            }
            h.postDelayed(this, 800);
        }
    };

    @Override public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        super.onRequestPermissionsResult(code, perms, results);
        askBattery();
    }

    /** Explains why first, then shows Android's own prompt. Asked again at most once if the user cancels. */
    private void askBattery() {
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        final SharedPreferences sp = getSharedPreferences("nx2a", MODE_PRIVATE);
        if (pm.isIgnoringBatteryOptimizations(getPackageName()) || sp.getInt("battery_declined", 0) >= 2) return;
        new AlertDialog.Builder(this)
                .setTitle("Allow background activity?")
                .setMessage("nx2android needs the battery setting \"Unrestricted\" (no limit) so that setup, downloads and porting keep running in the background while the screen is off or you use other apps. Without it Android can stop them halfway.\n\nTap OK to open Android's prompt for it.")
                .setPositiveButton("OK", (d, w) -> {
                    try {
                        startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getPackageName())));
                    } catch (Exception e) {
                        startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
                    }
                })
                .setNegativeButton("Cancel", (d, w) -> sp.edit().putInt("battery_declined", sp.getInt("battery_declined", 0) + 1).apply())
                .show();
    }

    @Override public void onBackPressed() {
        if (web.getVisibility() == View.VISIBLE && web.canGoBack()) web.goBack();
        else moveTaskToBack(true);
    }

    private void doInstall(String path) {
        try {
            String p = path.startsWith("/sdcard/") ? Environment.getExternalStorageDirectory().getAbsolutePath() + path.substring(7) : path;
            File f = new File(p);
            if (!f.isFile()) { Toast.makeText(this, "APK not found: " + p, Toast.LENGTH_LONG).show(); return; }
            if (!getPackageManager().canRequestPackageInstalls()) {
                Toast.makeText(this, "Allow installs from nx2android, then tap Install APK again", Toast.LENGTH_LONG).show();
                startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getPackageName())));
                return;
            }
            Uri u = FileProvider.getUriForFile(this, getPackageName() + ".files", f);
            Intent i = new Intent(Intent.ACTION_VIEW).setDataAndType(u, "application/vnd.android.package-archive")
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
        } catch (Exception e) {
            Toast.makeText(this, "Install failed: " + e, Toast.LENGTH_LONG).show();
        }
    }

    private class Bridge {
        @JavascriptInterface public void runProotExperiments() {
            startForegroundService(new Intent(MainActivity.this, ProotService.class).setAction("experiments"));
        }

        @JavascriptInterface public void traceDotnet() {
            startForegroundService(new Intent(MainActivity.this, ProotService.class).setAction("trace"));
        }

        @JavascriptInterface public void installApk(String path) { runOnUiThread(() -> doInstall(path)); }

        @JavascriptInterface public void quit() {
            runOnUiThread(() -> {
                stopService(new Intent(MainActivity.this, ProotService.class));
                finishAffinity();
                h.postDelayed(() -> android.os.Process.killProcess(android.os.Process.myPid()), 600);
            });
        }
    }
}
