# Telugu News Video Template — standalone Streamlit tool (Plan C, LocalAITV).
# Upload karo -> tool JOINS + overlays a reference-style news template:
#   intro clip -> [2s pillar/filler -> section clip] x N   (ek continuous broadcast)
#   with logo top-right + red strip + a SEAMLESS bottom scrolling Telugu ticker that runs
#   NON-STOP across the WHOLE video. Output 1920x1080. Telugu via ffmpeg/libass (Nirmala UI).
import os, subprocess, tempfile, shutil
import streamlit as st

W, H, FPS = 1280, 720, 25          # 720p output (~2x faster render than 1080p)
_S = H / 1080.0                    # scale factor: all overlay geometry derives from the 1080p design
# ffmpeg/ffprobe: local Windows build if present, else system binaries (Linux/cloud via apt), else imageio fallback
_WIN_FF = r"C:\Users\Sameer\Downloads\ffmpeg-8.0.1-essentials_build\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe"
if os.path.isfile(_WIN_FF):
    FF = _WIN_FF; FP = _WIN_FF.replace("ffmpeg.exe", "ffprobe.exe")
else:
    FF = shutil.which("ffmpeg") or "ffmpeg"
    FP = shutil.which("ffprobe") or "ffprobe"
    if not shutil.which("ffmpeg"):
        try:
            import imageio_ffmpeg; FF = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass


def _ensure_chromium(log=lambda *_a: None):
    """Make a Chromium available to Playwright on Linux/cloud. Streamlit Cloud installs the
    `playwright` pip pkg but NOT the browser, so we fetch it once per container. Never raises;
    returns True if a browser is ready (Windows: user installs locally, treated as ready)."""
    import sys
    if os.name == "nt":
        return True                       # local: `python -m playwright install chromium`
    if any(os.path.isfile(x) for x in ("/usr/bin/chromium", "/usr/bin/chromium-browser",
                                       "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable")):
        return True                       # cloud: Debian's `chromium` pkg (packages.txt) — no download
    flag = os.path.join(tempfile.gettempdir(), "pw_chromium_ready")
    if os.path.isfile(flag):
        return True
    try:
        log("installing Chrome engine (first run only, ~30-60s)…")
        r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                           capture_output=True, text=True, timeout=420)
        if r.returncode == 0:
            open(flag, "w").close()
            return True
        log(f"chromium install failed: {(r.stderr or r.stdout or '')[-200:]}")
        return False
    except Exception as e:
        log(f"chromium install error: {type(e).__name__}")
        return False


NIRMALA = r"C:\Windows\Fonts\Nirmala.ttf"
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
NOTO_TTF = os.path.join(FONTS_DIR, "NotoSansTelugu-Bold.ttf")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
VID_EXTS = (".mp4", ".mov", ".webm")
LOGO_EXTS = VID_EXTS + (".gif", ".png", ".jpg", ".jpeg", ".webp")


_CAT_ICON = {"district": "📍", "local": "🏙️", "national_state": "🏛️"}


def _list_media(subdir, exts, icon="🎬"):
    """Saved clips under <app>/<subdir>/ — flat files OR one level of category subfolders. {icon+label: path}."""
    base = os.path.join(APP_DIR, subdir)
    out = {}
    if not os.path.isdir(base):
        return out
    for entry in sorted(os.listdir(base)):
        p = os.path.join(base, entry)
        if os.path.isdir(p):                                        # a category subfolder (e.g. intros/district/)
            ci = _CAT_ICON.get(entry.lower(), icon)
            for f in sorted(os.listdir(p)):
                if f.lower().endswith(exts):
                    out[f"{ci} {os.path.splitext(f)[0]}"] = os.path.join(p, f)
        elif entry.lower().endswith(exts):                          # a flat file (e.g. fillers/guntur.mp4)
            out[f"{icon} {os.path.splitext(entry)[0]}"] = p
    return out
# Noto Sans Telugu shapes Telugu correctly; Nirmala-Bold dropped 'ా' vowel signs, Ramabhadra broke conjuncts
HEAD_FONT = "Noto Sans Telugu" if os.path.isfile(NOTO_TTF) else "Nirmala UI"
# measured template geometry (from the reference khammam_20.mp4)
RED = "0xB92F23"; BLUE = "0x06215B"
STRIP_H = round(86 * _S)          # bottom strip height (scaled)
STRIP_Y = H - STRIP_H             # strip pinned to bottom (covers NotebookLM's watermark)
RED_W = round(543 * _S)
LOGO_W = round(330 * _S); LOGO_Y = round(34 * _S); LOGO_X = W - LOGO_W - round(30 * _S)


def _esc(t):  # escape for ass text
    return (t or "").replace("\n", " ").replace("{", "(").replace("}", ")").strip()

def _tc(s):
    h = int(s // 3600); m = int((s % 3600) // 60); sec = s % 60
    return f"{h}:{m:02d}:{sec:05.2f}"

def _dur(path):
    r = subprocess.run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except Exception: return 0.0

SLANT = round(46 * _S)                                # red parallelogram slant (px, scaled)
TICK_X = RED_W + SLANT + round(8 * _S)                 # ticker starts just past the slanted red edge
TICK_SIZE = round(56 * _S)                             # ticker font size (scaled)
TICK_SPEED = round(150 * _S)                           # ticker scroll px/sec (scaled)

def _ticker_image(text, D):
    """Shape the ticker text ONCE (correct Telugu, no per-frame libass re-shaping) into a transparent
    strip, then TILE it 2x horizontally. The video scrolls this pre-rendered IMAGE by a moving crop —
    so glyphs can never mix/jitter while scrolling. Returns (png_path, cycle_width_px)."""
    import cv2, numpy as np
    unit = _esc(text) + "         •         "
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 20000\nPlayResY: %d\nWrapStyle: 2\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
            "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Tk,%s,%d,&H00FFFFFF,&H00FFFFFF,&H00301A0A,&H00000000,1,0,0,0,100,100,0,0,1,0.8,0,4,0,0,0,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            % (STRIP_H, HEAD_FONT, TICK_SIZE))
    y = STRIP_H // 2
    # 1) measure one unit's rendered width (on solid bg so we can autodetect it)
    pa = os.path.join(D, "tprobe.ass")
    open(pa, "w", encoding="utf-8").write(head + f"Dialogue: 0,{_tc(0)},{_tc(9)},Tk,,0,0,0,,{{\\an4\\pos(0,{y})}}{unit}\n")
    pp = os.path.join(D, "tprobe.png")
    subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s=8000x{STRIP_H}:d=1",
                    "-vf", "subtitles=tprobe.ass:fontsdir=.", "-frames:v", "1", pp], check=True, cwd=D)
    g = cv2.imread(pp, cv2.IMREAD_GRAYSCALE)
    cols = (g > 30).any(axis=0)
    uw = (int(np.where(cols)[0].max()) + 12) if cols.any() else max(240, len(unit) * TICK_SIZE // 2)
    reps = int((W - TICK_X + 500) / uw) + 2               # enough units so one cycle is wider than the visible ticker
    cyc = uw * reps
    # 2) render TWO cycles (short string -> perfect shaping) to a TRANSPARENT strip, crop to exactly 2*cyc
    ca = os.path.join(D, "tcyc.ass")
    open(ca, "w", encoding="utf-8").write(head + f"Dialogue: 0,{_tc(0)},{_tc(9)},Tk,,0,0,0,,{{\\an4\\pos(0,{y})}}{unit * (reps * 2)}\n")
    img = os.path.join(D, "tick2x.png")
    # render on the SAME navy as the strip (opaque) -> overlay is navy-on-navy = seamless, no alpha needed
    subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={BLUE}:s={cyc * 2 + 80}x{STRIP_H}:d=1",
                    "-vf", f"subtitles=tcyc.ass:fontsdir=.,crop={cyc * 2}:{STRIP_H}:0:0",
                    "-frames:v", "1", img], check=True, cwd=D)
    return img, cyc

def _overlay_ass(path, red_text, sections):
    """Static overlay track drawn ONLY during content sections (fillers stay clean, like the reference):
    the slanted RED parallelogram + its label. The scrolling ticker is a separate scrolled IMAGE."""
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Shape,Arial,20,&H00232FB9,&H00232FB9,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Red,{HEAD_FONT},44,&H00FFFFFF,&H00FFFFFF,&H00301A0A,&H00000000,1,0,0,0,100,100,0,0,1,0.8,0,4,0,0,0,1
Style: Tick,{HEAD_FONT},56,&H00FFFFFF,&H00FFFFFF,&H00301A0A,&H00000000,1,0,0,0,100,100,0,0,1,0.8,0,4,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    yc = STRIP_Y + STRIP_H // 2                    # vertical centre of the (raised) strip
    ev = []
    for (ss, se) in sections:
        # slanted RED parallelogram behind the label, only during this content section
        ev.append(f"Dialogue: 1,{_tc(ss)},{_tc(se)},Shape,,0,0,0,,"
                  f"{{\\an7\\pos(0,{STRIP_Y})\\1c&H232FB9&\\p1}}m 0 0 l {RED_W} 0 {RED_W+SLANT} {STRIP_H} 0 {STRIP_H}{{\\p0}}")
        if red_text:
            ev.append(f"Dialogue: 1,{_tc(ss)},{_tc(se)},Red,,0,0,0,,{{\\an4\\pos(30,{yc})}}{_esc(red_text)}")
    open(path, "w", encoding="utf-8").write(head + "\n".join(ev) + "\n")

def _normalize(src, out):
    """scale+pad any clip to 1920x1080 25fps + ensure an audio track (silent if none).
    Pad colour is BLACK (never white) so odd-aspect clips never look like a 'white page'."""
    has_audio = "audio" in subprocess.run([FP, "-v", "error", "-show_entries", "stream=codec_type",
                 "-of", "csv=p=0", src], capture_output=True, text=True).stdout
    cmd = [FF, "-y", "-v", "error", "-i", src]
    if not has_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest"]
    cmd += ["-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                   f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,fps={FPS},setsar=1",
            "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", out]
    subprocess.run(cmd, check=True)

def _endcard_start(src):
    """Detect the trailing NotebookLM 'notebooklm.google.com' endcard — a near-white plate at the very
    end — and return the time (s) where it begins, or None. Content slides are ~85% white; the endcard
    is ~98%+ white. So a sustained >=96%-white run reaching the video end = the endcard, and we cut it."""
    try:
        import cv2, numpy as np
    except Exception:
        return None
    dur = _dur(src)
    if dur < 4:
        return None
    cap = cv2.VideoCapture(src)
    run_start, tt = None, max(0.0, dur - 14.0)
    while tt < dur - 0.15:
        cap.set(cv2.CAP_PROP_POS_MSEC, tt * 1000); ok, fr = cap.read()
        if ok:
            white = (fr >= 232).all(axis=2).mean()
            run_start = (run_start if run_start is not None else tt) if white >= 0.96 else None
        tt += 0.4
    cap.release()
    if run_start is not None and 0.6 <= (dur - run_start) <= 9.0:
        return run_start
    return None

def _trim_to(src, end, out):
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-t", f"{end:.3f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", out], check=True)
    return out

def _parse_times(s):
    """'0:58, 2:30, 4:15' or seconds -> [58.0, 150.0, 255.0] (section start seconds)."""
    out = []
    for tok in (s or "").replace(",", " ").split():
        try:
            if ":" in tok:
                sec = 0.0
                for p in tok.split(":"): sec = sec * 60 + float(p)
                out.append(sec)
            else:
                out.append(float(tok))
        except Exception:
            pass
    return out

def _detect_sections(src, step=0.5):
    """Auto-find the NotebookLM 'big number' section cards (1..5) and return each section's START
    time (s). Instead of guessing from shapes (which confused content speech-bubbles, temples, and
    big in-content numbers like '20'/'32' with real section cards), we now actually READ the number:
    locate the giant white digit in the frame's left strip and OCR it with Tesseract — a frame counts
    as a section card ONLY if that region reads as a SINGLE digit 1-9. This works across every
    template (pale OR vivid backgrounds, Telugu OR English content) because centred content numbers
    and title/date text never sit as a lone digit in the far-left strip. Guards:
      • a real card must PERSIST ≥~2.5s (>=5 hits) — brief OCR misreads are dropped, and
      • each start is refined to the card's onset so no previous slide flashes in after the 2s filler.
    The exact digit VALUE doesn't matter (we only need the card's position); an occasional 1-vs-4
    misread is harmless. Returns [] if OpenCV/Tesseract are unavailable or nothing is found — the app
    then simply skips auto-fillers, and the user can type exact times in 'Section Start Times'."""
    try:
        import cv2, numpy as np, pytesseract, re
        pytesseract.get_tesseract_version()
    except Exception:
        return []
    def _ocr(im):
        for psm in ("10", "8", "7", "13"):
            t = re.sub(r"[^1-9]", "", pytesseract.image_to_string(
                im, config="--psm %s -c tessedit_char_whitelist=123456789" % psm).strip())
            if len(t) == 1:
                return t
        return ""
    def _try(g, comp, x, y, ww, hh):
        """OCR the digit from its bounding box — Otsu of the natural crop first (best for clean digits),
        then (if a fill component is given) its dark SILHOUETTE, which excludes an emblem drawn inside it."""
        pad = 15
        gc = g[max(0, y - pad):y + hh + pad, max(0, x - pad):x + ww + pad]
        if gc.size:
            _, ot = cv2.threshold(gc, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            if ot.mean() < 127:
                ot = 255 - ot                                             # Tesseract wants a dark glyph on a light ground
            r = _ocr(cv2.copyMakeBorder(ot, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255))
            if r:
                return r
        if comp is not None:
            cc = cv2.dilate(comp[max(0, y - pad):y + hh + pad, max(0, x - pad):x + ww + pad] * 255, np.ones((3, 3), np.uint8))
            if cc.size:
                r = _ocr(cv2.copyMakeBorder(255 - cc, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255))
                if r:
                    return r
        return ""
    def white_digit(fr):
        """Method A — isolate the digit by its WHITE FILL (best on vivid/coloured backgrounds). Strict
        pure-white pass, then a looser pass + morphological CLOSE that recovers a digit an emblem/shield is
        drawn across (e.g. Vijayanagaram's '2' with a police crest). An OUTLINE GATE (the glyph must be
        hugged by a dark outline) skips content light-blobs. Returns the OCR'd digit or ''."""
        h, w, _ = fr.shape
        L = fr[int(.06 * h):int(.95 * h), 0:int(.26 * w)]                 # left strip where the giant digit sits
        g = cv2.cvtColor(L, cv2.COLOR_BGR2GRAY); s = cv2.cvtColor(L, cv2.COLOR_BGR2HSV)[:, :, 1]
        Hh, Ww = L.shape[:2]
        for thr, close in ((232, False), (212, True)):
            white = ((g >= thr) & (s <= 60)).astype(np.uint8)
            if close:
                white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
            n, lab, st, _c = cv2.connectedComponentsWithStats(white, 8)
            if n <= 1:
                continue
            i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])); x, y, ww, hh, area = st[i]
            if not (hh / Hh >= 0.5 and ww / Ww <= 0.85 and 0.14 <= area / (ww * hh + 1) <= 0.95):
                continue                                                   # one tall, digit-like glyph
            comp = (lab == i).astype(np.uint8)
            ring = cv2.dilate(comp, np.ones((5, 5), np.uint8)) - comp      # OUTLINE GATE: a real digit is hugged by a
            rs = int(ring.sum())                                            # dark outline; content light-blobs are not
            if rs == 0 or int(((g <= 110) & (ring > 0)).sum()) / rs < 0.22:
                continue
            r = _try(g, comp, x, y, ww, hh)
            if r:
                return r
        return ""
    def black_digit(fr):
        """Method B — isolate the digit by its thick BLACK OUTLINE (background-agnostic). Essential when the
        digit is a LIGHT colour on a LIGHT background (e.g. Tirupati's '1' and '3'), where the white-fill
        mask of Method A merges the digit into the background. Used ONLY to fill cards Method A missed."""
        h, w, _ = fr.shape
        L = fr[int(.06 * h):int(.95 * h), 0:int(.26 * w)]
        g = cv2.cvtColor(L, cv2.COLOR_BGR2GRAY); Hh, Ww = L.shape[:2]
        black = cv2.morphologyEx((g <= 110).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, lab, st, _c = cv2.connectedComponentsWithStats(black, 8)
        if n <= 1:
            return ""
        i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])); x, y, ww, hh, area = st[i]
        if not (hh / Hh >= 0.55 and ww / Ww <= 0.85 and 0.03 <= area / (Hh * Ww) <= 0.22):
            return ""
        return _try(g, None, x, y, ww, hh)
    def count_boxes(fr):                          # the intro Table-of-Contents shows ONE white box per section
        h, w, _ = fr.shape; A = h * w
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        white = cv2.morphologyEx((g >= 205).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        n, _l, st, _c = cv2.connectedComponentsWithStats(white, 8)
        b = 0
        for i in range(1, n):
            _x, _y, ww, hh, area = st[i]
            if 0.03 * A <= area <= 0.16 * A and ww > 0.15 * w and hh > 0.12 * h \
               and 0.6 <= ww / hh <= 3.0 and area / (ww * hh) > 0.75:      # a big, filled, ~rectangular white card
                b += 1
        return b
    cap = cv2.VideoCapture(src); fps = cap.get(cv2.CAP_PROP_FPS) or 25
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    def frame_at(t):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, fr = cap.read()
        return fr if ok else None
    # ANCHOR: the intro Table-of-Contents tells us HOW MANY sections to expect (count its numbered boxes)
    # and WHERE it ends (last multi-box frame) — so a title/TOC glyph is never mistaken for a section card.
    n_expected, toc_end, t = 0, 0.0, 8.0
    while t < min(dur - 2, 70):
        fr = frame_at(t)
        if fr is not None:
            b = count_boxes(fr); n_expected = max(n_expected, b)
            if b >= 3:
                toc_end = t
        t += 1.0
    n_expected = n_expected if 2 <= n_expected <= 8 else 0     # only trust a sane count
    # ONE pass: Method A (white fill) is primary; only where it finds nothing do we try Method B (black outline).
    wd, bd, t = [], [], 6.0
    while t < dur - 2:
        fr = frame_at(t)
        if fr is not None:
            if white_digit(fr):
                wd.append(round(t, 1))
            elif black_digit(fr):
                bd.append(round(t, 1))
        t += step
    def _clus(hh):
        ev = []
        for tt in hh:
            if ev and tt - ev[-1][-1] <= 2.0:
                ev[-1].append(tt)
            else:
                ev.append([tt])
        return [c for c in ev if len(c) >= 5]                  # a real card is held ≥~2.5s
    wc, bc = _clus(wd), _clus(bd)
    cards = sorted(c[0] for c in wc)
    if n_expected and len(cards) > n_expected:                # more than the TOC says -> keep the most-persistent N
        cards = sorted(sorted(wc, key=len, reverse=True)[i][0] for i in range(n_expected))
    if n_expected and len(cards) < n_expected:                # a light-on-light card Method A missed ->
        for c in sorted(bc, key=len, reverse=True):            # rescue it from Method B, past the TOC and well-spaced
            if len(cards) >= n_expected:
                break
            if c[0] > toc_end and all(abs(c[0] - x) > 40 for x in cards):
                cards.append(c[0])
    cards.sort()
    def _present(t):
        fr = frame_at(t)
        return fr is not None and bool(white_digit(fr) or black_digit(fr))
    starts = []
    for c0 in cards:
        onset = c0; tt = round(c0 - 0.1, 2)                   # refine back to the card's first frame (kills previous-slide flash)
        while tt > c0 - 1.0 and _present(tt):
            onset = tt; tt = round(tt - 0.1, 2)
        starts.append(round(max(0.0, onset - 0.1), 1))
    cap.release()
    return starts

def _split_at(src, times, D, end=None):
    """Cut the ONE long normalized video `src` into sections at the given start times (seconds).
    Accurate (frame-level) cuts. `end` caps the last section (used to drop the NotebookLM endcard).
    Returns the section clip paths in order."""
    total = end if end else _dur(src)
    cuts = sorted(set(x for x in times if 0 < x < total))
    pts = [0.0] + cuts + [total]
    segs = []
    for i in range(len(pts) - 1):
        s, e = pts[i], pts[i + 1]
        seg = os.path.join(D, f"seg{i}.mp4")
        # -ss BEFORE -i = fast AND frame-accurate (decodes only from the preceding keyframe)
        subprocess.run([FF, "-y", "-v", "error", "-ss", f"{s:.3f}", "-i", src, "-t", f"{e - s:.3f}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", seg], check=True)
        segs.append(seg)
    return segs

def _concat(paths, out):
    lst = out + ".txt"
    open(lst, "w").write("\n".join(f"file '{p.replace(chr(92), '/')}'" for p in paths))
    subprocess.run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", out], check=True)
    return out


# ---------------- YouTube Shorts maker ----------------
SHORT_W, SHORT_H, SHORT_MAX = 1080, 1920, 60          # Shorts = vertical 9:16, max 60s

def make_short(src, out, start=0.0, length=60.0, fill="blur", progress=None):
    """ANY input video -> a YouTube-Shorts-ready vertical mp4 (1080x1920, <=60s, h264/aac, faststart).
    fill='blur' = video fitted on a blurred vertical bg (nothing cropped away);
    fill='crop' = centre-cropped to fill the whole screen."""
    log = progress or (lambda x: None)
    length = max(1.0, min(float(SHORT_MAX), float(length)))
    has_audio = "audio" in subprocess.run([FP, "-v", "error", "-show_entries", "stream=codec_type",
                                           "-of", "csv=p=0", src], capture_output=True, text=True).stdout
    if fill == "crop":
        vf = f"crop='min(iw,ih*9/16)':ih,scale={SHORT_W}:{SHORT_H},setsar=1"
    else:
        vf = (f"split[a][b];[a]scale={SHORT_W}:{SHORT_H}:force_original_aspect_ratio=increase,"
              f"crop={SHORT_W}:{SHORT_H},boxblur=22:2[bg];[b]scale={SHORT_W}:-2[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    cmd = [FF, "-y", "-v", "error", "-ss", str(start), "-i", src]
    if not has_audio:                                  # Shorts play better with an audio track
        cmd += ["-f", "lavfi", "-t", f"{length:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += ["-t", f"{length:.2f}", "-vf", vf, "-r", "30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart", out]
    log(f"making {length:.0f}s vertical Short ({SHORT_W}x{SHORT_H})…")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("shorts render failed: " + (r.stderr or "unknown ffmpeg error")[-500:])
    log(f"DONE → {out}")
    return out


def render(main_clips, intro, logo, red_text, bottom_text, section_titles, out_path,
           pillar_clip=None, split_times=None, progress=None):
    """intro + [pillar filler -> section] x N, with ONE continuous logo+strip+ticker overlay
    over the whole content. `main_clips` = list of section clips; OR one long clip + `split_times`
    (section start seconds) -> the long clip is cut into sections automatically."""
    log = progress or (lambda x: None)
    D = tempfile.mkdtemp(prefix="news_")
    if os.path.isfile(NOTO_TTF):                        # give libass the Noto Telugu font (fontsdir=.)
        shutil.copy(NOTO_TTF, os.path.join(D, "NotoSansTelugu-Bold.ttf"))
    if isinstance(main_clips, str):
        main_clips = [main_clips]

    # 1) normalize the 2s pillar/filler once (reused before every section)
    pillar_n = None
    if pillar_clip:
        log("normalizing 2s filler clip…")
        pillar_n = os.path.join(D, "pillar_n.mp4"); _normalize(pillar_clip, pillar_n)
    pil_dur = _dur(pillar_n) if pillar_n else 0.0

    # 2) figure out the SECTIONS:
    #    - many clips uploaded          -> each clip is one section
    #    - ONE long clip + split_times  -> cut that video at those times into sections
    log("normalizing / splitting content…")
    norm = []
    for i, clip in enumerate(main_clips):
        n = os.path.join(D, f"main_n{i}.mp4"); _normalize(clip, n); norm.append(n)
    preroll = False
    if len(norm) == 1:
        times = split_times
        if not times:                                     # ⑦ empty -> auto-find the big number cards
            log("auto-detecting section number cards (1,2,3…)…")
            times = _detect_sections(norm[0])
            log(f"found {len(times)} sections: " + (", ".join(f'{int(t//60)}:{int(t%60):02d}' for t in times) or "none"))
        cend = _endcard_start(norm[0])                    # drop trailing NotebookLM 'notebooklm.google.com' endcard
        if cend:
            log(f"removing NotebookLM endcard (from {int(cend//60)}:{int(cend%60):02d})…")
        if times:
            log(f"cutting into {len(times) + 1} sections, filler before each…")
            sections = _split_at(norm[0], times, D, end=cend)
            preroll = True                                # segment[0] = title/TOC -> no filler before it
        else:                                             # nothing found -> single section (endcard trimmed)
            sections = [_trim_to(norm[0], cend, norm[0].replace(".mp4", "_tc.mp4")) if cend else norm[0]]
    else:
        sections = []                                     # each clip is a section; trim its endcard if present
        for i, c in enumerate(norm):
            ec = _endcard_start(c)
            if ec:
                log(f"removing NotebookLM endcard from clip {i+1}…")
                sections.append(_trim_to(c, ec, c.replace(".mp4", "_tc.mp4")))
            else:
                sections.append(c)

    # 3) build the raw timeline: [filler, section] for each section; record the SECTION windows
    #    (fillers stay CLEAN — no strip/ticker/logo — exactly like the reference eluru.mp4).
    #    On split: title/TOC pre-roll (segment 0) gets NO leading filler; fillers go before cards 1..N.
    segs, sec_windows, t = [], [], 0.0
    for i, sec_n in enumerate(sections):
        if pillar_n and not (i == 0 and preroll):
            segs.append(pillar_n); t += pil_dur           # 2s CLEAN filler BEFORE this section card
        segs.append(sec_n)
        d = _dur(sec_n)
        sec_windows.append((t, t + d))                    # overlay only here
        t += d
    content_dur = t

    log("joining sections + fillers…")
    content_raw = _concat(segs, os.path.join(D, "content_raw.mp4"))

    # 4) overlay pass: navy strip + slanted red label + scrolling ticker + logo — ONLY on sections.
    #    The strip's Telugu (red label + ticker) is rendered by Chrome/Playwright (best shaping);
    #    falls back to ffmpeg/libass if Playwright isn't available.
    en = "+".join(f"between(t\\,{s:.2f}\\,{e:.2f})" for s, e in sec_windows) or "0"
    label_png, tick_img, cyc, ass = None, None, 0, None
    try:
        import sys, json
        _ensure_chromium(log)             # cloud: fetch Chromium if missing (Streamlit Cloud needs this)
        # Playwright sync API can't run inside Streamlit's event loop -> run it in a CLEAN subprocess
        json.dump({"ticker": bottom_text or "", "label": red_text or ""},
                  open(os.path.join(D, "pw_params.json"), "w", encoding="utf-8"))
        pw_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pw_render.py")
        log("rendering strip text with Chrome (Playwright)…")
        r = subprocess.run([sys.executable, pw_py, D], capture_output=True, text=True, timeout=150)
        lp, tp, cp = (os.path.join(D, x) for x in ("pw_label.png", "pw_ticker.png", "pw_cyc.txt"))
        if r.returncode == 0 and all(os.path.isfile(x) for x in (lp, tp, cp)):
            label_png, tick_img, cyc = lp, tp, int(open(cp).read().strip())
        else:
            raise RuntimeError((r.stderr or r.stdout or "pw_render failed")[-400:])
    except Exception as e:
        log(f"Playwright unavailable ({type(e).__name__}) → libass fallback")
        ass = os.path.join(D, "overlay.ass"); _overlay_ass(ass, red_text, sec_windows)
        if bottom_text:
            tick_img, cyc = _ticker_image(bottom_text, D)

    fc = f"[0:v]drawbox=x=0:y={STRIP_Y}:w={W}:h={STRIP_H}:color={BLUE}:t=fill:enable='{en}'[bg];"
    inputs = ["-i", content_raw]; extra = []; idx = 1; cur = "bg"
    if logo:
        logo_n = os.path.join(D, "logo" + os.path.splitext(logo)[1]); shutil.copy(logo, logo_n)
        if os.path.splitext(logo)[1].lower() in (".mp4", ".mov", ".webm", ".gif"):
            inputs += ["-stream_loop", "-1", "-i", logo_n]        # animated logo -> loops continuously
        else:
            inputs += ["-loop", "1", "-i", logo_n]
        fc += (f"[{idx}:v]colorkey=0xFFFFFF:0.14:0.08,scale={LOGO_W}:-1[lg];"    # key out the logo's white background
               f"[{cur}][lg]overlay=x={LOGO_X}:y={LOGO_Y}:shortest=1:enable='{en}'[o1];")
        cur = "o1"; idx += 1; extra = ["-shortest"]
    if tick_img:
        inputs += ["-loop", "1", "-i", tick_img]; vw = W - TICK_X
        fc += (f"[{idx}:v]crop=w={vw}:h={STRIP_H}:x=mod(t*{TICK_SPEED}\\,{cyc}):y=0[tk];"   # moving crop = smooth pixel scroll
               f"[{cur}][tk]overlay=x={TICK_X}:y={STRIP_Y}:enable='{en}'[o2];")
        cur = "o2"; idx += 1; extra = ["-shortest"]
    if label_png:                                            # Chrome red-slant label (transparent) on the strip
        inputs += ["-loop", "1", "-i", label_png]
        fc += f"[{cur}][{idx}:v]overlay=x=0:y={STRIP_Y}:enable='{en}'[o3];"
        cur = "o3"; idx += 1; extra = ["-shortest"]
    fc += (f"[{cur}]subtitles={os.path.basename(ass)}:fontsdir=.[v]" if ass else f"[{cur}]null[v]")
    content = os.path.join(D, "content.mp4")
    subprocess.run([FF, "-y", "-v", "error"] + inputs + ["-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
                    "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2"] + extra + [content],
                   check=True, cwd=D)

    # 4) intro (clean channel branding) + content
    parts = []
    if intro:
        log("normalizing intro…"); intro_n = os.path.join(D, "intro_n.mp4"); _normalize(intro, intro_n); parts.append(intro_n)
    parts.append(content)
    log("final join…")
    final = _concat(parts, os.path.join(D, "joined.mp4"))
    # web-optimize (moov atom to front). Some concat outputs choke `-c copy`, so fall back to a
    # full re-encode (bulletproof) and, if even that fails, surface ffmpeg's REAL error (not just "254").
    try:
        subprocess.run([FF, "-y", "-v", "error", "-i", final, "-c", "copy", "-movflags", "+faststart", out_path],
                       check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        log("faststart copy failed — re-encoding final (fallback)…")
        r = subprocess.run([FF, "-y", "-v", "error", "-i", final,
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
                            "-movflags", "+faststart", out_path], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("final render failed: " + (r.stderr or r.stdout or "unknown ffmpeg error")[-600:])
    log(f"DONE → {out_path}")
    shutil.rmtree(D, ignore_errors=True)                # free the tmpfs working dir (keeps /tmp from filling up)
    return out_path


# ---------------- App-download branding: filler + video + end card ----------------
# Koi bhi video -> [filler] + video + [app download end card].
# NOTE: mp4 ke andar clickable link ka koi provision hi nahi hai (format me hyperlink hota hi
# nahi). Isliye card par URL sirf DIKHTA hai, aur clickable copy app_caption() se milti hai —
# wo caption Facebook/YouTube pe paste karte hi link apne aap clickable ban jaata hai.
APP_URL = "https://play.google.com/store/apps/details?id=com.localaitv.app&pcampaignid=web_share"
APP_URL_SHORT = "play.google.com/store/apps/details?id=com.localaitv.app"
ENDCARD_S = 6

ENDCARD_DIR = os.path.join(APP_DIR, "assets", "endcards")
CARD_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _endcard_from_image(img, out, secs=ENDCARD_S):
    """Card image ko clip bana do. Image ka aspect video se alag ho to sides usi image ke
    blurred copy se bharte hain — kaali pattiyon se kaafi behtar dikhta hai."""
    fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"boxblur=30:3,eq=brightness=-0.12[bg];"
          f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fade=t=in:st=0:d=0.5,format=yuv420p[v]")
    subprocess.run([FF, "-y", "-v", "error", "-loop", "1", "-t", str(secs), "-i", img,
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-t", str(secs),
                    "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", out], check=True)
    return out


def make_endcard(out, D, secs=ENDCARD_S, card_file=None):
    """assets/endcards/ ki card file -> end card clip (W x H, silent audio).

    Card ZAROORI hai. Pehle yahan ek auto-generate fallback tha, par wo chupke se lag jaata
    tha jab city match nahi hoti — aur video galat card ke saath nikal jaata tha. Ab card na
    mile to saaf error aata hai, taaki pata chale ki city/card chunna reh gaya."""
    if not (card_file and os.path.isfile(card_file)):
        raise RuntimeError("End card nahi mila — City likho ya 'End card' dropdown se chuno.")
    if card_file.lower().endswith(CARD_IMG_EXTS):
        return _endcard_from_image(card_file, out, secs)
    _normalize(card_file, out)                     # animated card — apni poori length chalega
    return out


def app_caption(title="", city=""):
    """Yahi wo jagah hai jahan link SACH ME clickable banta hai — post ka caption/description."""
    tags = "#LocalAITV #TeluguNews" + (f" #{city.strip().replace(' ', '')}" if city.strip() else "")
    return (f"{title.strip() or 'మీ ఊరి తాజా వార్తలు 📺'}\n\n"
            f"📱 LocalAI TV యాప్ డౌన్‌లోడ్ చేసుకోండి — ఉచితం!\n"
            f"మీ ఊరి వార్తలు, మీ ఫోన్‌లోనే.\n\n"
            f"👇 ఇక్కడ క్లిక్ చేయండి\n{APP_URL}\n\n{tags}\n")


def brand_video(src, out, D, endcard, filler=None, secs=ENDCARD_S, filler_at_start=False,
                filler_before_card=True, progress=None):
    """[filler?] + src + [filler] + [app end card] -> out.

    filler_at_start default FALSE hai: news app se bane videos me filler pehle se laga hota hai,
    to yahan dobara lagane se shuru me do baar chal jaata hai. Kaccha/raw video ho tabhi ON karo.
    Filler ek hi baar normalize hota hai; concat list me wahi file dobara likh dete hain."""
    log = progress or (lambda *_a: None)
    fill_n, parts = None, []
    if filler and os.path.isfile(filler):
        log("normalizing filler…")
        fill_n = os.path.join(D, "b_filler.mp4")
        _normalize(filler, fill_n)
        if filler_at_start:
            parts.append(fill_n)
    log("normalizing video…")
    _normalize(src, os.path.join(D, "c_main.mp4"))
    parts.append(os.path.join(D, "c_main.mp4"))
    if fill_n and filler_before_card:
        parts.append(fill_n)                              # app card se pehle wahi filler dobara
    # End card user chunta hai — koi auto-detect nahi. Naam se aur watermark-OCR se guess
    # karke dekha tha, dono galat card laga dete the aur pata render ke baad chalta tha.
    log(f"end card: {os.path.basename(endcard)}")
    parts.append(make_endcard(os.path.join(D, "d_endcard.mp4"), D, secs, card_file=endcard))
    log("joining…")
    _concat(parts, out)
    log(f"DONE → {out}")
    return out


def _brand_panel(D):
    """UI: koi bhi video -> filler shuru me + app download card end me + ready caption."""
    st.caption("Koi bhi video daalo → **shuru me filler** + **end me app download card** lag jaayega, "
               "aur saath me **caption** milega jisme link **clickable** hota hai.")
    up = st.file_uploader("🎬 Video (any format)", key="br_up",
                          type=["mp4", "mov", "webm", "mkv", "avi", "m4v", "mpeg", "mpg", "flv", "wmv", "3gp", "ts"])
    _f = _list_media("fillers", VID_EXTS, "📢")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        pick = st.selectbox("🎞️ Filler (shuru me)", ["— none —"] + list(_f), key="br_fill") if _f else None
        f_up = st.file_uploader("…ya filler upload karo", key="br_fup", type=list(e[1:] for e in VID_EXTS))
    with c2:
        secs = st.slider("⏱️ End card kitne second", 3, 12, ENDCARD_S, 1, key="br_secs")
        city = st.text_input("📍 City (optional)", "", key="br_city", placeholder="Rajahmundry",
                             help="Khaali chhod do — card filler ya video ke naam se apne aap "
                                  "chun jaata hai. Sirf tab bharo jab auto galat chune.")
    k1, k2 = st.columns(2)
    with k1:
        at_start = st.checkbox("▶️ Filler **shuru me** bhi lagao", True, key="br_start",
                               help="Video me filler pehle se laga ho (news app se bana ho) to ye OFF "
                                    "kar do — warna shuru me do baar chalega.")
    with k2:
        twice = st.checkbox("🔁 Filler **app card se pehle**", True, key="br_twice",
                            help="Video khatam → wahi filler → app download card.")
    title = st.text_input("📰 Caption ki pehli line", "", key="br_title",
                          placeholder="మీ ఊరి తాజా వార్తలు 📺")

    _cards = _list_media("endcards", CARD_IMG_EXTS + VID_EXTS, "🖼️")
    NONE = "— chuno —"
    e1, e2 = st.columns(2, gap="large")
    with e1:
        card_pick = st.selectbox("🖼️ End card  ·  ZAROORI", [NONE] + list(_cards), key="br_card",
                                 help="Jis city ka video hai wahi card chuno. Filler jaisa hi — "
                                      "khud chunna hai, apne aap nahi hoga.")
    with e2:
        card_up = st.file_uploader("…ya card upload karo", key="br_cup",
                                   type=[e[1:] for e in CARD_IMG_EXTS + VID_EXTS])

    if card_up:
        st.success(f"🖼️ End card: **{card_up.name}**")
    elif card_pick in _cards:
        st.success(f"🖼️ End card: **{os.path.basename(_cards[card_pick])}**")
    else:
        st.warning("🖼️ End card chuno — iske bina video nahi banega.")

    if st.button("🎬 Video + app card banao", type="primary", use_container_width=True, key="br_go"):
        if not up:
            st.error("Pehle video daalo."); return
        src = os.path.join(D, os.path.basename(up.name))
        with open(src, "wb") as w:
            w.write(up.getbuffer())
        filler = None
        if f_up:
            filler = os.path.join(D, os.path.basename(f_up.name))   # basename = path traversal se bacha
            with open(filler, "wb") as w:
                w.write(f_up.getbuffer())
        elif pick and pick in _f:
            filler = _f[pick]
        card = None
        if card_up:
            card = os.path.join(D, "brand_card" + os.path.splitext(card_up.name)[1])
            with open(card, "wb") as w:
                w.write(card_up.getbuffer())
        elif card_pick in _cards:
            card = _cards[card_pick]
        if not card:
            st.error("🖼️ **End card chuno** — dropdown se city ka card select karo, "
                     "ya apna card upload karo."); return
        out = os.path.join(D, "branded.mp4")
        box, logs = st.empty(), []
        def prog(m): logs.append(str(m)); box.code("\n".join(logs[-8:]))
        try:
            with st.spinner("Ban raha hai…"):
                brand_video(src, out, D, card, filler=filler, secs=secs,
                            filler_at_start=at_start, filler_before_card=twice, progress=prog)
            st.session_state.br_out = out
            st.session_state.br_cap = app_caption(title, city)
        except Exception as e:
            st.error("Branding error: " + str(e)); return

    out = st.session_state.get("br_out")
    if out and os.path.isfile(out):
        st.success("✅ Ready!")
        st.video(out)
        with open(out, "rb") as f:
            st.download_button("⬇️ Download video", f, "branded.mp4", "video/mp4",
                               use_container_width=True, key="br_dl")
        st.markdown("#### 📋 Caption — ye paste karo, link yahan **clickable** banega")
        st.code(st.session_state.get("br_cap", ""), language=None)
        st.download_button("⬇️ caption.txt", st.session_state.get("br_cap", "").encode("utf-8"),
                           "caption.txt", "text/plain", use_container_width=True, key="br_capdl")


# ---------------- Streamlit UI ----------------
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap');
:root{
  --bg0:#050816; --card:rgba(255,255,255,.05); --card2:rgba(255,255,255,.03);
  --bd:rgba(255,255,255,.08); --bd2:rgba(255,255,255,.14);
  --purple:#7C3AED; --pink:#EC4899; --orange:#FF8A00; --blue:#38BDF8; --green:#22C55E;
  --txt:#EAECF5; --muted:#8B93B0;
}

/* ---------- base ---------- */
.stApp{ background:
    radial-gradient(1200px 700px at 8% -10%, rgba(124,58,237,.20), transparent 55%),
    radial-gradient(1100px 650px at 100% 0%, rgba(56,189,248,.14), transparent 50%),
    radial-gradient(1000px 800px at 60% 120%, rgba(236,72,153,.14), transparent 55%),
    var(--bg0); background-attachment:fixed; }
html,body,[class*="css"],.stApp,button,input,textarea{ font-family:'Plus Jakarta Sans','Inter',sans-serif; }
[data-testid="stHeader"]{ background:transparent; }
[data-testid="stToolbar"]{ display:none; }
.block-container{ padding-top:1.4rem; padding-bottom:1rem; max-width:1340px; position:relative; z-index:1; }
h1,h2,h3,h4,h5,p,label,span,li,.stMarkdown{ color:var(--txt); }

/* ---------- aurora animated background ---------- */
.aurora{ position:fixed; inset:0; z-index:0; overflow:hidden; pointer-events:none; }
.aurora b{ position:absolute; border-radius:50%; filter:blur(95px); opacity:.45; animation:float 20s ease-in-out infinite; }
.aurora .b1{ width:520px;height:520px; left:-8%; top:-14%; background:var(--purple); }
.aurora .b2{ width:460px;height:460px; right:-6%; top:0%; background:var(--blue); animation-delay:-7s; }
.aurora .b3{ width:520px;height:520px; left:34%; bottom:-24%; background:var(--pink); animation-delay:-13s; }
@keyframes float{ 0%,100%{transform:translate(0,0) scale(1)} 33%{transform:translate(45px,32px) scale(1.08)} 66%{transform:translate(-32px,22px) scale(.94)} }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{ background:linear-gradient(180deg,rgba(14,23,43,.96),rgba(8,12,26,.97))!important;
  border-right:1px solid var(--bd); backdrop-filter:blur(16px); }
[data-testid="stSidebar"] *{ color:#C7CDE6; }
.sb-logo{ display:flex; align-items:center; gap:12px; padding:8px 4px 4px; }
.sb-logo .mark{ width:44px;height:44px; border-radius:13px; display:grid;place-items:center; font-size:1.45rem;
  background:linear-gradient(135deg,var(--purple),var(--pink)); box-shadow:0 8px 24px rgba(124,58,237,.5); }
.sb-logo .t1{ font-weight:800; font-size:1.2rem; line-height:1.05; color:#fff; }
.sb-logo .t1 b{ background:linear-gradient(90deg,var(--blue),var(--pink)); -webkit-background-clip:text;-webkit-text-fill-color:transparent; }
.sb-logo .t2{ color:var(--muted); font-size:.7rem; letter-spacing:.5px; }
.nav{ display:flex; flex-direction:column; gap:5px; margin:16px 0 6px; }
.nav a{ display:flex; align-items:center; gap:12px; padding:11px 14px; border-radius:13px; color:#C4CBE4!important;
  font-weight:600; font-size:.93rem; text-decoration:none; position:relative; transition:.2s; cursor:pointer; }
.nav a .ic{ font-size:1.02rem; width:20px; text-align:center; }
.nav a:hover{ background:rgba(255,255,255,.05); color:#fff!important; transform:translateX(2px); }
.nav a.active{ background:linear-gradient(90deg,rgba(124,58,237,.30),rgba(236,72,153,.10));
  color:#fff!important; box-shadow:0 6px 20px rgba(124,58,237,.22); }
.nav a.active::before{ content:""; position:absolute; left:0; top:18%; height:64%; width:4px; border-radius:4px;
  background:linear-gradient(var(--purple),var(--pink)); }
.plan{ margin:16px 2px 8px; padding:16px; border-radius:16px; border:1px solid var(--bd2);
  background:linear-gradient(160deg,rgba(124,58,237,.20),rgba(255,138,0,.07)); }
.plan .top{ display:flex; justify-content:space-between; align-items:center; }
.plan .top span{ color:var(--muted); font-size:.78rem; } .plan .crown{ font-size:1.05rem; }
.plan .lvl{ font-weight:800; font-size:1.1rem; margin:2px 0 1px;
  background:linear-gradient(90deg,var(--orange),var(--pink)); -webkit-background-clip:text;-webkit-text-fill-color:transparent; }
.plan .exp{ color:var(--muted); font-size:.74rem; }
.profile{ display:flex; align-items:center; gap:10px; margin:10px 2px 2px; padding:10px 12px; border-radius:14px;
  background:var(--card); border:1px solid var(--bd); }
.profile .av{ width:36px;height:36px;border-radius:11px; display:grid;place-items:center; font-weight:800; color:#fff;
  background:linear-gradient(135deg,var(--purple),var(--blue)); }
.profile .pn{ font-weight:700; font-size:.88rem; color:#fff; } .profile .pe{ color:var(--muted); font-size:.72rem; }

/* ---------- hero ---------- */
.hero{ display:flex; gap:20px; align-items:center; border-radius:22px; padding:30px 34px; margin:2px 0 20px;
  background:linear-gradient(120deg,rgba(124,58,237,.16),rgba(236,72,153,.10) 55%,rgba(255,138,0,.10));
  border:1px solid var(--bd2); backdrop-filter:blur(16px); box-shadow:0 24px 60px rgba(0,0,0,.45);
  position:relative; overflow:hidden; animation:rise .6s ease both; }
.hero-left{ flex:1; z-index:1; }
.hero h1{ font-size:2.6rem; font-weight:800; margin:0 0 6px; letter-spacing:-.5px; color:#fff; }
.hero h1 span{ background:linear-gradient(90deg,var(--pink),var(--orange)); -webkit-background-clip:text;-webkit-text-fill-color:transparent; }
.hero p{ font-size:1.05rem; color:#C4CBE4; margin:0 0 16px; }
.hero-badges{ display:flex; flex-wrap:wrap; gap:9px; }
.hb{ display:inline-flex; align-items:center; gap:6px; padding:8px 14px; border-radius:999px; font-size:.81rem; font-weight:600;
  background:rgba(255,255,255,.06); border:1px solid var(--bd2); color:#E6EAF8; backdrop-filter:blur(6px); transition:.2s; }
.hb:hover{ transform:translateY(-2px); border-color:rgba(236,72,153,.5); }
.hero-visual{ width:300px; height:170px; position:relative; z-index:1; flex-shrink:0; }
.hero-vid{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; border-radius:16px;
  border:1px solid var(--bd2); box-shadow:0 18px 46px rgba(56,189,248,.3); background:#000; }
.monitor{ position:absolute; inset:0; border-radius:16px; display:grid; place-items:center;
  background:linear-gradient(135deg,var(--purple),var(--pink) 58%,var(--orange)); box-shadow:0 20px 50px rgba(236,72,153,.4); }
.monitor::after{ content:"\\25B6"; color:#fff; font-size:2.2rem; margin-left:6px; text-shadow:0 4px 14px rgba(0,0,0,.35); }
.monitor::before{ content:""; position:absolute; width:280px;height:280px; border:1px solid rgba(255,255,255,.18);
  border-radius:50%; left:60%; top:50%; transform:translate(-50%,-50%) rotate(16deg); }

/* ---------- stat cards ---------- */
.stats{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin:0 0 6px; }
.stat{ display:flex; gap:13px; align-items:center; padding:18px; border-radius:18px; background:var(--card);
  border:1px solid var(--bd); backdrop-filter:blur(12px); transition:.22s; animation:rise .6s ease both; }
.stat:hover{ transform:translateY(-3px); border-color:var(--bd2); box-shadow:0 16px 40px rgba(0,0,0,.32); }
.stat-ic{ width:46px;height:46px;border-radius:13px; display:grid;place-items:center; font-size:1.3rem; flex-shrink:0; }
.si-purple{ background:linear-gradient(135deg,rgba(124,58,237,.4),rgba(124,58,237,.12)); }
.si-blue{ background:linear-gradient(135deg,rgba(56,189,248,.4),rgba(56,189,248,.12)); }
.si-orange{ background:linear-gradient(135deg,rgba(255,138,0,.4),rgba(255,138,0,.12)); }
.si-green{ background:linear-gradient(135deg,rgba(34,197,94,.4),rgba(34,197,94,.12)); }
.stat .lab{ color:var(--muted); font-size:.79rem; font-weight:600; }
.stat .num{ font-size:1.5rem; font-weight:800; color:#fff; line-height:1.15; }
.stat .sub{ font-size:.72rem; color:var(--green); font-weight:600; }
.stat .sub.on{ display:flex; align-items:center; gap:5px; }
.stat .sub.on::before{ content:""; width:7px;height:7px;border-radius:50%; background:var(--green); box-shadow:0 0 8px var(--green); }

/* ---------- panel titles ---------- */
.panel-title{ display:flex; align-items:center; gap:10px; font-size:1.16rem; font-weight:700; color:#fff; margin:14px 0 14px; }
.panel-title .pd{ width:8px;height:22px;border-radius:5px; background:linear-gradient(var(--purple),var(--pink)); }

/* ---------- uploaders as premium cards ---------- */
[data-testid="stFileUploader"]{ background:var(--card); border:1px solid var(--bd); border-radius:20px;
  padding:18px 18px 14px; transition:.24s; animation:rise .55s ease both; height:100%; }
[data-testid="stFileUploader"]:hover{ transform:translateY(-3px); border-color:rgba(124,58,237,.5);
  box-shadow:0 18px 44px rgba(124,58,237,.18); }
[data-testid="stFileUploader"] label p{ font-weight:700!important; color:#fff!important; font-size:.98rem!important; }
[data-testid="stFileUploaderDropzone"]{ background:rgba(255,255,255,.02)!important;
  border:1.5px dashed rgba(255,255,255,.16)!important; border-radius:15px!important; padding:14px 16px!important; transition:.2s; }
[data-testid="stFileUploaderDropzone"]:hover{ border-color:rgba(56,189,248,.55)!important; background:rgba(56,189,248,.05)!important; }
[data-testid="stFileUploaderDropzoneInstructions"] *{ color:var(--muted)!important; }
[data-testid="stFileUploader"] button{ background:linear-gradient(90deg,var(--purple),var(--pink))!important; color:#fff!important;
  border:none!important; border-radius:11px!important; font-weight:700!important; box-shadow:0 8px 22px rgba(124,58,237,.35)!important; transition:.18s!important; }
[data-testid="stFileUploader"] button:hover{ transform:scale(1.04); box-shadow:0 12px 28px rgba(236,72,153,.45)!important; }

/* ---------- text inputs ---------- */
[data-testid="stWidgetLabel"] label,[data-testid="stWidgetLabel"] p{ font-weight:600!important; color:#DCE1F5!important; font-size:.9rem!important; }
.stTextInput input,.stTextArea textarea{ background:rgba(255,255,255,.04)!important; border-radius:14px!important;
  border:1px solid var(--bd)!important; color:#fff!important; padding:.72rem .9rem!important; font-size:.95rem!important; transition:.2s; }
.stTextInput input:focus,.stTextArea textarea:focus{ border-color:var(--purple)!important;
  box-shadow:0 0 0 3px rgba(124,58,237,.28)!important; }
[data-baseweb="input"],[data-baseweb="base-input"]{ background:transparent!important; border-radius:14px!important; }

/* ---------- premium dropdowns (selectbox + its menu) ---------- */
[data-baseweb="select"] > div{ background:rgba(255,255,255,.04)!important; border:1.5px solid rgba(124,58,237,.45)!important;
  border-radius:15px!important; min-height:52px; transition:.2s; }
[data-baseweb="select"] > div:hover{ border-color:rgba(236,72,153,.6)!important; box-shadow:0 6px 20px rgba(124,58,237,.2)!important; }
[data-baseweb="select"] > div:focus-within{ border-color:var(--purple)!important; box-shadow:0 0 0 3px rgba(124,58,237,.28)!important; }
[data-baseweb="select"] input,[data-baseweb="select"] div[title]{ color:#fff!important; font-weight:700; font-size:.96rem; }
[data-baseweb="select"] svg{ fill:var(--pink)!important; }
/* the open menu = floating glass card with a coloured edge */
[data-baseweb="popover"] ul[role="listbox"]{ background:linear-gradient(180deg,#131d38,#0b1122)!important;
  border:1px solid rgba(124,58,237,.4)!important; border-radius:20px!important; padding:8px!important;
  box-shadow:0 30px 72px rgba(0,0,0,.62), 0 0 22px rgba(124,58,237,.25)!important; }
[data-baseweb="popover"] li[role="option"]{ border-radius:13px!important; margin:3px 5px!important; padding:13px 15px!important;
  color:#E9EDFB!important; font-weight:600; font-size:.96rem; transition:.16s; }
[data-baseweb="popover"] li[role="option"]:hover{ background:rgba(124,58,237,.26)!important; transform:translateX(3px); }
/* selected / keyboard-highlighted row -> vibrant full gradient (like the mock) */
[data-baseweb="popover"] li[role="option"][aria-selected="true"]{
  background:linear-gradient(90deg,var(--blue),var(--purple) 55%,var(--pink))!important; color:#fff!important; font-weight:700;
  box-shadow:0 8px 22px rgba(124,58,237,.45)!important; }
[data-baseweb="popover"] ul[role="listbox"]::-webkit-scrollbar{ width:8px; }
[data-baseweb="popover"] ul[role="listbox"]::-webkit-scrollbar-thumb{ background:linear-gradient(var(--pink),var(--purple)); border-radius:8px; }
[data-baseweb="popover"] ul[role="listbox"]::-webkit-scrollbar-track{ background:transparent; }

/* ---------- info card ---------- */
.infocard{ background:linear-gradient(120deg,rgba(56,189,248,.12),rgba(124,58,237,.10)); border:1px solid var(--bd2);
  border-radius:16px; padding:14px 16px; margin-top:14px; font-size:.85rem; color:#C9D3F0; line-height:1.65; }
.infocard b{ color:#fff; }

/* ---------- buttons ---------- */
.stButton>button,.stDownloadButton>button{ background:linear-gradient(90deg,var(--purple),var(--pink) 52%,var(--orange))!important;
  background-size:180% auto!important; color:#fff!important; border:none!important; border-radius:16px!important; font-weight:700!important;
  box-shadow:0 14px 38px rgba(236,72,153,.35)!important; transition:transform .18s,box-shadow .18s,background-position .5s!important; }
.stButton>button{ height:60px; font-size:1.1rem!important; letter-spacing:.3px; margin-top:8px; }
.stButton>button:hover,.stDownloadButton>button:hover{ transform:scale(1.02); background-position:right center!important;
  box-shadow:0 20px 50px rgba(255,138,0,.45)!important; }

/* ---------- success / logs / video / alerts ---------- */
.okcard{ background:linear-gradient(90deg,rgba(34,197,94,.16),rgba(56,189,248,.12)); border:1px solid var(--bd2);
  border-radius:16px; padding:14px 18px; margin:10px 0; font-size:1.02rem; animation:rise .5s ease both; }
[data-testid="stCode"],pre{ background:#080b1a!important; border:1px solid var(--bd)!important; border-radius:14px!important; }
[data-testid="stCode"] code,pre,code{ color:#54f5a0!important; font-family:'JetBrains Mono',monospace!important; font-size:.85rem!important; }
[data-testid="stVideo"] video{ border-radius:18px; border:1px solid var(--bd2); box-shadow:0 22px 55px rgba(0,0,0,.55); }
[data-testid="stNotification"],.stAlert{ border-radius:14px!important; }
.stProgress>div>div>div{ background:linear-gradient(90deg,var(--purple),var(--blue))!important; }

/* ---------- footer ---------- */
.footer{ text-align:center; color:var(--muted); font-size:.82rem; margin:34px 0 6px; padding-top:18px; border-top:1px solid var(--bd); }
.footer a{ color:var(--blue); text-decoration:none; margin:0 9px; } .footer a:hover{ color:var(--pink); }
.footer .sep{ opacity:.35; }

/* ---------- scrollbar ---------- */
::-webkit-scrollbar{ width:10px; height:10px; }
::-webkit-scrollbar-thumb{ background:linear-gradient(var(--purple),var(--blue)); border-radius:10px; }
::-webkit-scrollbar-track{ background:transparent; }

@keyframes rise{ from{ opacity:0; transform:translateY(16px); } to{ opacity:1; transform:none; } }

@media(max-width:1100px){ .stats{ grid-template-columns:repeat(2,1fr); } .hero-visual{ display:none; } }
</style>
"""


def _clean_tmp():
    """Remove leftover render temp dirs older than 1h — /tmp is a small tmpfs and must not fill up."""
    import glob, time
    now = time.time()
    for d in glob.glob("/tmp/news_*") + glob.glob("/tmp/newsui_*"):
        try:
            if os.path.isdir(d) and now - os.path.getmtime(d) > 3600:
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


def _shorts_panel(D):
    """UI: any-format video in -> YouTube-Shorts-ready vertical video out."""
    st.caption("Koi bhi format ka video daalo (mp4/mov/mkv/avi/webm…) → **YouTube Shorts ready** "
               "vertical video (9:16 · 1080×1920 · max 60s) ban ke mil jaayega.")
    up = st.file_uploader("🎬 Video (any format)", key="sh_up",
                          type=["mp4", "mov", "webm", "mkv", "avi", "m4v", "mpeg", "mpg", "flv", "wmv", "3gp", "ts"])
    c1, c2, c3 = st.columns(3, gap="large")
    with c1:
        length = st.slider("⏱️ Short length (sec)", 5, SHORT_MAX, SHORT_MAX, 1, key="sh_len",
                           help="YouTube Shorts ki limit 60 sec hai.")
    with c2:
        start = st.number_input("▶️ Start from (sec)", 0.0, 36000.0, 0.0, 1.0, key="sh_start",
                                help="Lambe video me se kahan se kaatna hai.")
    with c3:
        fill = st.radio("🎨 Look", ["Full screen (normal Short)", "Blurred bg (poora video, chhota)"],
                        key="sh_fill",
                        help="Full screen = asli Shorts jaisा, video poori screen bhar deta hai (side thode cut). "
                             "Blurred bg = kuch cut nahi hota par video chhota dikhta hai aur upar-neeche blur aata hai.")
    if up:
        p = os.path.join(D, "short_src" + os.path.splitext(up.name)[1])
        with open(p, "wb") as w:
            w.write(up.getbuffer())
        st.caption(f"Source = {_dur(p):.0f}s → Short = {length}s vertical.")
    if st.button("📱 Make Shorts video", type="primary", use_container_width=True, key="sh_go"):
        if not up:
            st.error("Pehle video daalo."); return
        src = os.path.join(D, "short_src" + os.path.splitext(up.name)[1])
        out = os.path.join(D, "youtube_short.mp4")
        box = st.empty(); logs = []
        def prog(m): logs.append(str(m)); box.code("\n".join(logs[-8:]))
        try:
            with st.spinner("Shorts ban raha hai…"):
                make_short(src, out, start=start, length=length,
                           fill=("blur" if fill.startswith("Blurred") else "crop"), progress=prog)
            st.success("✅ YouTube Shorts ready — seedha upload kar do!")
            st.video(out)
            with open(out, "rb") as f:
                st.download_button("⬇️ Download Short", f, "youtube_short.mp4", "video/mp4",
                                   use_container_width=True, key="sh_dl")
        except Exception as e:
            st.error("Shorts error: " + str(e))


def main():
    _clean_tmp()
    st.set_page_config(page_title="LocalAI TV Studio", page_icon="📺", layout="wide",
                       initial_sidebar_state="expanded")
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown("<div class='aurora'><b class='b1'></b><b class='b2'></b><b class='b3'></b></div>", unsafe_allow_html=True)

    # ---- sidebar ----
    with st.sidebar:
        st.markdown("""
        <div class='sb-logo'>
          <div class='mark'>📺</div>
          <div><div class='t1'>LocalAI <b>TV</b></div><div class='t2'>AI News Studio</div></div>
        </div>
        <div class='nav'>
          <a class='active'><span class='ic'>🏠</span> Dashboard</a>
          <a><span class='ic'>🎬</span> News Generator</a>
          <a><span class='ic'>📂</span> History</a>
          <a><span class='ic'>🎙️</span> Voices</a>
          <a><span class='ic'>📺</span> Branding</a>
          <a><span class='ic'>⚙️</span> Settings</a>
          <a><span class='ic'>📊</span> Analytics</a>
          <a><span class='ic'>💳</span> Billing</a>
          <a><span class='ic'>❓</span> Help &amp; Docs</a>
        </div>
        <div class='plan'>
          <div class='top'><span>Your Plan</span><span class='crown'>👑</span></div>
          <div class='lvl'>Professional</div>
          <div class='exp'>Chrome-crisp Telugu · v2.0</div>
        </div>
        <div class='profile'>
          <div class='av'>L</div>
          <div><div class='pn'>LocalAI TV Team</div><div class='pe'>admin@localai.tv</div></div>
        </div>
        """, unsafe_allow_html=True)
        with st.expander("🩺 System info"):
            import platform as _pf
            _info = {"python": _pf.python_version(), "platform": _pf.platform(), "ffmpeg": FF}
            try:
                _osr = _pf.freedesktop_os_release()
                _info["distro"] = f"{_osr.get('ID', '?')} {_osr.get('VERSION_ID', '?')} ({_osr.get('VERSION_CODENAME', '?')})"
            except Exception:
                _info["distro"] = "n/a (Windows/local)"
            _chr = next((x for x in ("/usr/bin/chromium", "/usr/bin/chromium-browser",
                                     "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable")
                         if os.path.isfile(x)), None)
            _info["chromium"] = _chr or ("bundled/Playwright (local)" if os.name == "nt" else "NOT installed yet — still building")
            _info["chrome_ready"] = "✅ YES — Telugu will render via Chrome" if (_chr or os.name == "nt") \
                else "⏳ not yet (still on old build or building)"
            st.json(_info)

    # ---- hero ----
    _hp = os.path.join(APP_DIR, "assets", "hero.mp4")
    if os.path.isfile(_hp):
        import base64
        _b64 = base64.b64encode(open(_hp, "rb").read()).decode()
        _hero_visual = ("<video class='hero-vid' autoplay loop muted playsinline "
                        "src='data:video/mp4;base64,%s'></video>" % _b64)
    else:
        _hero_visual = "<div class='monitor'></div>"
    st.markdown(f"""
    <div class='hero'>
      <div class='hero-left'>
        <h1>LocalAI TV <span>Studio</span></h1>
        <p>Create Professional AI Powered Telugu Broadcast Videos</p>
        <div class='hero-badges'>
          <span class='hb'>✨ AI Powered</span>
          <span class='hb'>🎬 Auto Sections</span>
          <span class='hb'>📺 Live Broadcast</span>
          <span class='hb'>🎙️ Gemini Voice</span>
          <span class='hb'>⚡ Fast Rendering</span>
        </div>
      </div>
      <div class='hero-visual'>{_hero_visual}</div>
    </div>
    <div class='stats'>
      <div class='stat'><div class='stat-ic si-purple'>🎬</div>
        <div><div class='lab'>Output Quality</div><div class='num'>720p</div><div class='sub'>~2x faster render</div></div></div>
      <div class='stat'><div class='stat-ic si-blue'>⚡</div>
        <div><div class='lab'>Render Preset</div><div class='num'>veryfast</div><div class='sub'>optimized pipeline</div></div></div>
      <div class='stat'><div class='stat-ic si-orange'>🔤</div>
        <div><div class='lab'>Telugu Engine</div><div class='num'>Chrome</div><div class='sub'>crisp shaping</div></div></div>
      <div class='stat'><div class='stat-ic si-green'>🟢</div>
        <div><div class='lab'>Server Status</div><div class='num'>ONLINE</div><div class='sub on'>all systems operational</div></div></div>
    </div>
    """, unsafe_allow_html=True)

    if "nd" not in st.session_state: st.session_state.nd = tempfile.mkdtemp(prefix="newsui_")
    D = st.session_state.nd

    with st.expander("📱  YouTube Shorts Maker — koi bhi video → Shorts ready (9:16 · 60s)", expanded=False):
        _shorts_panel(D)

    with st.expander("🔗  App Link Maker — filler shuru me + app download card end me", expanded=False):
        _brand_panel(D)

    left, right = st.columns([1.55, 1], gap="large")
    with left:
        st.markdown("<div class='panel-title'><span class='pd'></span>📤 Upload Content</div>", unsafe_allow_html=True)
        u1, u2 = st.columns(2, gap="large")
        with u1:
            main_ups = st.file_uploader("🎬 Main Video (Sections)  \n:gray[One long video or separate clips · required]",
                                        type=["mp4", "mov", "webm"], accept_multiple_files=True)
        with u2:
            intro_up = st.file_uploader("🎥 Intro Clip (8–9s)  \n:gray[Optional · plays before each section]",
                                        type=["mp4", "mov", "webm"])
            _intros = _list_media("intros", VID_EXTS)
            intro_pick = st.selectbox("🎬 …or pick a saved intro", ["— none —"] + list(_intros.keys()),
                                      help="Bundled intros by category. An uploaded file above overrides this.") if _intros else None
            if intro_pick and intro_pick in _intros:
                st.caption("✅ Preview — verify this is the right one:")
                st.video(open(_intros[intro_pick], "rb").read())
        u3, u4 = st.columns(2, gap="large")
        with u3:
            logo_up = st.file_uploader("🖼️ Logo / Watermark  \n:gray[Optional · PNG, JPG, WEBP or GIF]",
                                       type=["png", "jpg", "jpeg", "webp", "mp4", "mov", "webm", "gif"])
            _logos = _list_media("logos", LOGO_EXTS, "🖼️")
            logo_pick = st.selectbox("🖼️ …or pick a saved logo", ["— none —"] + list(_logos.keys()),
                                     help="Bundled logos. An uploaded file above overrides this.") if _logos else None
            if logo_pick and logo_pick in _logos:
                st.caption("✅ Preview — verify this is the right one:")
                _lp = _logos[logo_pick]
                if _lp.lower().endswith((".mp4", ".mov", ".webm")):
                    st.video(open(_lp, "rb").read())
                else:
                    st.image(_lp, use_container_width=True)
        with u4:
            pillar_up = st.file_uploader("🎞️ Filler / Pillar Clip  \n:gray[Optional · ~2s, plays before each section]",
                                         type=["mp4", "mov", "webm"])
            _fillers = _list_media("fillers", VID_EXTS, "📢")
            pillar_pick = st.selectbox("🎞️ …or pick a saved filler", ["— none —"] + list(_fillers.keys()),
                                       help="Bundled fillers. An uploaded file above overrides this.") if _fillers else None
            if pillar_pick and pillar_pick in _fillers:
                st.caption("✅ Preview — verify this is the right one:")
                st.video(open(_fillers[pillar_pick], "rb").read())
    with right:
        st.markdown("<div class='panel-title'><span class='pd'></span>⚙️ Settings</div>", unsafe_allow_html=True)
        red_text = st.text_input("🟥 Red Strip Text (Telugu, bottom-left)", "సిద్దిపేట జిల్లా వార్తలు")
        bottom_text = st.text_input("📰 Scrolling Ticker Text (Telugu, NON-STOP)",
                                    "మున్సిపల్ పరిధిలో తాగునీటి సరఫరా మెరుగుదలకు ప్రత్యేక చర్యలు")
        split_raw = st.text_input("⏱️ Section Start Times — EMPTY = auto-detect",
                                  "", help="Leave empty and the tool auto-detects the big number cards (1–5) and inserts a filler before each. Only fill this in if auto-detect misses or gets a section wrong.")
        st.markdown("<div class='infocard'>ℹ️ <b>Empty = auto-detect</b> · clean filler · slanted red strip · "
                    "non-stop ticker · NotebookLM endcard auto-removed</div>", unsafe_allow_html=True)
    section_titles = []
    split_times = _parse_times(split_raw)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    if st.button("✨  Generate News Video", type="primary", use_container_width=True):
        if not main_ups:
            st.error("⚠️ Please upload the main content video."); return
        def save(up, name):
            if not up: return None
            p = os.path.join(D, name + os.path.splitext(up.name)[1])
            open(p, "wb").write(up.getbuffer()); return p
        clips = [save(u, f"main{i}") for i, u in enumerate(main_ups)]
        intro = save(intro_up, "intro"); logo = save(logo_up, "logo"); pillar = save(pillar_up, "pillar")
        if not intro and intro_pick and intro_pick in _intros:      # no upload -> use the chosen saved intro
            intro = _intros[intro_pick]
        if not logo and logo_pick and logo_pick in _logos:
            logo = _logos[logo_pick]
        if not pillar and pillar_pick and pillar_pick in _fillers:
            pillar = _fillers[pillar_pick]
        if len(clips) == 1 and split_times:
            st.info(f"The video will be cut into {len(split_times)+1} sections, with a filler before each.")
        out = os.path.join(D, "news_out.mp4"); box = st.empty(); logs = []
        def prog(m): logs.append(str(m)); box.code("\n".join(logs[-14:]))
        try:
            with st.spinner("🎬 Rendering (cut + fillers + Chrome strip + continuous overlay)…"):
                render(clips, intro, logo, red_text, bottom_text, section_titles, out,
                       pillar_clip=pillar, split_times=split_times, progress=prog)
            st.markdown("<div class='okcard'>✅ <b>Video ready!</b> — preview &amp; download below</div>", unsafe_allow_html=True)
            st.video(out)
            with open(out, "rb") as vf:
                st.download_button("⬇️  Download News Video", vf, "news_video.mp4", "video/mp4", use_container_width=True)
        except Exception as e:
            st.error("Render error: " + repr(e)); st.exception(e)

    st.markdown("""<div class='footer'>
      Powered by <b style='color:#EAECF5'>LocalAI TV</b> <span class='sep'>·</span> v2.0
      <span class='sep'>·</span> <a>GitHub</a> <span class='sep'>·</span> <a>Documentation</a>
    </div>""", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
