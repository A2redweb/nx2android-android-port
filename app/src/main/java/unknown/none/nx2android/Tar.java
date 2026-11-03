package unknown.none.nx2android;

import android.system.Os;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;

/** Minimal tar reader (ustar, GNU long names, pax paths, symlinks, hard links) that keeps file modes usable for the app's own user. */
final class Tar {
    private Tar() {}

    static void extract(InputStream in, File root) throws IOException {
        byte[] h = new byte[512];
        String longName = null, longLink = null, paxPath = null, paxLink = null;
        int entries = 0;
        while (readFully(in, h, 512) == 512) {
            if (allZero(h)) break;
            String name = cstr(h, 0, 100);
            String link = cstr(h, 157, 100);
            long size = number(h, 124, 12);
            int mode = (int) number(h, 100, 8);
            char type = (char) (h[156] & 0xff);
            if (type == 0) type = '0';
            if (new String(h, 257, 5, StandardCharsets.US_ASCII).equals("ustar")) {
                String pre = cstr(h, 345, 155);
                if (!pre.isEmpty()) name = pre + "/" + name;
            }
            if (type == 'L') { longName = readText(in, size); continue; }
            if (type == 'K') { longLink = readText(in, size); continue; }
            if (type == 'x') {
                String[] pl = pax(readText(in, size));
                if (pl[0] != null) paxPath = pl[0];
                if (pl[1] != null) paxLink = pl[1];
                continue;
            }
            if (type == 'g') { skipData(in, size); continue; }
            if (longName != null) { name = longName; longName = null; }
            if (paxPath != null) { name = paxPath; paxPath = null; }
            if (longLink != null) { link = longLink; longLink = null; }
            if (paxLink != null) { link = paxLink; paxLink = null; }

            boolean data = type == '0' || type == '7';
            String clean = clean(name);
            if (clean.isEmpty() || clean.equals("..") || clean.startsWith("../") || clean.contains("/../")) {
                if (data) skipData(in, size);
                continue;
            }
            File f = new File(root, clean);
            switch (type) {
                case '5':
                    f.mkdirs();
                    chmod(f, (mode & 0777) | 0700);
                    break;
                case '0':
                case '7': {
                    File parent = f.getParentFile();
                    if (parent != null) parent.mkdirs();
                    f.delete();
                    try (OutputStream out = new FileOutputStream(f)) {
                        byte[] buf = new byte[1 << 16];
                        long left = size;
                        while (left > 0) {
                            int n = in.read(buf, 0, (int) Math.min(buf.length, left));
                            if (n < 0) throw new IOException("tar ended inside " + clean);
                            out.write(buf, 0, n);
                            left -= n;
                        }
                    }
                    skipBytes(in, (512 - size % 512) % 512);
                    chmod(f, (mode & 0777) | 0600);
                    break;
                }
                case '2': {
                    File parent = f.getParentFile();
                    if (parent != null) parent.mkdirs();
                    Files.deleteIfExists(f.toPath());
                    Files.createSymbolicLink(f.toPath(), Paths.get(link));
                    break;
                }
                case '1': {
                    File parent = f.getParentFile();
                    if (parent != null) parent.mkdirs();
                    File target = new File(root, clean(link));
                    Files.deleteIfExists(f.toPath());
                    try {
                        Files.createLink(f.toPath(), target.toPath());
                    } catch (IOException | UnsupportedOperationException | SecurityException e) {
                        Files.copy(target.toPath(), f.toPath(), StandardCopyOption.REPLACE_EXISTING);
                    }
                    break;
                }
                default:
                    break;   // devices, fifos: not needed inside proot
            }
            if (++entries % 4000 == 0) ProotService.log("  unpacked " + entries + " entries");
        }
        ProotService.log("  unpacked " + entries + " entries, done");
    }

    private static String clean(String n) {
        while (n.startsWith("./")) n = n.substring(2);
        while (n.startsWith("/")) n = n.substring(1);
        while (n.endsWith("/")) n = n.substring(0, n.length() - 1);
        return n.equals(".") ? "" : n;
    }

    private static void chmod(File f, int mode) {
        try { Os.chmod(f.getAbsolutePath(), mode); } catch (Exception ignored) { }
    }

    private static int readFully(InputStream in, byte[] b, int len) throws IOException {
        int got = 0;
        while (got < len) {
            int n = in.read(b, got, len - got);
            if (n < 0) break;
            got += n;
        }
        return got;
    }

    private static boolean allZero(byte[] b) {
        for (byte x : b) if (x != 0) return false;
        return true;
    }

    private static String cstr(byte[] b, int off, int len) {
        int end = off;
        while (end < off + len && b[end] != 0) end++;
        return new String(b, off, end - off, StandardCharsets.UTF_8);
    }

    private static long number(byte[] b, int off, int len) {
        if ((b[off] & 0x80) != 0) {
            long v = b[off] & 0x7f;
            for (int i = 1; i < len; i++) v = (v << 8) | (b[off + i] & 0xff);
            return v;
        }
        String s = cstr(b, off, len).trim();
        return s.isEmpty() ? 0 : Long.parseLong(s, 8);
    }

    private static void skipBytes(InputStream in, long n) throws IOException {
        byte[] buf = new byte[1 << 14];
        while (n > 0) {
            int r = in.read(buf, 0, (int) Math.min(buf.length, n));
            if (r < 0) throw new IOException("tar ended early");
            n -= r;
        }
    }

    private static void skipData(InputStream in, long size) throws IOException {
        skipBytes(in, size + (512 - size % 512) % 512);
    }

    private static String readText(InputStream in, long size) throws IOException {
        byte[] b = new byte[(int) size];
        if (readFully(in, b, b.length) != b.length) throw new IOException("tar ended early");
        skipBytes(in, (512 - size % 512) % 512);
        int end = b.length;
        while (end > 0 && b[end - 1] == 0) end--;
        return new String(b, 0, end, StandardCharsets.UTF_8);
    }

    /** pax records look like "27 path=some/long/name\n"; returns {path, linkpath}. */
    private static String[] pax(String s) {
        String[] r = new String[2];
        for (String line : s.split("\n")) {
            int sp = line.indexOf(' ');
            if (sp < 0) continue;
            String kv = line.substring(sp + 1);
            if (kv.startsWith("path=")) r[0] = kv.substring(5);
            else if (kv.startsWith("linkpath=")) r[1] = kv.substring(9);
        }
        return r;
    }
}
