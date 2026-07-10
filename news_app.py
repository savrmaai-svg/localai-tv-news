# Telugu News Video Template — standalone Streamlit tool (Plan C, LocalAITV).
# Upload karo -> tool JOINS + overlays a reference-style news template:
#   intro clip -> [2s pillar/filler -> section clip] x N   (ek continuous broadcast)
#   with logo top-right + red strip + a SEAMLESS bottom scrolling Telugu ticker that runs
#   NON-STOP across the WHOLE video. Output 1920x1080. Telugu via ffmpeg/libass (Nirmala UI).
import os, subprocess, tempfile, shutil
import streamlit as st

W, H, FPS = 1920, 1080, 25
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
NIRMALA = r"C:\Windows\Fonts\Nirmala.ttf"
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
NOTO_TTF = os.path.join(FONTS_DIR, "NotoSansTelugu-Bold.ttf")
# Noto Sans Telugu shapes Telugu correctly; Nirmala-Bold dropped 'ా' vowel signs, Ramabhadra broke conjuncts
HEAD_FONT = "Noto Sans Telugu" if os.path.isfile(NOTO_TTF) else "Nirmala UI"
# measured template geometry (from the reference khammam_20.mp4)
RED = "0xB92F23"; BLUE = "0x06215B"
STRIP_Y, STRIP_H = 994, 86        # raised so the strip covers NotebookLM's bottom-right watermark
RED_W = 543
LOGO_X, LOGO_Y, LOGO_W = 1560, 34, 330


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

SLANT = 46                                            # red parallelogram slant (px) — matches reference
TICK_X = RED_W + SLANT + 8                             # ticker starts just past the slanted red edge
TICK_SIZE = 56                                         # ticker font size
TICK_SPEED = 150                                       # ticker scroll px/sec

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
            "-r", str(FPS), "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
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
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
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

def _detect_sections(src, step=0.6):
    """Auto-find the NotebookLM 'big number' section cards (1..5). Each such card = a huge white
    number with a thick black outline on a full-bleed COLOURED background. Robust signature:
      left strip is coloured (not white), overall bg coloured, and the number's outline spans most
      of the frame height (works even when an illustration partly covers the digit).
    Returns the section START times (s). Empty list if cv2 missing or nothing found."""
    try:
        import cv2, numpy as np
    except Exception:
        return []
    def is_card(fr):
        h, w, _ = fr.shape
        lb = fr[int(.08 * h):int(.94 * h), int(.015 * w):int(.26 * w)]
        g = cv2.cvtColor(lb, cv2.COLOR_BGR2GRAY); s = cv2.cvtColor(lb, cv2.COLOR_BGR2HSV)[:, :, 1]
        Wm = ((g >= 195) & (s <= 80)).astype(np.uint8); Bm = (g <= 85).astype(np.uint8)
        outline = cv2.dilate(Wm, np.ones((9, 9), np.uint8)) & Bm       # black hugging white = digit outline
        rowspan = (outline.sum(1) > 2).mean(); colspan = (outline.sum(0) > 2).mean()
        ledge = (fr[:, :int(.05 * w)] >= 232).all(axis=2).mean()
        white = (fr >= 232).all(axis=2).mean()
        return (ledge < 0.28) and (0.12 < white < 0.60) and (rowspan >= 0.58) and (colspan >= 0.50)
    cap = cv2.VideoCapture(src); fps = cap.get(cv2.CAP_PROP_FPS) or 25
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    hits, t = [], 8.0
    while t < dur - 3:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, fr = cap.read()
        if ok and is_card(fr):
            hits.append(t)
        t += step
    cap.release()
    ev = []
    for hh in hits:
        if ev and hh - ev[-1][-1] <= 2.5:
            ev[-1].append(hh)
        else:
            ev.append([hh])
    return [round(max(0.0, c[0] - 0.6), 1) for c in ev if len(c) >= 4]   # ~0.6s before the card is fully in

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
                        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", seg], check=True)
        segs.append(seg)
    return segs

def _concat(paths, out):
    lst = out + ".txt"
    open(lst, "w").write("\n".join(f"file '{p.replace(chr(92), '/')}'" for p in paths))
    subprocess.run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", out], check=True)
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
                    "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2"] + extra + [content],
                   check=True, cwd=D)

    # 4) intro (clean channel branding) + content
    parts = []
    if intro:
        log("normalizing intro…"); intro_n = os.path.join(D, "intro_n.mp4"); _normalize(intro, intro_n); parts.append(intro_n)
    parts.append(content)
    log("final join…")
    final = _concat(parts, os.path.join(D, "joined.mp4"))
    subprocess.run([FF, "-y", "-v", "error", "-i", final, "-c", "copy", "-movflags", "+faststart", out_path], check=True)
    log(f"DONE → {out_path}")
    return out_path


# ---------------- Streamlit UI ----------------
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&family=JetBrains+Mono&display=swap');
:root{ --card:rgba(255,255,255,.06); --bd:rgba(255,255,255,.09); }
.stApp{
  background:
    radial-gradient(1100px 560px at 12% -12%, rgba(108,99,255,.24), transparent 60%),
    radial-gradient(1000px 520px at 105% -5%, rgba(0,212,255,.16), transparent 55%),
    radial-gradient(900px 720px at 55% 125%, rgba(255,75,92,.16), transparent 60%),
    #050816;
  background-attachment:fixed;
}
html,body,[class*="css"]{ font-family:'Poppins',sans-serif; }
[data-testid="stHeader"]{ background:transparent; }
.block-container{ padding-top:1.1rem; max-width:1260px; }
h1,h2,h3,h4,h5,p,label,span,li,.stMarkdown{ color:#EAECF5; }

/* hero */
.hero{ border-radius:24px; padding:32px 38px; margin:2px 0 22px; background:var(--card);
  border:1px solid var(--bd); backdrop-filter:blur(14px); box-shadow:0 22px 60px rgba(0,0,0,.5);
  position:relative; overflow:hidden; animation:fade .7s ease both; }
.hero::before{ content:""; position:absolute; inset:-45%;
  background:conic-gradient(from 0deg,#FF4B5C,#FF7A18,#6C63FF,#00D4FF,#FF4B5C);
  filter:blur(72px); opacity:.26; animation:spin 14s linear infinite; z-index:0; }
.hero>*{ position:relative; z-index:1; }
.hero h1{ font-size:2.4rem; font-weight:800; margin:0; letter-spacing:.2px;
  background:linear-gradient(90deg,#FF4B5C,#FF7A18 38%,#6C63FF 72%,#00D4FF);
  -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; }
.hero p{ font-size:1.02rem; color:#AEB4CF; margin:.55rem 0 .7rem; }
.badge{ display:inline-block; margin:6px 6px 0 0; padding:6px 13px; border-radius:999px;
  background:rgba(255,255,255,.07); border:1px solid var(--bd); font-size:.78rem; color:#D8E6FF; }

/* section header */
.sec{ font-weight:700; font-size:1.08rem; margin:2px 0 12px; display:flex; align-items:center; gap:10px; color:#fff; }
.sec .dot{ width:9px; height:24px; border-radius:6px; background:linear-gradient(#FF4B5C,#FF7A18); }

/* uploaders as glass cards */
[data-testid="stFileUploader"]{ animation:fade .6s ease both; }
[data-testid="stFileUploaderDropzone"]{ background:var(--card)!important;
  border:1.5px dashed rgba(255,255,255,.16)!important; border-radius:18px!important; padding:16px 18px!important; transition:.25s; }
[data-testid="stFileUploaderDropzone"]:hover{ border-color:rgba(0,212,255,.55)!important;
  transform:translateY(-2px); box-shadow:0 14px 34px rgba(0,212,255,.14); }
[data-testid="stWidgetLabel"] label,[data-testid="stWidgetLabel"] p{ font-weight:600!important; color:#E4E8FA!important; }

/* text inputs */
.stTextInput input,.stTextArea textarea{ background:rgba(255,255,255,.05)!important; border-radius:14px!important;
  border:1px solid var(--bd)!important; color:#fff!important; padding:.6rem .8rem!important; }
.stTextInput input:focus,.stTextArea textarea:focus{ border-color:#6C63FF!important;
  box-shadow:0 0 0 3px rgba(108,99,255,.25)!important; }
[data-baseweb="input"]{ background:transparent!important; border-radius:14px!important; }

/* buttons */
.stButton>button,.stDownloadButton>button{ background:linear-gradient(90deg,#FF4B5C,#FF7A18)!important;
  color:#fff!important; border:none!important; border-radius:16px!important; font-weight:700!important;
  box-shadow:0 12px 32px rgba(255,75,92,.35)!important; transition:transform .18s, box-shadow .18s!important; }
.stButton>button{ height:62px; font-size:1.06rem!important; letter-spacing:.3px; }
.stButton>button:hover,.stDownloadButton>button:hover{ transform:scale(1.02);
  box-shadow:0 18px 44px rgba(255,122,24,.5)!important; }

/* success card */
.okcard{ background:linear-gradient(90deg,rgba(0,212,255,.14),rgba(108,99,255,.14)); border:1px solid var(--bd);
  border-radius:16px; padding:14px 18px; margin:8px 0; font-size:1.02rem; animation:fade .5s ease both; }

/* logs / code terminal */
[data-testid="stCode"],pre{ background:#080b1a!important; border:1px solid var(--bd)!important; border-radius:14px!important; }
[data-testid="stCode"] code,pre,code{ color:#54f5a0!important; font-family:'JetBrains Mono',monospace!important; font-size:.86rem!important; }

/* video + alerts */
[data-testid="stVideo"] video{ border-radius:18px; border:1px solid var(--bd); box-shadow:0 22px 55px rgba(0,0,0,.55); }
[data-testid="stNotification"],.stAlert{ border-radius:14px!important; }

/* sidebar */
[data-testid="stSidebar"]{ background:rgba(9,12,26,.9)!important; border-right:1px solid var(--bd); backdrop-filter:blur(12px); }
[data-testid="stSidebar"] *{ color:#D6DAEE; }

/* progress + spinner */
.stProgress>div>div>div{ background:linear-gradient(90deg,#6C63FF,#00D4FF)!important; }

/* scrollbar */
::-webkit-scrollbar{ width:10px; height:10px; }
::-webkit-scrollbar-thumb{ background:linear-gradient(#6C63FF,#00D4FF); border-radius:10px; }
::-webkit-scrollbar-track{ background:transparent; }

@keyframes spin{ to{ transform:rotate(360deg); } }
@keyframes fade{ from{ opacity:0; transform:translateY(14px); } to{ opacity:1; transform:none; } }
</style>
"""


def main():
    st.set_page_config(page_title="LocalAI TV — Telugu News Generator", page_icon="📺", layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)

    # ---- sidebar ----
    with st.sidebar:
        st.markdown("""<div style='text-align:center;padding:10px 0 6px'>
            <div style='font-size:2.6rem;line-height:1'>📺</div>
            <div style='font-weight:800;font-size:1.2rem;background:linear-gradient(90deg,#FF4B5C,#00D4FF);
                 -webkit-background-clip:text;-webkit-text-fill-color:transparent'>LocalAI TV</div>
            <div style='color:#8b90ad;font-size:.78rem;letter-spacing:.5px'>TELUGU NEWS STUDIO</div></div>""",
                    unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("#### ⚙️ About")
        st.markdown("<span style='color:#AEB4CF;font-size:.88rem'>AI-powered Telugu news video generator — "
                    "turns a NotebookLM clip into a broadcast-style news video.</span>", unsafe_allow_html=True)
        st.markdown("#### 💡 Tips")
        st.markdown("<span style='color:#AEB4CF;font-size:.86rem'>• Leave section times <b>empty</b> → auto-detect<br>"
                    "• Logo can be a PNG or video/GIF<br>• Filler plays before each section<br>"
                    "• Ticker: crisp Telugu via Chrome</span>", unsafe_allow_html=True)
        st.markdown("---")
        st.caption("🟢 v2.0 · Chrome-rendered ticker")
        st.caption("🔗 GitHub  ·  ❓ Help  ·  📄 Docs")

    # ---- hero ----
    st.markdown("""<div class='hero'>
        <h1>📺 LocalAI TV — Telugu News Generator</h1>
        <p>Create professional Telugu news videos within seconds using AI.</p>
        <span class='badge'>✨ Auto sections</span> <span class='badge'>📰 Non-stop ticker</span>
        <span class='badge'>🔤 Chrome-crisp Telugu</span> <span class='badge'>🧹 Endcard auto-remove</span>
    </div>""", unsafe_allow_html=True)

    if "nd" not in st.session_state: st.session_state.nd = tempfile.mkdtemp(prefix="newsui_")
    D = st.session_state.nd

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("<div class='sec'><span class='dot'></span>📤 Uploads</div>", unsafe_allow_html=True)
        main_ups = st.file_uploader("🎬 Main video (sections) — one long video OR a separate clip per section — required",
                                    type=["mp4", "mov", "webm"], accept_multiple_files=True)
        intro_up = st.file_uploader("🎥 Intro clip (8–9s) — optional", type=["mp4", "mov", "webm"])
        logo_up = st.file_uploader("📛 Logo (top-right — PNG or animated VIDEO/GIF) — optional",
                                   type=["png", "jpg", "jpeg", "webp", "mp4", "mov", "webm", "gif"])
        pillar_up = st.file_uploader("🎞️ Filler / pillar clip (~2s, plays BEFORE each section) — optional", type=["mp4", "mov", "webm"])
    with c2:
        st.markdown("<div class='sec'><span class='dot'></span>⚙️ Settings</div>", unsafe_allow_html=True)
        red_text = st.text_input("🟥 Red strip text (Telugu, bottom-left)", "సిద్దిపేట జిల్లా వార్తలు")
        bottom_text = st.text_input("📰 Scrolling ticker text (Telugu, NON-STOP)",
                                    "మున్సిపల్ పరిధిలో తాగునీటి సరఫరా మెరుగుదలకు ప్రత్యేక చర్యలు")
        split_raw = st.text_input("⏱️ Section start times — EMPTY = auto-detect (or e.g. 0:49, 2:50, 4:28)",
                                  "", help="Leave empty and the tool auto-detects the big number cards (1–5) and inserts a filler before each. Only fill this in if auto-detect misses or gets a section wrong.")
        st.caption("ℹ️ Empty = auto-detect · clean filler · slanted red strip · non-stop ticker · NotebookLM endcard auto-removed")
    section_titles = []
    split_times = _parse_times(split_raw)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    if st.button("🚀 Generate News Video", type="primary", use_container_width=True):
        if not main_ups:
            st.error("⚠️ Please upload the main content video."); return
        def save(up, name):
            if not up: return None
            p = os.path.join(D, name + os.path.splitext(up.name)[1])
            open(p, "wb").write(up.getbuffer()); return p
        clips = [save(u, f"main{i}") for i, u in enumerate(main_ups)]
        intro = save(intro_up, "intro"); logo = save(logo_up, "logo"); pillar = save(pillar_up, "pillar")
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


if __name__ == "__main__":
    main()
