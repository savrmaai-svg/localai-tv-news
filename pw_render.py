# -*- coding: utf-8 -*-
# Render the news bottom-strip pieces with Chrome (Playwright) for best Telugu shaping:
#   - the slanted RED parallelogram + white label  -> transparent PNG (label.png)
#   - the scrolling navy ticker text (wide, tiled)  -> navy PNG (ticker.png) + cycle width
# The video then scrolls ticker.png with an ffmpeg moving crop (smooth, no per-frame reshaping).
import base64, os

_S = 720 / 1080.0                 # 720p scale — MUST match news_app.py's _S (keep in sync)
W = round(1920 * _S)
STRIP_H = round(86 * _S)
RED_W = round(543 * _S)
SLANT = round(46 * _S)
LABEL_W = RED_W + SLANT
RED = "#B92F23"
NAVY = "#06215B"
STROKE = "#301A0A"
LABEL_SIZE = round(44 * _S)
TICK_SIZE = round(56 * _S)
LABEL_PAD = round(30 * _S)        # label left padding (scaled)
LABEL_FIT = RED_W - round(44 * _S)  # auto-fit max text width (scaled)
LABEL_MIN = round(22 * _S)        # min font size when shrinking (scaled)
TICK_GAP = " " * 6      # wide gap between scrolling phrases (em-spaces, no bullet — matches reference)
FONT_TTF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "NotoSansTelugu-Bold.ttf")


def _font_face():
    b64 = base64.b64encode(open(FONT_TTF, "rb").read()).decode()
    return (f"@font-face{{font-family:'NotoTel';src:url(data:font/ttf;base64,{b64}) format('truetype');"
            f"font-weight:bold;}}")


def _launch_browser(p):
    """Launch Chromium. Prefer a SYSTEM chromium (Linux: Debian's `chromium` pkg -> /usr/bin/chromium,
    deps guaranteed); fall back to Playwright's bundled browser (local/Windows). Default flags are the
    ROBUST set (stable on a normal VPS/PC). Set env LOWMEM_CHROME=1 on tiny ~1GB hosts (e.g. free
    Streamlit) to collapse Chromium into one lean process (~half the RAM) at a small stability cost."""
    safe = ["--no-sandbox", "--disable-dev-shm-usage"]
    args = safe + ["--disable-gpu", "--disable-software-rasterizer", "--mute-audio", "--no-first-run"]
    if os.environ.get("LOWMEM_CHROME"):          # opt-in for tiny ~1GB hosts (e.g. free Streamlit)
        args = args + ["--single-process", "--no-zygote", "--disable-extensions",
                       "--disable-background-networking", "--disable-breakpad",
                       "--js-flags=--max-old-space-size=128"]
    for exe in ("/usr/bin/chromium", "/usr/bin/chromium-browser",
                "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"):
        if os.path.isfile(exe):
            try:
                return p.chromium.launch(executable_path=exe, args=args)
            except Exception:
                return p.chromium.launch(executable_path=exe, args=safe)
    return p.chromium.launch(args=safe)


def render_strip(ticker_text, label_text, D, repeats=8):
    """Render label.png (transparent parallelogram+label) and ticker2x.png (navy scrolling text).
    Returns (label_png, ticker_png, cycle_width_px)."""
    from playwright.sync_api import sync_playwright
    ff = _font_face()
    label_png = os.path.join(D, "pw_label.png")
    ticker_png = os.path.join(D, "pw_ticker.png")
    unit = _esc(ticker_text or "") + TICK_GAP
    with sync_playwright() as p:
        b = _launch_browser(p)
        pg = b.new_page(device_scale_factor=1)          # 1x -> image px == CSS px (exact strip dims)

        # 1) RED parallelogram + label  -> transparent PNG (element screenshot)
        lbl_html = f"""<!doctype html><meta charset="utf-8"><style>{ff}
*{{margin:0;padding:0;box-sizing:border-box}}html,body{{background:transparent}}
#lab{{width:{LABEL_W}px;height:{STRIP_H}px;background:{RED};
 clip-path:polygon(0 0,{RED_W}px 0,{LABEL_W}px {STRIP_H}px,0 {STRIP_H}px);
 display:flex;align-items:center;padding-left:{LABEL_PAD}px;overflow:hidden}}
#lab span{{color:#fff;font-family:'NotoTel';font-weight:bold;font-size:{LABEL_SIZE}px;
 white-space:nowrap;-webkit-text-stroke:.5px {STROKE}}}</style>
<div id="lab"><span>{_esc(label_text)}</span></div>"""
        pg.set_content(lbl_html); pg.wait_for_timeout(300)
        # auto-fit the label so it never overflows the red parallelogram (any district name fits)
        pg.eval_on_selector("#lab span", f"el => {{ let fs={LABEL_SIZE}; el.style.fontSize=fs+'px';"
                            f" while(el.scrollWidth > {LABEL_FIT} && fs>{LABEL_MIN}){{ fs--; el.style.fontSize=fs+'px'; }} }}")
        pg.wait_for_timeout(120)
        pg.locator("#lab").screenshot(path=label_png, omit_background=True)

        # 2) navy ticker (repeated text) -> wide PNG; cycle = width/2 (even repeats -> seamless wrap)
        tik_html = f"""<!doctype html><meta charset="utf-8"><style>{ff}
*{{margin:0;padding:0}}body{{background:{NAVY}}}
#t{{display:inline-block;white-space:pre;height:{STRIP_H}px;line-height:{STRIP_H}px;
 background:{NAVY};color:#fff;font-family:'NotoTel';font-weight:bold;font-size:{TICK_SIZE}px;
 letter-spacing:.5px;-webkit-text-stroke:.6px {STROKE}}}</style>
<span id="t">{unit * repeats}</span>"""
        pg.set_content(tik_html); pg.wait_for_timeout(300)
        pg.locator("#t").screenshot(path=ticker_png)
        b.close()

    try:
        import cv2
        cyc = cv2.imread(ticker_png).shape[1] // 2       # image = `repeats` units (even) -> one cycle = width/2
    except Exception:
        cyc = 3000
    return label_png, ticker_png, cyc


def _esc(t):
    return ((t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")).strip()


if __name__ == "__main__":
    # Run as a SUBPROCESS (Playwright sync API can't run inside Streamlit's asyncio loop -> NotImplementedError).
    # Reads {ticker,label} from <D>/pw_params.json, writes pw_label.png / pw_ticker.png / pw_cyc.txt into <D>.
    import sys, json
    D = sys.argv[1] if len(sys.argv) > 1 else "."
    prm = json.load(open(os.path.join(D, "pw_params.json"), encoding="utf-8"))
    l, t, c = render_strip(prm.get("ticker", ""), prm.get("label", ""), D)
    open(os.path.join(D, "pw_cyc.txt"), "w").write(str(c))
    print("OK", l, t, c)
