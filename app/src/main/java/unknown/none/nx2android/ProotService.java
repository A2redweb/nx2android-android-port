package unknown.none.nx2android;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Environment;
import android.os.IBinder;
import android.os.PowerManager;

import java.io.BufferedInputStream;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import org.json.JSONObject;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.zip.GZIPInputStream;

/** Unpacks Ubuntu once, installs the build tools once, then keeps the launcher (and through it the web GUI) running inside proot. */
public class ProotService extends Service {
    static final int PORT = 7331;
    private static final StringBuilder LOG = new StringBuilder();
    static volatile boolean ready, failed, running;
    static volatile String token = "";
    private Process server;
    private boolean wasRunning;
    private PowerManager.WakeLock wl;

    static synchronized void log(String s) {
        LOG.append(s).append('\n');
        if (LOG.length() > 80000) LOG.delete(0, 30000);
    }

    static synchronized String snapshot() { return LOG.toString(); }

    @Override public IBinder onBind(Intent i) { return null; }

    @Override public int onStartCommand(Intent i, int flags, int id) {
        startForeground(1, notification("nx2android is running"));
        if (!running) {
            running = true; ready = false; failed = false;
            PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
            wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "nx2a:porter");
            wl.acquire();
            new Thread(this::work, "nx2a-boot").start();
        }
        return START_STICKY;
    }

    @Override public void onDestroy() {
        running = false; ready = false;
        if (server != null) server.destroy();
        if (wl != null && wl.isHeld()) wl.release();
        super.onDestroy();
    }

    private Notification notification(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel("nx2a", "nx2android", NotificationManager.IMPORTANCE_LOW));
        PendingIntent pi = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), 0);
        return new Notification.Builder(this, "nx2a").setContentTitle("nx2android").setContentText(text)
                .setSmallIcon(R.drawable.ic_stat_nx2a).setColor(0xFF2E2BD9).setContentIntent(pi).setOngoing(true).build();
    }

    /** Updates the ongoing notification (pct below 0 = no bar). */
    private void show(String text, int pct) {
        PendingIntent pi = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), 0);
        Notification.Builder b = new Notification.Builder(this, "nx2a").setContentTitle("nx2android").setContentText(text)
                .setSmallIcon(R.drawable.ic_stat_nx2a).setColor(0xFF2E2BD9).setContentIntent(pi).setOngoing(true);
        if (pct >= 0) b.setProgress(100, pct, false);
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).notify(1, b.build());
    }

    private void notifyDone(String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel("nx2a_done", "Finished tasks", NotificationManager.IMPORTANCE_DEFAULT));
        PendingIntent pi = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), 0);
        nm.notify(2, new Notification.Builder(this, "nx2a_done").setContentTitle("nx2android").setContentText(text)
                .setSmallIcon(R.drawable.ic_stat_nx2a).setContentIntent(pi).setAutoCancel(true).build());
    }

    private static String label(String kind) {
        switch (kind) {
            case "port": return "Porting";
            case "tools": return "Downloading tools";
            case "copy": return "Copying game data";
            case "install": return "Installing";
            default: return "Working";
        }
    }

    /** Tasks run inside the service's own process, so they keep going with the app closed. This mirrors them in the notification. */
    private void watchTasks() {
        while (running && ready) {
            try {
                HttpURLConnection c = (HttpURLConnection) new URL("http://127.0.0.1:" + PORT + "/api/summary").openConnection();
                c.setRequestProperty("Cookie", "nx2a=" + token);
                c.setConnectTimeout(1500);
                c.setReadTimeout(1500);
                StringBuilder sb = new StringBuilder();
                try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
                    String ln;
                    while ((ln = r.readLine()) != null) sb.append(ln);
                }
                JSONObject o = new JSONObject(sb.toString());
                String kind = o.optString("kind", "");
                if (o.optBoolean("running")) {
                    wasRunning = true;
                    String stage = o.optString("stage", "");
                    int pct = o.isNull("frac") ? -1 : (int) (o.optDouble("frac", -1) * 100);
                    show(label(kind) + (stage.isEmpty() ? "" : ": " + stage), pct);
                } else {
                    if (wasRunning) {
                        wasRunning = false;
                        int code = o.isNull("code") ? 0 : o.optInt("code", 0);
                        notifyDone(code == 0 ? label(kind) + " finished" : label(kind) + " stopped (exit " + code + "). Open the app for details.");
                    }
                    show("nx2android is ready", -1);
                }
            } catch (Exception ignored) { }
            try { Thread.sleep(2500); } catch (InterruptedException e) { return; }
        }
    }

    private void work() {
        try {
            File base = getFilesDir(), root = new File(base, "ubuntu"), ok = new File(base, "ubuntu.ok");
            new File(base, "ptmp").mkdirs();
            if (!ok.exists()) {
                log("First run: unpacking Ubuntu (a minute or two)...");
                show("Unpacking Ubuntu (first run)", -1);
                deleteTree(root);
                root.mkdirs();
                try (InputStream in = openRootfs()) {
                    Tar.extract(in, root);
                }
                prepareRootfs(root);
                ok.createNewFile();
            }
            copyAssets("nx2a", new File(root, "nx2a"));
            writeFakeProc();
            File mark = new File(root, "root/.nx2a_setup");
            if (!mark.exists()) {
                log("Installing the build tools (needs internet, about 10 minutes)...");
                show("Installing the build tools (first run)", -1);
                int rc = runLogged(proot("bash /nx2a/payload/inner_setup.sh", null));
                if (rc != 0 || !mark.exists()) throw new IOException("setup failed (exit " + rc + "). Check your connection, then tap Retry.");
            }
            show("Starting nx2android", -1);
            startServer();
            show("nx2android is ready", -1);
            new Thread(this::watchTasks, "nx2a-watch").start();
        } catch (Throwable t) {
            log("ERROR: " + t);
            failed = true; running = false;
        }
    }

    /** The bundle is a gzip file stored as rootfs.bin. Build tools rewrite assets named *.gz (they unpack them and drop the extension), which broke the first release. */
    private InputStream openRootfs() throws IOException {
        try {
            return new GZIPInputStream(new BufferedInputStream(getAssets().open("rootfs.bin"), 1 << 16));
        } catch (java.io.FileNotFoundException e) {
            return new BufferedInputStream(getAssets().open("rootfs.tar"), 1 << 16);   // a build tool already unpacked it
        }
    }

    private void prepareRootfs(File root) throws IOException {
        write(new File(root, "etc/resolv.conf"), "nameserver 1.1.1.1\nnameserver 8.8.8.8\n");
        write(new File(root, "etc/hosts"), "127.0.0.1 localhost\n::1 localhost\n");
        write(new File(root, "etc/apt/apt.conf.d/99nx2a"), "APT::Sandbox::User \"root\";\nAcquire::Retries \"3\";\n");
        new File(root, "tmp").mkdirs();
        new File(root, "root").mkdirs();
    }

    /** Android hides some /proc files from apps; tools that read them get these stand-ins. */
    private void writeFakeProc() throws IOException {
        File d = new File(getFilesDir(), "fakeproc");
        d.mkdirs();
        write(new File(d, "loadavg"), "0.54 0.41 0.30 1/931 370\n");
        write(new File(d, "uptime"), "284684.56 513853.46\n");
        write(new File(d, "version"), "Linux version 5.1.1-nx2a (proot@nx2a) (gcc 14.2.0) #1 SMP PREEMPT_DYNAMIC Fri Jan  1 00:00:00 UTC 2027\n");
        write(new File(d, "vmstat"), "nr_free_pages 1743136\nnr_zone_inactive_anon 179281\n");
        StringBuilder st = new StringBuilder("cpu  1957 0 2877 93280 262 342 254 87 0 0\n");
        int n = Runtime.getRuntime().availableProcessors();
        for (int i = 0; i < n; i++) st.append("cpu").append(i).append(" 31 0 226 12027 82 10 4 9 0 0\n");
        st.append("intr 0 0 0\nctxt 0\nbtime 1\nprocesses 1\nprocs_running 1\nprocs_blocked 0\nsoftirq 0 0 0 0 0 0 0 0 0 0 0\n");
        write(new File(d, "stat"), st.toString());
    }

    private ProcessBuilder proot(String cmd, Map<String, String> extra) {
        String lib = getApplicationInfo().nativeLibraryDir;
        File root = new File(getFilesDir(), "ubuntu");
        String sd = Environment.getExternalStorageDirectory().getAbsolutePath();
        String fp = new File(getFilesDir(), "fakeproc").getAbsolutePath();
        List<String> c = new ArrayList<>(Arrays.asList(
                lib + "/libproot.so", "--kill-on-exit", "--link2symlink", "-0",
                "-r", root.getAbsolutePath(), "-w", "/root",
                "-b", "/dev", "-b", "/proc", "-b", "/sys", "-b", "/dev/urandom:/dev/random", "-b", sd + ":/sdcard",
                "--kernel-release=5.1.1-nx2a"));
        for (String n : new String[]{"stat", "loadavg", "uptime", "version", "vmstat"}) {
            if (!readable("/proc/" + n)) { c.add("-b"); c.add(fp + "/" + n + ":/proc/" + n); }
        }
        c.addAll(Arrays.asList(
                "/usr/bin/env", "-i", "HOME=/root", "PATH=/root/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "TERM=xterm", "LANG=C.UTF-8", "TMPDIR=/tmp", "DEBIAN_FRONTEND=noninteractive",
                "DOTNET_EnableWriteXorExecute=0", "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1"));
        if (extra != null) for (Map.Entry<String, String> e : extra.entrySet()) c.add(e.getKey() + "=" + e.getValue());
        c.add("bash"); c.add("-c"); c.add(cmd);
        ProcessBuilder b = new ProcessBuilder(c);
        b.redirectErrorStream(true);
        Map<String, String> env = b.environment();
        env.put("PROOT_LOADER", lib + "/libproot-loader.so");
        env.put("PROOT_TMP_DIR", new File(getFilesDir(), "ptmp").getAbsolutePath());
        env.put("LD_LIBRARY_PATH", lib);
        return b;
    }

    /** True when this app may read the file; Android hides some /proc files from apps, and only those get a stand-in. */
    private static boolean readable(String path) {
        try (InputStream in = new java.io.FileInputStream(path)) { return in.read() >= -1; } catch (Exception e) { return false; }
    }

    private int runLogged(ProcessBuilder b) throws IOException, InterruptedException {
        Process p = b.start();
        try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
            String ln;
            while ((ln = r.readLine()) != null) log(ln);
        }
        return p.waitFor();
    }

    private void startServer() throws Exception {
        byte[] rnd = new byte[24];
        new SecureRandom().nextBytes(rnd);
        StringBuilder sb = new StringBuilder();
        for (byte x : rnd) sb.append(String.format("%02x", x));
        token = sb.toString();
        Map<String, String> env = new LinkedHashMap<>();
        env.put("NX2A_TOKEN", token);
        env.put("NX2A_PORT", String.valueOf(PORT));
        env.put("NX2A_REPO", "/root/nx2android");
        log("Starting the GUI (the first start also fetches the porter, up to a minute)...");
        final Process p = proot("exec /root/venv/bin/python /nx2a/launcher.py", env).start();
        server = p;
        new Thread(() -> {
            try (BufferedReader rd = new BufferedReader(new InputStreamReader(p.getInputStream(), StandardCharsets.UTF_8))) {
                String ln;
                while ((ln = rd.readLine()) != null) log(ln);
            } catch (IOException ignored) { }
            ready = false; failed = true;
            log("The GUI process ended. Tap Retry.");
        }, "nx2a-pump").start();
        for (int i = 0; i < 600; i++) {
            if (!p.isAlive()) throw new IOException("the GUI process stopped (exit " + p.exitValue() + ")");
            try (Socket s = new Socket()) {
                s.connect(new InetSocketAddress("127.0.0.1", PORT), 300);
                ready = true;
                return;
            } catch (IOException e) {
                Thread.sleep(500);
            }
        }
        throw new IOException("the GUI did not start in time");
    }

    private void copyAssets(String path, File dst) throws IOException {
        String[] list = getAssets().list(path);
        if (list == null || list.length == 0) {
            File parent = dst.getParentFile();
            if (parent != null) parent.mkdirs();
            try (InputStream in = getAssets().open(path); OutputStream out = new FileOutputStream(dst)) {
                byte[] b = new byte[1 << 16];
                int n;
                while ((n = in.read(b)) > 0) out.write(b, 0, n);
            }
            return;
        }
        dst.mkdirs();
        for (String n : list) copyAssets(path + "/" + n, new File(dst, n));
    }

    private static void write(File f, String text) throws IOException {
        File parent = f.getParentFile();
        if (parent != null) parent.mkdirs();
        f.delete();   // also removes a symlink such as Ubuntu's resolv.conf
        try (OutputStream out = new FileOutputStream(f)) { out.write(text.getBytes(StandardCharsets.UTF_8)); }
    }

    private static void deleteTree(File f) {
        File[] kids = f.listFiles();
        if (kids != null && !java.nio.file.Files.isSymbolicLink(f.toPath())) for (File k : kids) deleteTree(k);
        f.delete();
    }
}
