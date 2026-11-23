#!/usr/bin/env python3
"""
Ky Uc Que Nha - dung video doc 9:16 tu kich ban JSON.

Cach chay:  python3 render.py /files/jobs/<ma_tap>  [--mock]
Thu muc tap phai co script.json (do Claude viet). Ket qua:
  youtube.mp4  (giong doc + nhac nen + am thanh moi truong)
  tiktok.mp4   (giong doc + am thanh moi truong, KHONG nhac nen -> Dai Ca them nhac trend tren TikTok)
  thumb.jpg, subs.ass, result.json
Dong cuoi cung in ra stdout la JSON ket qua de n8n doc.

Bien moi truong (deu co mac dinh):
  IMAGE_PROVIDER   openai | pollinations | existing    (mac dinh: openai neu co OPENAI_API_KEY, nguoc lai pollinations)
  IMAGE_MODEL      mac dinh gpt-image-1-mini
  IMAGE_QUALITY    low | medium | high   (mac dinh medium)
  TTS_VOICE        vi-VN-HoaiMyNeural (nu) | vi-VN-NamMinhNeural (nam)
  TTS_RATE         mac dinh -8%  (doc cham, hoai niem)
  TARGET_SECONDS   mac dinh 178  (duoi gioi han 180 giay cua Shorts)
  MUSIC_DIR, SFX_DIR, FONT_FILE, FONT_NAME, CHANNEL_NAME, FILM_LOOK (1/0)
"""
import json, os, random, re, subprocess, sys, time, urllib.parse, urllib.request, urllib.error, base64, asyncio, shutil

W, H, FPS = 1080, 1920, 30
XF = 0.5          # thoi gian chuyen canh (giay)
PAUSE = 0.35      # nghi sau moi canh
# giong am, tram hon: tang nhe tan so thap, giam chut tan so cao, vang rat nhe
VOICE_FX = os.environ.get("VOICE_FX", "equalizer=f=140:t=q:w=1:g=3,equalizer=f=5000:t=q:w=1.2:g=-2,aecho=0.8:0.6:40:0.08,")
SUB_MARGIN = int(os.environ.get("SUB_MARGIN", "330"))   # phu de cach day (px); thap hon = gan day hon
LEAD = 0.4        # khoang lang dau video

ENV = os.environ.get
TARGET = float(ENV("TARGET_SECONDS", "178"))
MUSIC_DIR = ENV("MUSIC_DIR", "/files/music")
SFX_DIR = ENV("SFX_DIR", "/files/sfx")
FONT_FILE = ENV("FONT_FILE", "/usr/share/fonts/truetype/bevietnam/BeVietnamPro-SemiBold.ttf")
FONT_NAME = ENV("FONT_NAME", "Be Vietnam Pro SemiBold")
CHANNEL = ENV("CHANNEL_NAME", "Ký Ức Quê Nhà")
FILM_LOOK = ENV("FILM_LOOK", "1") == "1"
CROP_BOTTOM = float(ENV("CROP_BOTTOM", "0"))   # vd 0.05: cat bot day anh (vien loi). Khong dung de xoa logo ghi nguon.
PRECROP = f"crop=iw:ih*{1-CROP_BOTTOM:.3f}:0:0," if CROP_BOTTOM > 0 else ""
VOICE = ENV("TTS_VOICE", "vi-VN-HoaiMyNeural")
RATE = ENV("TTS_RATE", "+0%")
PITCH = ENV("TTS_PITCH", "-6Hz")          # giong tram hon mot chut
FPT_KEY = ENV("FPT_API_KEY")               # giong mien Nam (Sai Gon xua)
FPT_VOICE_NAM = ENV("FPT_VOICE_NAM", "lannhi")
FPT_VOICE_BAC = ENV("FPT_VOICE_BAC", "")   # de trong = dung Edge HoaiMy cho giong Bac


def log(*a):
    print("[render]", *a, file=sys.stderr, flush=True)


def run(cmd):
    log(" ".join(cmd[:6]), "...")
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        log(p.stderr[-3000:])
        raise SystemExit(f"ffmpeg loi: {' '.join(cmd[:4])}")
    return p.stdout


def dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path], stdout=subprocess.PIPE, text=True).stdout
    return float(out.strip())


def fp(path):
    """Duong dan an toan trong bo loc FFmpeg (ca Windows: C:/... -> C\\:/...)."""
    return "'" + str(path).replace("\\", "/").replace(":", "\\:") + "'"


def font_ok():
    if not os.path.exists(FONT_FILE):
        raise SystemExit(f"Khong thay font {FONT_FILE}. Kiem tra Dockerfile hoac dat FONT_FILE.")


# ---------------------------------------------------------------- hinh anh
STYLE = (" Photorealistic 35mm film photograph, shot on Kodak Gold 200, natural light, "
         "authentic period details, real Vietnamese people, candid, no text, no letters, "
         "no watermark, no modern objects, vertical 9:16 composition.")
# Mo hinh AI hay lam meo mat nguoi -> mac dinh: nguoi o xa, quay lung, nhin nghieng, hoac chi tay; khong can mat
STYLE += ENV("FACE_SAFE", " People appear small in the frame, seen from behind, in profile or far away, "
                          "faces not visible or softly out of focus, no close-up portraits, natural relaxed hands.")


def gen_image(prompt, out, provider, mock_idx=None):
    if provider == "mock":
        hue = (mock_idx * 37) % 360
        run(["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"gradients=s=1024x1536:c0=0x8a6a3a:c1=0x2f4422:x0=0:y0=0:x1=1024:y1=1536:d=1",
             "-vf", f"hue=h={hue},drawgrid=w=128:h=128:t=2:c=white@0.25",
             "-frames:v", "1", out])
        return
    if provider == "openai":
        key = ENV("OPENAI_API_KEY")
        body = json.dumps({"model": ENV("IMAGE_MODEL", "gpt-image-1-mini"), "prompt": prompt + STYLE,
                           "size": "1024x1536", "quality": ENV("IMAGE_QUALITY", "medium"), "n": 1}).encode()
        req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=body,
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = json.load(r)["data"][0]
                if data.get("b64_json"):
                    open(out, "wb").write(base64.b64decode(data["b64_json"]))
                else:
                    urllib.request.urlretrieve(data["url"], out)
                return
            except Exception as e:
                log("openai image loi, thu lai:", e)
                time.sleep(5 * (attempt + 1))
        raise SystemExit("Khong tao duoc hinh bang OpenAI")
    if provider == "cloudflare":
        # Workers AI, goi mien phi 10.000 neuron/ngay (du cho ~1 video/ngay). CF_FILE: dong 1 Account ID, dong 2 token.
        acc, tok = ENV("CF_ACCOUNT_ID", ""), ENV("CF_API_TOKEN", "")
        if not (acc and tok) and ENV("CF_FILE") and os.path.exists(ENV("CF_FILE")):
            lines = [l.strip() for l in open(ENV("CF_FILE"), encoding="utf-8-sig") if l.strip()]
            acc, tok = lines[0], lines[1]
        model = ENV("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-2-klein-4b")
        fields = {"prompt": prompt + STYLE, "width": ENV("CF_W", "768"), "height": ENV("CF_H", "1344"),
                  "seed": str(random.randint(1, 2**31 - 1))}
        if ENV("CF_STEPS"):
            fields["steps"] = ENV("CF_STEPS")
        if "flux-2" in model:      # FLUX.2 tren Cloudflare nhan multipart/form-data
            bnd = "----kuqn" + str(random.randint(10**8, 10**9))
            data = "".join(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
                           for k, v in fields.items()).encode("utf-8") + f"--{bnd}--\r\n".encode()
            ctype = f"multipart/form-data; boundary={bnd}"
        else:
            body = {"prompt": fields["prompt"], "steps": int(ENV("CF_STEPS", "8"))}
            if ENV("CF_SIZE", "1"):
                body.update({"width": int(fields["width"]), "height": int(fields["height"])})
            data, ctype = json.dumps(body).encode(), "application/json"
        for attempt in range(4):
            try:
                req = urllib.request.Request(
                    f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{model}",
                    data=data, headers={"Authorization": f"Bearer {tok}", "Content-Type": ctype})
                with urllib.request.urlopen(req, timeout=180) as r:
                    raw = r.read()
                try:
                    img = base64.b64decode(json.loads(raw)["result"]["image"])
                except (ValueError, KeyError, TypeError):
                    img = raw                                  # mot so mo hinh tra thang file anh
                if len(img) > 20000:
                    open(out, "wb").write(img)
                    return
            except urllib.error.HTTPError as e:
                log("cloudflare loi", e.code, e.read()[:300])
                if e.code in (400, 401, 403):
                    raise SystemExit(f"Cloudflare tu choi ({e.code}), kiem tra token/model")
            except Exception as e:
                log("cloudflare loi, thu lai:", e)
            time.sleep(15 * (attempt + 1))
        raise SystemExit("Khong tao duoc hinh bang Cloudflare Workers AI")
    if provider == "pollinations":
        # Mien phi, khong can khoa. Chat luong va toc do khong on dinh -> dung de chay thu.
        url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt + STYLE) +
               f"?width=1080&height=1920&nologo=true&seed={random.randint(1, 10**6)}")
        # Ban mien phi gioi han ~1 anh / 45 giay / IP (loi 402 FREE_LIMIT) -> cho 50 giay giua cac lan.
        for attempt in range(8):
            try:
                urllib.request.urlretrieve(url, out)
                if os.path.getsize(out) > 20000:
                    time.sleep(float(ENV("POLLINATIONS_GAP", "47")))
                    return
            except Exception as e:
                log("pollinations loi, thu lai:", e)
            time.sleep(50)
        raise SystemExit("Khong tao duoc hinh bang Pollinations")
    raise SystemExit(f"Thieu hinh {out} (IMAGE_PROVIDER=existing)")


# ---------------------------------------------------------------- giong doc
def tts_fpt(text, out, voice):
    req = urllib.request.Request("https://api.fpt.ai/hmi/tts/v5", data=text.encode("utf-8"),
                                 headers={"api-key": FPT_KEY, "voice": voice, "speed": ENV("FPT_SPEED", "-1"),
                                          "format": "mp3"})
    with urllib.request.urlopen(req, timeout=60) as r:
        link = json.load(r)["async"]
    for _ in range(30):            # FPT tra link, file san sang sau vai giay
        time.sleep(3)
        try:
            urllib.request.urlretrieve(link, out)
            if os.path.getsize(out) > 1000:
                return
        except Exception:
            pass
    raise SystemExit("FPT.AI khong tra file giong doc")


def tts(text, out, mock=False, accent="bac"):
    if mock:
        secs = max(2.0, len(text.split()) / 2.5)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={secs:.2f}",
             "-af", "volume=0.05", "-ar", "48000", out])
        return
    fpt_voice = FPT_VOICE_NAM if accent == "nam" else FPT_VOICE_BAC
    if FPT_KEY and fpt_voice:
        return tts_fpt(text, out, fpt_voice)
    if accent == "nam":
        log("CANH BAO: chua co FPT_API_KEY, tap mien Nam tam dung giong Bac")
    import edge_tts

    async def go():
        await edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH).save(out)
    for attempt in range(6):
        try:
            asyncio.run(go())
            if os.path.getsize(out) > 1000:
                return
        except Exception as e:
            log("edge-tts loi, thu lai:", e)
            time.sleep(5)
    raise SystemExit("Khong tao duoc giong doc")


# ---------------------------------------------------------------- phu de
def chunks(text, max_chars=34):
    words, cur, res = text.split(), [], []
    for w in words:
        if cur and (len(" ".join(cur + [w])) > max_chars):
            res.append(" ".join(cur)); cur = []
        cur.append(w)
        if re.search(r"[.,!?;:…]$", w) and len(" ".join(cur)) > 14:
            res.append(" ".join(cur)); cur = []
    if cur:
        res.append(" ".join(cur))
    return res


def ass_time(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def write_ass(path, cues, hook, notes=()):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{FONT_NAME},66,&H00FFFFFF,&H00FFFFFF,&H00101010,&H64000000,0,0,0,0,100,100,0,0,1,5,2,2,80,80,{SUB_MARGIN},1
Style: Hook,{FONT_NAME},84,&H00B8F2FF,&H00FFFFFF,&H00101010,&H64000000,0,0,0,0,100,100,0,0,1,6,3,8,70,70,260,1
Style: Note,{FONT_NAME},62,&H00B8F2FF,&H00FFFFFF,&H00101010,&H64000000,0,0,0,0,100,100,0,0,1,5,2,8,70,70,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [head]
    if hook:
        lines.append(f"Dialogue: 1,{ass_time(0.2)},{ass_time(3.2)},Hook,,0,0,0,,{{\\fad(300,300)}}{ass_escape(hook)}\n")
    for s, e, t in cues:
        lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Sub,,0,0,0,,{ass_escape(t)}\n")
    for s, e, t in notes:
        lines.append(f"Dialogue: 1,{ass_time(s)},{ass_time(e)},Note,,0,0,0,,{{\\fad(250,250)}}{ass_escape(t)}\n")
    open(path, "w", encoding="utf-8").write("".join(lines))


# ---------------------------------------------------------------- chuyen dong
def motion_expr(kind, n):
    c_x, c_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    p = f"(on/{n})"
    table = {
        "zoom_in":  (f"1.0+0.14*{p}", c_x, c_y),
        "zoom_out": (f"1.14-0.14*{p}", c_x, c_y),
        "pan_left": ("1.12", f"(iw-iw/zoom)*(1-{p})", c_y),
        "pan_right": ("1.12", f"(iw-iw/zoom)*{p}", c_y),
        "pan_up":   ("1.12", c_x, f"(ih-ih/zoom)*(1-{p})"),
        "pan_down": ("1.12", c_x, f"(ih-ih/zoom)*{p}"),
        "static":   (f"1.03+0.02*{p}", c_x, c_y),
    }
    return table.get(kind, table["zoom_in"])


def scene_clip(img, out, seconds, kind, clip=None):
    look = ",noise=alls=7:allf=t,vignette=PI/5,eq=saturation=0.88:gamma=1.02,colorbalance=rs=0.03:bs=-0.04" if FILM_LOOK else ""
    if clip and os.path.exists(clip):   # clip AI (Kling...) neu co
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", clip, "-t", f"{seconds:.3f}", "-an", "-vf",
             f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}{look},format=yuv420p",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out])
        return
    n = int(round(seconds * FPS))
    z, x, y = motion_expr(kind, n)
    vf = (f"{PRECROP}scale={W*3//2}:{H*3//2}:force_original_aspect_ratio=increase,crop={W*3//2}:{H*3//2},"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={FPS}{look},format=yuv420p")
    run(["ffmpeg", "-y", "-i", img, "-vf", vf, "-frames:v", str(n),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out])


def pick_file(folder, keyword):
    if not os.path.isdir(folder):
        return None
    files = [f for f in os.listdir(folder) if f.lower().endswith((".mp3", ".wav", ".m4a", ".ogg"))]
    if not files:
        return None
    hit = [f for f in files if keyword and keyword.lower() in f.lower()]
    return os.path.join(folder, random.choice(hit or files))


# ---------------------------------------------------------------- chinh
def main():
    global TARGET
    job = sys.argv[1]
    mock = "--mock" in sys.argv
    font_ok()
    sc = json.load(open(os.path.join(job, "script.json"), encoding="utf-8"))
    scenes = sc["scenes"]
    provider = "mock" if mock else ENV("IMAGE_PROVIDER") or ("openai" if ENV("OPENAI_API_KEY") else "pollinations")
    for d in ("images", "audio", "clips", "parts"):
        os.makedirs(os.path.join(job, d), exist_ok=True)

    # 1) hinh + giong doc cho tung canh (chay lai thi bo qua phan da co)
    for i, s in enumerate(scenes):
        img = os.path.join(job, "images", f"scene_{i:02d}.png")
        if not os.path.exists(img) or os.path.getsize(img) < 1000:
            gen_image(s["image_prompt"], img, provider, i)
        aud = os.path.join(job, "audio", f"scene_{i:02d}.mp3")
        if not s.get("narration", "").strip():      # canh chi co hinh, khong loi
            if not os.path.exists(aud):
                run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo", "-t",
                     str(float(s.get("seconds", 4))), aud])
            s["narration"] = ""
        elif not os.path.exists(aud) or os.path.getsize(aud) < 1000:
            tts(s["narration"], aud, mock, sc.get("accent", "bac"))
        s["_voice"] = dur(aud)

    # 2) tinh thoi luong, neu dai qua thi tang toc giong doc nhe
    voice_total = sum(s["_voice"] for s in scenes)
    global PAUSE
    min_outro = 4.0
    PAUSE = float(ENV("PAUSE", "0.35")) if len(scenes) <= 20 else float(ENV("PAUSE_MANY", "0.25"))    # nhieu canh ngan thi nghi ngan hon
    budget = TARGET - LEAD - min_outro - PAUSE * len(scenes)
    tempo = 1.0
    if voice_total > budget:
        tempo = voice_total / budget
        if tempo > 1.15:
            print(json.dumps({"ok": False, "error": "too_long", "voice_seconds": round(voice_total, 1),
                              "budget_seconds": round(budget, 1)}))
            sys.exit(3)
    # thoi gian con du: chia deu cho cac canh (hinh dung lau hon, nhip cham), outro toi da OUTRO_MAX giay
    outro_max = float(ENV("OUTRO_MAX", "7"))
    if ENV("FIT_VOICE", "1") == "1":   # video dai dung bang giong doc: hinh khop loi, khong keo gian
        TARGET = min(TARGET, LEAD + voice_total / tempo + PAUSE * len(scenes) + outro_max)
    spare = TARGET - LEAD - voice_total / tempo - PAUSE * len(scenes) - outro_max
    extra = max(spare, 0) / len(scenes)
    for k, s in enumerate(scenes):
        s["_slot"] = s["_voice"] / tempo + PAUSE + extra + (LEAD if k == 0 else 0)
    outro = TARGET - sum(s["_slot"] for s in scenes)
    log(f"giong {voice_total:.1f}s, tempo {tempo:.3f}, outro {outro:.1f}s")

    # 3) clip tung canh (moi clip dai them XF de chong mi)
    parts = []
    for i, s in enumerate(scenes):
        part = os.path.join(job, "parts", f"p_{i:02d}.mp4")
        scene_clip(os.path.join(job, "images", f"scene_{i:02d}.png"), part, s["_slot"] + XF,
                   s.get("motion", "zoom_in"), os.path.join(job, "clips", f"scene_{i:02d}.mp4"))
        parts.append(part)
    # outro: canh thumbnail, chu ten kenh
    ti = min(max(int(sc.get("thumbnail_scene", 0)), 0), len(scenes) - 1)
    outro_raw = os.path.join(job, "parts", "outro_raw.mp4")
    scene_clip(os.path.join(job, "images", f"scene_{ti:02d}.png"), outro_raw, outro, "zoom_out")
    open(os.path.join(job, "outro1.txt"), "w", encoding="utf-8").write(CHANNEL)
    open(os.path.join(job, "outro2.txt"), "w", encoding="utf-8").write(sc.get("outro_text", "Tập mới mỗi ngày lúc 19h"))
    outro_part = os.path.join(job, "parts", "p_outro.mp4")
    run(["ffmpeg", "-y", "-i", outro_raw, "-vf",
         "boxblur=12:2,eq=brightness=-0.12,"
         f"drawtext=fontfile={fp(FONT_FILE)}:textfile={fp(os.path.join(job, 'outro1.txt'))}:fontsize=110:fontcolor=white:borderw=5:bordercolor=black@0.6:x=(w-tw)/2:y=h*0.40,"
         f"drawtext=fontfile={fp(FONT_FILE)}:textfile={fp(os.path.join(job, 'outro2.txt'))}:fontsize=56:fontcolor=0xFFE7B0:borderw=3:bordercolor=black@0.6:x=(w-tw)/2:y=h*0.40+150,"
         "fade=t=out:st=" + f"{max(outro-1.2,0):.2f}:d=1.2",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", outro_part])
    parts.append(outro_part)

    # 4) phu de
    cues, start = [], 0.0
    for k, s in enumerate(scenes):
        segs = chunks(s["narration"])
        total_chars = sum(len(x) for x in segs) or 1
        span, cur = s["_voice"] / tempo, start + (LEAD if k == 0 else 0)
        norm = lambda t: re.sub(r"\W+", "", (t or "").lower())
        dup = k == 0 and sc.get("hook_text") and norm(sc["hook_text"]) == norm(s["narration"])
        for seg in segs:
            d = span * len(seg) / total_chars
            if not dup:          # cau mo dau trung dong hook -> khong lap phu de
                cues.append((cur, cur + d - 0.05, seg))
            cur += d
        start += s["_slot"]
    notes, st = [], 0.0
    for k, s in enumerate(scenes):
        txt = (s.get("on_screen_text") or "").strip()
        if txt and not (k == 0 and sc.get("hook_text")):
            notes.append((st + 0.3, st + s["_slot"] - 0.2, txt))
        st += s["_slot"]
    ass = os.path.join(job, "subs.ass")
    write_ass(ass, cues, sc.get("hook_text", ""), notes)

    # 5) noi canh bang xfade + chay phu de -> video khong tieng
    inputs, fc, prev, off = [], [], "0:v", 0.0
    for p in parts:
        inputs += ["-i", p]
    lengths = [s["_slot"] + XF for s in scenes] + [outro]
    for i in range(1, len(parts)):
        off += lengths[i - 1] - XF
        fc.append(f"[{prev}][{i}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}[v{i}]")
        prev = f"v{i}"
    fc.append(f"[{prev}]ass={fp(ass)}:fontsdir={fp(os.path.dirname(FONT_FILE))},format=yuv420p[vout]")
    silent = os.path.join(job, "video_silent.mp4")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-t", f"{TARGET:.3f}",
         "-r", str(FPS), "-c:v", "libx264", "-preset", ENV("X264_PRESET", "medium"), "-crf", "20", silent])

    # 6) am thanh: giong doc + am thanh moi truong (+ nhac nen cho YouTube)
    a_in, a_fc, labels = [], [], []
    for i, s in enumerate(scenes):
        a_in += ["-i", os.path.join(job, "audio", f"scene_{i:02d}.mp3")]
        pre = f"adelay={int(LEAD*1000)}:all=1," if i == 0 else ""
        a_fc.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,atempo={tempo:.4f},{pre}"
                    f"apad=whole_dur={s['_slot']:.3f}[a{i}]")
        labels.append(f"[a{i}]")
    a_fc.append(f"{''.join(labels)}concat=n={len(scenes)}:v=0:a=1,{VOICE_FX}apad=whole_dur={TARGET:.3f}[voice]")
    nxt = len(scenes)
    sfx_labels, start = [], 0.0
    for i, s in enumerate(scenes):
        f = pick_file(SFX_DIR, s.get("sfx", "")) if s.get("sfx") else None
        if f:
            a_in += ["-stream_loop", "-1", "-i", f]
            a_fc.append(f"[{nxt}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{s['_slot']:.3f},"
                        f"afade=t=in:d=0.6,afade=t=out:st={max(s['_slot']-0.8,0):.3f}:d=0.8,volume=0.22,"
                        f"adelay={int(start*1000)}:all=1[s{i}]")
            sfx_labels.append(f"[s{i}]"); nxt += 1
        start += s["_slot"]
    if sfx_labels:
        a_fc.append(f"{''.join(sfx_labels)}amix=inputs={len(sfx_labels)}:normalize=0:duration=longest,"
                    f"apad=whole_dur={TARGET:.3f}[sfx]")
    else:
        a_fc.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{TARGET:.3f}[sfx]")
    a_fc.append("[voice]asplit=3[v1][v2][vsc]")
    a_fc.append("[sfx]asplit=2[sx1][sx2]")
    # TikTok: giong + moi truong
    a_fc.append(f"[v1][sx1]amix=inputs=2:normalize=0:duration=first,atrim=0:{TARGET:.3f},alimiter=limit=0.95[tk]")
    music = pick_file(MUSIC_DIR, sc.get("music_mood", ""))
    if music:
        a_in += ["-stream_loop", "-1", "-i", music]
        a_fc.append(f"[{nxt}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{TARGET:.3f},volume=0.30,"
                    f"afade=t=in:d=2,afade=t=out:st={TARGET-3:.3f}:d=3[mraw]")
        a_fc.append("[mraw][vsc]sidechaincompress=threshold=0.03:ratio=8:attack=30:release=600[mduck]")
        a_fc.append(f"[v2][sx2][mduck]amix=inputs=3:normalize=0:duration=first,atrim=0:{TARGET:.3f},alimiter=limit=0.95[yt]")
    else:
        log("CANH BAO: khong co nhac trong", MUSIC_DIR)
        a_fc.append("[vsc]anullsink")
        a_fc.append(f"[v2][sx2]amix=inputs=2:normalize=0:duration=first,atrim=0:{TARGET:.3f},alimiter=limit=0.95[yt]")
    yt_a, tk_a = os.path.join(job, "yt.m4a"), os.path.join(job, "tk.m4a")
    run(["ffmpeg", "-y", *a_in, "-filter_complex", ";".join(a_fc),
         "-map", "[yt]", "-c:a", "aac", "-b:a", "192k", yt_a,
         "-map", "[tk]", "-c:a", "aac", "-b:a", "192k", tk_a])

    # 7) ghep
    outs = {}
    for name, a in (("youtube", yt_a), ("tiktok", tk_a)):
        o = os.path.join(job, f"{name}.mp4")
        run(["ffmpeg", "-y", "-i", silent, "-i", a, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
             "-t", f"{TARGET:.3f}", "-movflags", "+faststart", o])
        outs[name] = o

    # 8) thumbnail doc 1080x1920 voi chu lon
    words, tl = sc.get("thumbnail_text", sc.get("title", "")).upper().split(), [""]
    for w_ in words:                     # toi da ~12 ky tu moi dong
        if tl[-1] and len(tl[-1] + " " + w_) > 12:
            tl.append("")
        tl[-1] = (tl[-1] + " " + w_).strip()
    tl = tl[:3]
    fs, lh = 120, 150
    box_y = int(H * 0.36)
    box_h = lh * len(tl) + 60
    vf = [f"{PRECROP}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},eq=contrast=1.06:saturation=1.05",
          f"drawbox=x=0:y={box_y}:w=iw:h={box_h}:color=black@0.45:t=fill"]
    for k, line in enumerate(tl):
        tf = os.path.join(job, f"thumb{k}.txt")
        open(tf, "w", encoding="utf-8").write(line)
        vf.append(f"drawtext=fontfile={fp(FONT_FILE)}:textfile={fp(tf)}:fontsize={fs}:fontcolor=0xFFE7B0:borderw=6:"
                  f"bordercolor=black:x=(w-tw)/2:y={box_y + 30 + k * lh}")
    thumb = os.path.join(job, "thumb.jpg")
    run(["ffmpeg", "-y", "-i", os.path.join(job, "images", f"scene_{ti:02d}.png"), "-vf", ",".join(vf),
         "-frames:v", "1", "-q:v", "3", thumb])

    result = {"ok": True, "youtube_video": outs["youtube"], "tiktok_video": outs["tiktok"], "thumbnail": thumb,
              "duration": round(dur(outs["youtube"]), 2), "tempo": round(tempo, 3), "scenes": len(scenes)}
    json.dump(result, open(os.path.join(job, "result.json"), "w"), ensure_ascii=False)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
