"""Dung video dang "POV Viet Nam xua": 10-12 clip x 5 giay, hinh co chieu sau chuyen dong (2.5D),
dong chu POV co dinh tren dau, phu de ngan giua-duoi, tieng dong that + nhac nhe, ket bang cau hoi.

Dung: python pov.py JOB_DIR [--mock]
JOB_DIR/script.json theo mau tap-pov/*.json. Ket qua: youtube.mp4 (co nhac), tiktok.mp4 (khong nhac), thumb.jpg.
Dong cuoi stdout: JSON {ok, youtube_video, tiktok_video, thumbnail, duration, clips}.

Bien moi truong dung chung voi render.py (IMAGE_PROVIDER, CF_*, FONT_FILE, FONT_NAME, MUSIC_DIR, SFX_DIR).
Them: CLIP_SECONDS (5), DEPTH_MODEL (depth-anything/Depth-Anything-V2-Small-hf), MOTION (do manh chuyen dong, 1.0).
"""
import json, os, sys, subprocess, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R
import numpy as np
import cv2

W, H, FPS = R.W, R.H, R.FPS
ENV = os.environ.get
CLIP = float(ENV("CLIP_SECONDS", "5"))
XF = 0.4
END = 4.0
MOTION = float(ENV("MOTION", "1.0"))
log = R.log


# ------------------------------------------------------------ chieu sau
_depth_pipe = None


def depth_map(img_bgr, mock=False):
    """Tra ve ban do chieu sau 0..1 (1 = gan). Loi mo hinh thi dung do doc (duoi gan, tren xa)."""
    global _depth_pipe
    h, w = img_bgr.shape[:2]
    fallback = np.tile(np.linspace(0.15, 1.0, h, dtype=np.float32)[:, None], (1, w))
    if mock:
        return fallback
    try:
        if _depth_pipe is None:
            from transformers import pipeline
            _depth_pipe = pipeline("depth-estimation", model=ENV("DEPTH_MODEL", "depth-anything/Depth-Anything-V2-Small-hf"))
        from PIL import Image
        out = _depth_pipe(Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)))
        d = np.array(out["predicted_depth"] if not hasattr(out["depth"], "size") else out["depth"], dtype=np.float32)
        d = cv2.resize(d, (w, h), interpolation=cv2.INTER_CUBIC)
        d = (d - d.min()) / max(float(d.max() - d.min()), 1e-6)       # Depth Anything: lon = gan
        return d
    except Exception as e:
        log("khong uoc luong duoc chieu sau, dung do doc:", e)
        return fallback


# ------------------------------------------------------------ chuyen dong 2.5D
def ease(t):
    return 0.5 - 0.5 * math.cos(math.pi * t)


def render_clip(img_path, out, seconds, move, mock=False):
    src = cv2.imread(img_path)
    if src is None:
        raise SystemExit(f"Khong doc duoc anh {img_path}")
    pad = 1.18                                    # anh lon hon khung de co cho di chuyen
    cw, ch = int(W * pad), int(H * pad)
    sh, sw = src.shape[:2]
    sc = max(cw / sw, ch / sh)
    canvas = cv2.resize(src, (int(sw * sc + 0.5), int(sh * sc + 0.5)), interpolation=cv2.INTER_LANCZOS4)
    y0, x0 = (canvas.shape[0] - ch) // 2, (canvas.shape[1] - cw) // 2
    canvas = canvas[y0:y0 + ch, x0:x0 + cw]
    d = depth_map(canvas, mock)
    d = cv2.GaussianBlur(d, (0, 0), 9)            # mem bien de khong rach hinh
    ox, oy = (cw - W) / 2, (ch - H) / 2
    U, V = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    D = d[int(oy):int(oy) + H, int(ox):int(ox) + W]
    near = 0.35 + 0.9 * D                         # lop gan di nhieu hon lop xa
    cu, cv_ = W / 2, H / 2
    n = int(round(seconds * FPS))
    m = MOTION
    seed = random.random() * 10
    p_ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             "-vf", ENV("LOOK", "noise=alls=3:allf=t,vignette=PI/7,eq=saturation=1.02:contrast=1.03,"
                                    "colorbalance=rs=0.02:bs=-0.02") + ",format=yuv420p",
                             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out], stdin=subprocess.PIPE)
    for i in range(n):
        t = ease(i / max(n - 1, 1))
        zoom, tx, ty = 1.0, 0.0, 0.0
        if move == "push":
            zoom = 1.0 + 0.10 * m * t
        elif move == "pull":
            zoom = 1.10 * m - 0.10 * m * t if m else 1.0
            zoom = max(zoom, 1.0)
        elif move == "pan_r":
            tx, zoom = -0.045 * W * m * (t - 0.5), 1.04
        elif move == "pan_l":
            tx, zoom = 0.045 * W * m * (t - 0.5), 1.04
        elif move == "up":
            ty, zoom = 0.04 * H * m * (t - 0.5), 1.04
        elif move == "down":
            ty, zoom = -0.04 * H * m * (t - 0.5), 1.04
        # rung tay nhe nhu cam may quay
        tt = i / FPS
        hx = 2.2 * math.sin(tt * 1.3 + seed) + 1.1 * math.sin(tt * 2.9 + seed * 2)
        hy = 1.8 * math.sin(tt * 1.1 + seed * 3) + 0.9 * math.sin(tt * 3.3 + seed)
        S = 1.0 + (zoom - 1.0) * near
        map_x = (cu + ox) + (U - cu) / S - tx * near - hx
        map_y = (cv_ + oy) + (V - cv_) / S - ty * near - hy
        frame = cv2.remap(canvas, map_x.astype(np.float32), map_y.astype(np.float32),
                          cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        p_ff.stdin.write(frame.tobytes())
    p_ff.stdin.close()
    if p_ff.wait() != 0:
        raise SystemExit("ffmpeg loi khi ghi clip")


# ------------------------------------------------------------ chu tren man hinh
BN = "\\N"
def write_ass(path, banner, cues, end_q, total):
    fn = R.FONT_NAME
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Banner,{fn},58,&H0040E6FF,&H0040E6FF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,4,2,8,40,40,{int(ENV('BANNER_MARGIN', '260'))},1
Style: Cap,{fn},58,&H0040E6FF,&H0040E6FF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,4,2,2,50,50,{int(ENV("CAP_MARGIN", "430"))},1
Style: End,{fn},78,&H00B8F2FF,&H00FFFFFF,&H00101010,&H78000000,1,0,0,0,100,100,0,0,1,6,3,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    L = [head]
    if banner:
        L.append(f"Dialogue: 2,{R.ass_time(0)},{R.ass_time(total - END + 0.2)},Banner,,0,0,0,,"
                 f"{{\\fad(250,300)}}{BN.join(R.ass_escape(x) for x in banner.split(chr(10)))}\n")
    for a, b, txt in cues:
        L.append(f"Dialogue: 1,{R.ass_time(a)},{R.ass_time(b)},Cap,,0,0,0,,{{\\fad(180,180)}}{R.ass_escape(txt)}\n")
    if end_q:
        L.append(f"Dialogue: 2,{R.ass_time(total - END + 0.3)},{R.ass_time(total)},End,,0,0,0,,"
                 f"{{\\fad(300,0)}}{R.ass_escape(end_q)}\\N\\N{{\\fs52\\c&HFFFFFF&}}{R.ass_escape(R.CHANNEL)} · 19h mỗi ngày\n")
    open(path, "w", encoding="utf-8").write("".join(L))


# ------------------------------------------------------------ chinh
def main():
    job = sys.argv[1]
    mock = "--mock" in sys.argv
    R.font_ok()
    sc = json.load(open(os.path.join(job, "script.json"), encoding="utf-8"))
    clips = sc["clips"]
    provider = "mock" if mock else ENV("IMAGE_PROVIDER", "cloudflare")
    base = float(sc.get("clip_seconds", CLIP))
    durs = [float(c.get("seconds", base)) for c in clips]          # do dai tung clip (cat nhanh o dau)
    starts = [sum(durs[:i]) for i in range(len(clips))]
    for d in ("images", "parts"):
        os.makedirs(os.path.join(job, d), exist_ok=True)

    # 1) anh
    style = sc.get("style", "")
    for i, c in enumerate(clips):
        img = os.path.join(job, "images", f"clip_{i:02d}.png")
        if not os.path.exists(img):
            R.gen_image(c["prompt"] + ", " + style, img, provider, mock_idx=i)

    # 2) clip chuyen dong
    parts = []
    for i, c in enumerate(clips):
        part = os.path.join(job, "parts", f"c_{i:02d}.mp4")
        if not os.path.exists(part):
            render_clip(os.path.join(job, "images", f"clip_{i:02d}.png"), part, durs[i] + XF, c.get("move", "push"), mock)
        parts.append(part)
    # canh ket: anh cuoi lam mo
    last_img = os.path.join(job, "images", f"clip_{len(clips) - 1:02d}.png")
    end_part = os.path.join(job, "parts", "end.mp4")
    R.run(["ffmpeg", "-y", "-loop", "1", "-i", last_img, "-t", f"{END:.2f}", "-vf",
           f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=14:2,eq=brightness=-0.15,"
           f"fade=t=out:st={END - 0.8:.2f}:d=0.8,format=yuv420p", "-r", str(FPS),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", end_part])
    parts.append(end_part)

    n = len(clips)
    total = round(sum(durs) + END, 3)

    # 2b) loi ke: tao truoc de biet do dai, xep noi tiep khong chong nhau
    vt = {}
    nxt = 0.0
    for i, c in enumerate(clips):
        if not c.get("voice"):
            continue
        os.makedirs(os.path.join(job, "voice"), exist_ok=True)
        vf_ = os.path.join(job, "voice", f"v_{i:02d}.mp3")
        if not os.path.exists(vf_):
            R.tts(c["voice"], vf_, mock=mock)
        st = max(starts[i] + 0.3, nxt)
        ln = R.dur(vf_)
        vt[i] = (st, ln, vf_)
        nxt = st + ln + 0.35

    # 3) chu
    cues = []
    for i, c in enumerate(clips):
        if i in vt:
            a, ln, _ = vt[i]
            cues.append((a - 0.1, a + ln + 0.25, c["voice"]))
        elif c.get("caption"):
            a = starts[i] + 0.25
            cues.append((a, a + durs[i] - 0.35, c["caption"]))
    ass = os.path.join(job, "subs.ass")
    write_ass(ass, sc.get("banner", ""), [x for x in cues if x[2]], sc.get("end_question", ""), total)

    # 4) noi clip bang xfade + chu
    inputs, fc = [], []
    for p in parts:
        inputs += ["-i", p]
    prev, off = "[0:v]", 0.0
    lens = [d + XF for d in durs] + [END]
    for k in range(1, len(parts)):
        off += lens[k - 1] - XF
        lab = f"[x{k}]"
        fc.append(f"{prev}[{k}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}{lab}")
        prev = lab
    fc.append(f"{prev}subtitles={R.fp(ass)}:fontsdir={R.fp(os.path.dirname(R.FONT_FILE))},format=yuv420p[vout]")
    silent = os.path.join(job, "video_silent.mp4")
    R.run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-t", f"{total:.3f}",
           "-r", str(FPS), "-c:v", "libx264", "-preset", ENV("X264_PRESET", "medium"), "-crf", "20", silent])

    # 5) am thanh: tieng dong theo tung clip + nhac nhe (ban YouTube)
    a_in, a_fc, labs = [], [], []
    idx = 0
    for i, c in enumerate(clips):
        f = R.pick_file(R.SFX_DIR, c.get("sfx", "")) if c.get("sfx") else None
        if not f:
            continue
        hit = [x for x in os.listdir(R.SFX_DIR) if c["sfx"].lower() in x.lower()]
        if not hit:
            continue
        a_in += ["-i", f]
        st, dc = starts[i], durs[i]
        a_fc.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{dc + 0.6:.2f},"
                    f"afade=t=in:d=0.3,afade=t=out:st={dc - 0.4:.2f}:d=1.0,volume={ENV('SFX_VOL', '0.55')},"
                    f"adelay={int(st * 1000)}:all=1[s{idx}]")
        labs.append(f"[s{idx}]")
        idx += 1
    bed = [x for x in (os.listdir(R.SFX_DIR) if os.path.isdir(R.SFX_DIR) else []) if x.lower().startswith("nen")]
    if bed:                                   # nen am thanh lang que, rat nho, suot video
        a_in += ["-stream_loop", "-1", "-i", os.path.join(R.SFX_DIR, sorted(bed)[0])]
        a_fc.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},"
                    f"volume={ENV('BED_VOL', '0.22')},afade=t=in:d=1.5[s{idx}]")
        labs.append(f"[s{idx}]")
        idx += 1
    if labs:
        a_fc.append(f"{''.join(labs)}amix=inputs={len(labs)}:normalize=0:duration=longest,"
                    f"apad=whole_dur={total:.3f},atrim=0:{total:.3f}[sfx]")
    else:
        a_fc.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.3f}[sfx]")
    tk_a, yt_a = os.path.join(job, "tk.m4a"), os.path.join(job, "yt.m4a")
    # loi ke ngan (truong "voice" cua clip): giong tram am, tieng dong tu nho lai khi co loi
    vo = sorted(vt.items())
    if vo:
        v_lab = []
        for k, (i, (st, ln, vf_)) in enumerate(vo):
            a_in += ["-i", vf_]
            a_fc.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,{R.VOICE_FX}"
                        f"volume={ENV('VOICE_VOL', '1.0')},adelay={int(st * 1000)}:all=1[v{k}]")
            v_lab.append(f"[v{k}]")
            idx += 1
        a_fc.append(f"{''.join(v_lab)}amix=inputs={len(v_lab)}:normalize=0:duration=longest,"
                    f"apad=whole_dur={total:.3f},atrim=0:{total:.3f},asplit=2[vo][vsc]")
        a_fc.append("[sfx][vsc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[sfxd]")
        a_fc.append("[sfxd][vo]amix=inputs=2:normalize=0:duration=first[mixv]")
        last = "[mixv]"
    else:
        last = "[sfx]"
    R.run(["ffmpeg", "-y", *a_in, "-filter_complex", ";".join(a_fc) + f";{last}alimiter=limit=0.95[o]",
           "-map", "[o]", "-c:a", "aac", "-b:a", "192k", tk_a])
    music = R.pick_file(R.MUSIC_DIR, sc.get("music_mood", ""))
    if music:
        R.run(["ffmpeg", "-y", "-i", tk_a, "-stream_loop", "-1", "-i", music, "-filter_complex",
               f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},volume={ENV('MUSIC_VOL', '0.22' if vo else '0.32')},"
               f"afade=t=in:d=1.5,afade=t=out:st={total - 2.5:.3f}:d=2.5[m];"
               f"[0:a][m]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[o]",
               "-map", "[o]", "-t", f"{total:.3f}", "-c:a", "aac", "-b:a", "192k", yt_a])
    else:
        yt_a = tk_a
    outs = {}
    for name, a in (("youtube", yt_a), ("tiktok", tk_a)):
        o = os.path.join(job, f"{name}.mp4")
        R.run(["ffmpeg", "-y", "-i", silent, "-i", a, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
               "-t", f"{total:.3f}", "-movflags", "+faststart", o])
        outs[name] = o

    # 6) anh bia: anh dep nhat + dong POV
    ti = min(max(int(sc.get("thumbnail_clip", 0)), 0), n - 1)
    lines = [x for x in (sc.get("thumbnail_text") or "").split("\n") if x.strip()] or [sc.get("thumbnail_text", "")]
    vf = [f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},eq=contrast=1.06:saturation=1.05"]
    btxt = os.path.join(job, "thumb_banner.txt")
    open(btxt, "w", encoding="utf-8").write((sc.get("banner") or "").split("\n")[0])
    vf.append(f"drawbox=x=0:y=150:w=iw:h=150:color=black@0.55:t=fill")
    vf.append(f"drawtext=fontfile={R.fp(R.FONT_FILE)}:textfile={R.fp(btxt)}:fontsize=52:fontcolor=white:"
              f"x=(w-tw)/2:y=150+(150-th)/2")
    for k, line in enumerate(lines[:2]):
        tf = os.path.join(job, f"thumb{k}.txt")
        open(tf, "w", encoding="utf-8").write(line)
        vf.append(f"drawtext=fontfile={R.fp(R.FONT_FILE)}:textfile={R.fp(tf)}:fontsize=120:fontcolor=0xFFE7B0:"
                  f"borderw=7:bordercolor=black:x=(w-tw)/2:y={int(H * 0.62) + k * 150}")
    thumb = os.path.join(job, "thumb.jpg")
    R.run(["ffmpeg", "-y", "-i", os.path.join(job, "images", f"clip_{ti:02d}.png"), "-vf", ",".join(vf),
           "-frames:v", "1", "-q:v", "3", thumb])
    res = {"ok": True, "youtube_video": outs["youtube"], "tiktok_video": outs["tiktok"], "thumbnail": thumb,
           "duration": round(R.dur(outs["youtube"]), 2), "clips": n}
    json.dump(res, open(os.path.join(job, "result.json"), "w"), ensure_ascii=False)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
