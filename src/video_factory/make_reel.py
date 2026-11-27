# -*- coding: utf-8 -*-
"""OpenClaw Video Factory — PhongBanAI-style fast-lane vertical reel creator (1080x1920 9:16).

Pipeline:
1. Validate script JSON (job_id, version, title, caption, scenes[]).
2. Synthesize Vietnamese voiceover via edge-tts (vi-VN-NamMinhNeural +5% default,
   or vi-VN-HoaiMyNeural) with pronunciation mapping (e.g. AI -> ây ai) and exact
   SentenceBoundary SRT cues. Scene durations automatically fit actual speech so
   voiceover is never truncated or out of sync.
3. Generate scene visuals in parallel:
   - "image_prompt": AI image via codex.anhlaptrinh.vn/v1/images/generations (cx/gpt-image-2, 1024x1536)
   - "pexels_query": HD portrait stock video via Pexels API (requires PEXELS_API_KEY in .env)
   - "image": local image file (.jpg/.jpeg/.png/.webp)
   Still images are encoded to smooth 1080x1920 30fps H.264 scene clips via ffmpeg.
4. Build clean HyperFrames HTML composition (single bottom subtitle pill, opening hook,
   BeVietnamPro typography, GSAP progress bar — never ffmpeg drawtext/subtitle burn-in).
5. Run HyperFrames lint -> validate -> render (--quality looks --fps 30 --no-browser-gpu --sdr).
6. Verify MP4 with ffprobe (1080x1920, audio present, duration match, full decode check).
7. Stage canonical MP4 into C:\\Users\\Giang\\openclaw\\media\\outbound\\ for Telegram delivery.

Usage:
  python make_reel.py --script path/to/script.json
"""
import argparse
import asyncio
import base64
import concurrent.futures
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OPENCLAW_DIR = ROOT.parent
OUTBOUND_DIR = OPENCLAW_DIR / "media" / "outbound"
CACHE_DIR = ROOT / ".cache"
PRONUNCIATION_FILE = ROOT / "config" / "pronunciation.json"

IMAGE_URL = "https://codex.anhlaptrinh.vn/v1/images/generations"
IMAGE_MODEL = "cx/gpt-image-2"
AI_CREDIT = "Ảnh minh họa tạo bằng AI"

ASPECT_PRESETS = {
    "9:16": {"width": 1080, "height": 1920, "img_size": "1024x1536", "pixabay_orient": "vertical", "pexels_orient": "portrait", "comp_desc": "vertical 9:16 composition"},
    "16:9": {"width": 1920, "height": 1080, "img_size": "1536x1024", "pixabay_orient": "horizontal", "pexels_orient": "landscape", "comp_desc": "horizontal 16:9 widescreen cinematic composition"},
    "1:1":  {"width": 1080, "height": 1080, "img_size": "1024x1024", "pixabay_orient": "all", "pexels_orient": "square", "comp_desc": "square 1:1 balanced composition"},
}

DEFAULT_VOICE = "vi-VN-NamMinhNeural"
DEFAULT_RATE = "+5%"
SCENE_PAD_S = 0.25


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_bin(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(f"Required binary not found on PATH: {name}")


def ffprobe_info(path: Path) -> dict:
    ffprobe = find_bin("ffprobe")
    res = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=60, check=True, stdin=subprocess.DEVNULL,
    )
    return json.loads(res.stdout)


def media_duration(path: Path) -> float:
    return float(ffprobe_info(path)["format"]["duration"])


def load_codex_api_key() -> str:
    key = os.environ.get("TOKEN_CODEX_API_KEY", "").strip()
    if key:
        return key
    secret_file = OPENCLAW_DIR / "member-provider.secret"
    if secret_file.is_file():
        key = secret_file.read_text(encoding="utf-8-sig").strip()
        if key:
            return key
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("TOKEN_CODEX_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("TOKEN_CODEX_API_KEY not found in env or member-provider.secret")


def load_pexels_api_key() -> str:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if key:
        return key
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("PEXELS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def load_pixabay_api_key() -> str:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if key:
        return key
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line.startswith("PIXABAY_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def load_pronunciation_rules():
    if not PRONUNCIATION_FILE.is_file():
        return []
    data = json.loads(PRONUNCIATION_FILE.read_text(encoding="utf-8-sig"))
    rules = sorted(data.get("rules", []), key=lambda r: -len(r["written"]))
    return [(r["written"], r["spoken"]) for r in rules]


def apply_pronunciation(text: str, rules):
    if not rules:
        return text, []
    pattern = re.compile("|".join(rf"(?<![\w.]){re.escape(w)}(?!\w)" for w, _ in rules))
    lookup = dict(rules)
    out, spans, last, pos = [], [], 0, 0
    for m in pattern.finditer(text):
        out.append(text[last:m.start()])
        pos += m.start() - last
        spoken = lookup[m.group(0)]
        spans.append((m.start(), m.end(), pos, pos + len(spoken)))
        out.append(spoken)
        pos += len(spoken)
        last = m.end()
    out.append(text[last:])
    return "".join(out), spans


def restore_display_text(original: str, spoken: str, spans, fragment: str, cursor: int = 0):
    if not spans:
        return fragment, cursor
    at = spoken.find(fragment, cursor)
    if at < 0:
        restored = fragment
        for o0, o1, s0, s1 in spans:
            restored = restored.replace(spoken[s0:s1], original[o0:o1], 1)
        return restored, cursor
    end = at + len(fragment)

    def to_orig(p: int, is_end: bool) -> int:
        delta = 0
        for o0, o1, s0, s1 in spans:
            if s0 <= p < s1 or (is_end and s0 < p <= s1):
                return o1 if is_end else o0
            if p >= s1:
                delta = o1 - s1
        return p + delta

    return original[to_orig(at, False):to_orig(end, True)], end


async def _synth_edge_once(text: str, voice: str, rate: str):
    import edge_tts

    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    audio_chunks = bytearray()
    cues = []
    async for chunk in comm.stream():
        ctype = chunk.get("type")
        if ctype == "audio":
            audio_chunks.extend(chunk["data"])
        elif ctype in ("SentenceBoundary", "WordBoundary"):
            offset_s = chunk["offset"] / 10_000_000.0
            dur_s = chunk["duration"] / 10_000_000.0
            cue_text = (chunk.get("text") or "").strip()
            if cue_text:
                cues.append((offset_s, offset_s + dur_s, cue_text))
    if not audio_chunks:
        raise RuntimeError("edge-tts returned empty audio")
    return bytes(audio_chunks), cues


def _estimate_sentence_cues(text: str, total_dur: float):
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s.strip()] or [text.strip()]
    weights = [max(1, len(s.split())) for s in sentences]
    total_w = sum(weights)
    cursor, cues = 0.0, []
    for idx, (sent, w) in enumerate(zip(sentences, weights)):
        end = total_dur if idx == len(sentences) - 1 else round(cursor + total_dur * w / total_w, 3)
        cues.append((round(cursor, 3), round(max(cursor + 0.1, end), 3), sent))
        cursor = end
    return cues


def _synth_gtts_fallback(spoken: str, dest_mp3: Path):
    from gtts import gTTS

    raw_mp3 = dest_mp3.with_suffix(".gtts_raw.mp3")
    gTTS(text=spoken, lang="vi", slow=False).save(str(raw_mp3))
    ffmpeg = find_bin("ffmpeg")
    # Speed up slightly (1.08x) and normalize to 24kHz mono 64k mp3 for crisp reel pacing
    subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", str(raw_mp3),
         "-af", "atempo=1.08", "-ar", "24000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", str(dest_mp3)],
        check=True, timeout=60, stdin=subprocess.DEVNULL,
    )
    raw_mp3.unlink(missing_ok=True)


def synth_scene_voice(text: str, voice: str, rate: str, rules, dest_mp3: Path, dest_srt: Path):
    spoken, spans = apply_pronunciation(text, rules)
    cache_key = sha256_bytes(json.dumps(["tts-v2", text, spoken, voice, rate], sort_keys=True).encode("utf-8"))
    c_mp3 = CACHE_DIR / "tts" / f"{cache_key}.mp3"
    c_json = CACHE_DIR / "tts" / f"{cache_key}.json"
    c_mp3.parent.mkdir(parents=True, exist_ok=True)

    if c_mp3.is_file() and c_json.is_file():
        meta = json.loads(c_json.read_text(encoding="utf-8"))
        shutil.copy2(c_mp3, dest_mp3)
        cues = [tuple(c) for c in meta["cues"]]
    else:
        audio_bytes, raw_cues, engine_used = None, None, "edge-tts"
        alt_voice = "vi-VN-HoaiMyNeural" if voice == "vi-VN-NamMinhNeural" else "vi-VN-NamMinhNeural"
        for try_voice in (voice, voice, alt_voice):
            try:
                audio_bytes, raw_cues = asyncio.run(_synth_edge_once(spoken, try_voice, rate))
                break
            except Exception:
                time.sleep(1.5)

        if audio_bytes is not None:
            c_mp3.write_bytes(audio_bytes)
            dur = media_duration(c_mp3)
            cues = []
            cursor = 0
            for a, b, frag in (raw_cues or []):
                shown, cursor = restore_display_text(text, spoken, spans, frag, cursor)
                cues.append((round(a, 3), round(min(b, dur), 3), shown))
            if not cues:
                cues = _estimate_sentence_cues(text, dur)
            for i in range(len(cues) - 1):
                a, b, t = cues[i]
                na = cues[i + 1][0]
                if b > na:
                    cues[i] = (a, max(a + 0.05, na), t)
        else:
            # Automatic fallback to gTTS (Vietnamese HTTPS — immune to Edge WebSocket drops)
            engine_used = "gtts"
            _synth_gtts_fallback(spoken, c_mp3)
            dur = media_duration(c_mp3)
            cues = _estimate_sentence_cues(text, dur)

        meta = {"duration": dur, "cues": cues, "voice": voice, "rate": rate, "engine": engine_used}
        c_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.copy2(c_mp3, dest_mp3)

    # Write SRT
    def fmt_srt(sec: float) -> str:
        ms = int(round(max(0.0, sec) * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    srt_blocks = [
        f"{idx}\n{fmt_srt(a)} --> {fmt_srt(b)}\n{t}"
        for idx, (a, b, t) in enumerate(cues, 1)
    ]
    dest_srt.write_text("\n\n".join(srt_blocks) + "\n", encoding="utf-8")
    return float(meta["duration"]), cues


def generate_ai_image(prompt: str, dest_png: Path, api_key: str, preset: dict) -> Path:
    img_size = preset["img_size"]
    style_suffix = (
        f" Photorealistic, natural light, real Vietnamese people where relevant, "
        f"documentary photo style, {preset['comp_desc']}, no text, no logo, no watermark."
    )
    cache_key = sha256_bytes(json.dumps(["img-v2", IMAGE_MODEL, img_size, prompt], sort_keys=True).encode("utf-8"))
    cached = CACHE_DIR / "images" / f"{cache_key}.png"
    cached.parent.mkdir(parents=True, exist_ok=True)
    if cached.is_file() and cached.stat().st_size > 10000:
        shutil.copy2(cached, dest_png)
        return dest_png

    body = json.dumps({
        "model": IMAGE_MODEL,
        "prompt": prompt + style_suffix,
        "size": img_size,
        "n": 1,
    }).encode("utf-8")

    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                IMAGE_URL,
                data=body,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            item = data["data"][0]
            if item.get("b64_json"):
                raw = base64.b64decode(item["b64_json"])
            else:
                with urllib.request.urlopen(item["url"], timeout=120) as img_resp:
                    raw = img_resp.read()
            if len(raw) < 10000:
                raise ValueError("Generated image too small")
            cached.write_bytes(raw)
            shutil.copy2(cached, dest_png)
            return dest_png
        except Exception as exc:
            last_err = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (400, 401, 403):
                break
            time.sleep(3 + 4 * attempt)
    raise RuntimeError(f"AI image generation failed: {last_err}")


def fetch_pixabay_clip(query: str, seconds: float, dest_mp4: Path, api_key: str, preset: dict) -> Path:
    """Fetch HD video from Pixabay Videos API; fall back to Pixabay photo -> Ken Burns clip."""
    if not api_key:
        raise RuntimeError("PIXABAY_API_KEY not set in video-factory/.env")
    w, h = preset["width"], preset["height"]
    q = urllib.parse.quote(query)
    # 1) Try Pixabay Videos API
    vid_url = f"https://pixabay.com/api/videos/?key={urllib.parse.quote(api_key)}&q={q}&per_page=10&safesearch=true"
    req = urllib.request.Request(vid_url, headers={"User-Agent": "OpenClawVideoFactory/1.0"})
    hits = []
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            hits = json.loads(resp.read().decode("utf-8")).get("hits") or []
    except Exception:
        hits = []

    chosen_url = ""
    if hits:
        long_hits = [x for x in hits if float(x.get("duration", 0)) >= seconds] or hits
        for item in long_hits:
            vids = item.get("videos") or {}
            for tier in ("large", "medium", "small"):
                u = (vids.get(tier) or {}).get("url")
                if u:
                    chosen_url = u
                    break
            if chosen_url:
                break

    if chosen_url:
        raw_mp4 = dest_mp4.with_suffix(".raw.mp4")
        req_dl = urllib.request.Request(chosen_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req_dl, timeout=120) as resp, raw_mp4.open("wb") as f:
            shutil.copyfileobj(resp, f)
        ffmpeg = find_bin("ffmpeg")
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=bicubic,crop={w}:{h},fps=30,format=yuv420p"
        subprocess.run(
            [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y", "-stream_loop", "-1",
             "-i", str(raw_mp4), "-t", f"{seconds + 0.5:.3f}", "-vf", vf,
             "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an", "-movflags", "+faststart", str(dest_mp4)],
            check=True, timeout=180, stdin=subprocess.DEVNULL,
        )
        raw_mp4.unlink(missing_ok=True)
        return dest_mp4

    # 2) Fallback: Pixabay Photos API -> smooth Ken Burns clip
    orient = preset["pixabay_orient"]
    img_url = f"https://pixabay.com/api/?key={urllib.parse.quote(api_key)}&q={q}&image_type=photo&orientation={orient}&per_page=10&safesearch=true"
    req_img = urllib.request.Request(img_url, headers={"User-Agent": "OpenClawVideoFactory/1.0"})
    with urllib.request.urlopen(req_img, timeout=45) as resp:
        img_hits = json.loads(resp.read().decode("utf-8")).get("hits") or []
    if not img_hits:
        raise RuntimeError(f"No Pixabay videos or photos found for query: {query}")
    photo_link = img_hits[0].get("largeImageURL") or img_hits[0].get("webformatURL")
    raw_img = dest_mp4.with_suffix(".jpg")
    req_p = urllib.request.Request(photo_link, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_p, timeout=60) as resp, raw_img.open("wb") as f:
        shutil.copyfileobj(resp, f)
    image_to_clip(raw_img, seconds, dest_mp4, preset)
    raw_img.unlink(missing_ok=True)
    return dest_mp4


def fetch_pexels_clip(query: str, seconds: float, dest_mp4: Path, api_key: str, preset: dict) -> Path:
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY not set in video-factory/.env")
    w, h = preset["width"], preset["height"]
    orient = preset["pexels_orient"]
    url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&orientation={orient}&per_page=10"
    req = urllib.request.Request(url, headers={"Authorization": api_key, "User-Agent": "OpenClawVideoFactory/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    videos = [v for v in data.get("videos", []) if float(v.get("duration", 0)) >= seconds] or data.get("videos", [])
    if not videos:
        raise RuntimeError(f"No Pexels videos found for query: {query}")
    video = videos[0]
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")]
    files.sort(key=lambda f: (f["width"] < w or f["height"] < h, abs(f["width"] * f["height"] - w * h)))
    chosen = files[0]
    raw_mp4 = dest_mp4.with_suffix(".raw.mp4")
    req_dl = urllib.request.Request(chosen["link"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_dl, timeout=120) as resp, raw_mp4.open("wb") as f:
        shutil.copyfileobj(resp, f)
    ffmpeg = find_bin("ffmpeg")
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=bicubic,crop={w}:{h},fps=30,format=yuv420p"
    subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y", "-stream_loop", "-1",
         "-i", str(raw_mp4), "-t", f"{seconds + 0.5:.3f}", "-vf", vf,
         "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an", "-movflags", "+faststart", str(dest_mp4)],
        check=True, timeout=180, stdin=subprocess.DEVNULL,
    )
    raw_mp4.unlink(missing_ok=True)
    return dest_mp4


def image_to_clip(src_img: Path, seconds: float, dest_mp4: Path, preset: dict) -> Path:
    ffmpeg = find_bin("ffmpeg")
    w, h = preset["width"], preset["height"]
    sw, sh = int(round(w * 1.12)), int(round(h * 1.12))
    frames = max(30, int(round((seconds + 0.4) * 30)))
    vf = (
        f"scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=bicubic,"
        f"crop={sw}:{sh},"
        f"zoompan=z='min(zoom+0.0005,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps=30,"
        "format=yuv420p"
    )
    cmd = [
        ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y",
        "-i", str(src_img), "-t", f"{seconds + 0.4:.3f}", "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-an", "-movflags", "+faststart",
        str(dest_mp4),
    ]
    subprocess.run(cmd, check=True, timeout=180, stdin=subprocess.DEVNULL)
    return dest_mp4


def prepare_local_video(src_vid: Path, seconds: float, dest_mp4: Path, preset: dict) -> Path:
    """Scale, crop, and loop/trim a customer-provided MP4/MOV clip to exact target dimensions."""
    ffmpeg = find_bin("ffmpeg")
    w, h = preset["width"], preset["height"]
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=bicubic,crop={w}:{h},fps=30,format=yuv420p"
    cmd = [
        ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y",
        "-stream_loop", "-1", "-i", str(src_vid),
        "-t", f"{seconds + 0.4:.3f}", "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an", "-movflags", "+faststart",
        str(dest_mp4),
    ]
    subprocess.run(cmd, check=True, timeout=180, stdin=subprocess.DEVNULL)
    return dest_mp4


def hyperframes_bin() -> list:
    hf_js = ROOT / "node_modules" / "hyperframes" / "dist" / "cli.js"
    if hf_js.is_file():
        return [find_bin("node"), str(hf_js)]
    hf_cmd = ROOT / "node_modules" / ".bin" / ("hyperframes.cmd" if os.name == "nt" else "hyperframes")
    if hf_cmd.is_file():
        return [str(hf_cmd)]
    return [find_bin("npx"), "--yes", "hyperframes@0.8.78"]


def build_reel(script_path: Path) -> dict:
    t0 = time.perf_counter()
    script = json.loads(script_path.read_text(encoding="utf-8-sig"))
    job_id = re.sub(r"[^a-z0-9-]+", "-", str(script.get("job_id") or f"reel-{int(time.time())}").lower()).strip("-")
    version = str(script.get("version") or "v1").strip()
    title = str(script.get("title") or job_id).strip()
    caption = str(script.get("caption") or title).strip()
    voice_name = str(script.get("voice") or DEFAULT_VOICE).strip()
    voice_rate = str(script.get("rate") or DEFAULT_RATE).strip()
    aspect = str(script.get("aspect_ratio") or "9:16").strip()
    if aspect not in ASPECT_PRESETS:
        aspect = "9:16"
    preset = ASPECT_PRESETS[aspect]
    w, h = preset["width"], preset["height"]
    scenes = script.get("scenes") or []
    if not scenes:
        raise ValueError("Script must contain a non-empty 'scenes' list")

    slug = f"{job_id}-{version}"
    if script.get("reuse_composition"):
        import sys
        from reuse_composition import render
        return render(sys.modules[__name__], script, slug)
    ws = ROOT / "workspaces" / slug
    out_dir = ROOT / "output" / slug
    if ws.exists():
        shutil.rmtree(ws)
    (ws / "input").mkdir(parents=True, exist_ok=True)
    (ws / "assets").mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    rules = load_pronunciation_rules()

    # Step 1: Launch AI image generation in parallel WITH TTS synthesis (cuts 30-40% total time!)
    needs_ai = any(
        str(s.get("image_prompt") or "").strip()
        and not str(s.get("image") or "").strip()
        and not str(s.get("video") or s.get("local_video") or "").strip()
        for s in scenes
    )
    codex_key = load_codex_api_key() if needs_ai else ""
    ai_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    ai_futs = {}
    if needs_ai:
        for i, sc in enumerate(scenes, 1):
            p = str(sc.get("image_prompt") or "").strip()
            if p and not str(sc.get("image") or "").strip() and not str(sc.get("video") or sc.get("local_video") or "").strip():
                ai_futs[i] = ai_pool.submit(generate_ai_image, p, ws / "input" / f"scene-{i}.png", codex_key, preset)

    # Synthesize TTS sequentially while AI images generate in background
    tts_results = {}
    for i, sc in enumerate(scenes, 1):
        vtext = str(sc.get("voice") or "").strip()
        if not vtext:
            raise ValueError(f"Scene {i} missing 'voice'")
        tts_results[i] = synth_scene_voice(
            vtext, voice_name, voice_rate, rules,
            ws / "input" / f"voice-{i}.mp3", ws / "input" / f"voice-{i}.srt"
        )

    # Wait for any in-flight AI images
    ai_ready = {i: fut.result() for i, fut in ai_futs.items()}
    ai_pool.shutdown(wait=False)

    # Compute exact timeline from measured speech durations
    cursor = 0.0
    timeline = []
    for i, sc in enumerate(scenes, 1):
        speech_dur, cues = tts_results[i]
        planned_dur = 0.0
        if "start" in sc and "end" in sc:
            planned_dur = max(0.0, float(sc["end"]) - float(sc["start"]))
        scene_dur = round(max(speech_dur + SCENE_PAD_S, planned_dur, 2.5), 3)
        timeline.append({
            "index": i,
            "scene": sc,
            "start": round(cursor, 3),
            "duration": scene_dur,
            "speech_duration": round(speech_dur, 3),
            "cues": cues,
        })
        cursor += scene_dur
    total_duration = round(cursor, 3)

    # Step 2: Encode / fetch scene visuals in parallel
    needs_stock = any(
        (str(s.get("pixabay_query") or "").strip() or str(s.get("pexels_query") or "").strip())
        and not str(s.get("image_prompt") or "").strip()
        and not str(s.get("image") or "").strip()
        and not str(s.get("video") or s.get("local_video") or "").strip()
        for s in scenes
    )
    pixabay_key = load_pixabay_api_key() if needs_stock else ""
    pexels_key = load_pexels_api_key() if needs_stock else ""

    def prep_visual(item):
        i = item["index"]
        sc = item["scene"]
        dur = item["duration"]
        dest_mp4 = ws / "input" / f"scene-{i}.mp4"
        if str(sc.get("video") or sc.get("local_video") or "").strip():
            src_v = Path(str(sc.get("video") or sc.get("local_video"))).expanduser().resolve()
            if not src_v.is_file():
                raise ValueError(f"Scene {i} local video not found: {src_v}")
            prepare_local_video(src_v, dur, dest_mp4, preset)
            return str(sc.get("image_source") or "")
        if str(sc.get("image") or "").strip():
            src = Path(sc["image"]).expanduser().resolve()
            if not src.is_file():
                raise ValueError(f"Scene {i} local image not found: {src}")
            image_to_clip(src, dur, dest_mp4, preset)
            return str(sc.get("image_source") or "")
        if str(sc.get("image_prompt") or "").strip():
            dest_png = ai_ready.get(i) or generate_ai_image(sc["image_prompt"].strip(), ws / "input" / f"scene-{i}.png", codex_key, preset)
            image_to_clip(dest_png, dur, dest_mp4, preset)
            return str(sc.get("image_source") or AI_CREDIT)
        if str(sc.get("pixabay_query") or "").strip():
            fetch_pixabay_clip(sc["pixabay_query"].strip(), dur, dest_mp4, pixabay_key, preset)
            return ""
        if str(sc.get("pexels_query") or "").strip():
            q = sc["pexels_query"].strip()
            if pexels_key:
                fetch_pexels_clip(q, dur, dest_mp4, pexels_key, preset)
            elif pixabay_key:
                fetch_pixabay_clip(q, dur, dest_mp4, pixabay_key, preset)
            else:
                raise RuntimeError("PIXABAY_API_KEY (or PEXELS_API_KEY) not set in video-factory/.env")
            return ""
        raise ValueError(f"Scene {i} requires one of: video, image, image_prompt, pixabay_query, or pexels_query")

    credits = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(prep_visual, item): item["index"] for item in timeline}
        for fut in concurrent.futures.as_completed(futs):
            credits[futs[fut]] = fut.result()

    # Step 3: Copy assets (fonts, gsap, styles, package.json) and generate index.html
    for src, dst_name in [
        (ROOT / "assets" / "fonts" / "BeVietnamPro-Regular.ttf", "regular.ttf"),
        (ROOT / "assets" / "fonts" / "BeVietnamPro-Bold.ttf", "bold.ttf"),
        (ROOT / "node_modules" / "gsap" / "dist" / "gsap.min.js", "gsap.min.js"),
    ]:
        if src.is_file():
            shutil.copy2(src, ws / "assets" / dst_name)
    css_tpl = (ROOT / "templates" / "fast-reel" / "styles.css").read_text(encoding="utf-8")
    css_rendered = css_tpl.replace("1080px", f"{w}px").replace("1920px", f"{h}px")
    if aspect == "16:9":
        css_rendered += "\n#hook{top:120px;left:180px;right:180px;font-size:56px}\n.subtitle{bottom:72px;max-width:1520px;font-size:34px}\n.scrim-top{height:280px}\n.scrim-bottom{height:300px}\n"
    elif aspect == "1:1":
        css_rendered += "\n#hook{top:110px;font-size:52px}\n.subtitle{bottom:70px;max-width:940px;font-size:32px}\n.scrim-top{height:260px}\n.scrim-bottom{height:280px}\n"
    (ws / "styles.css").write_text(css_rendered, encoding="utf-8")
    shutil.copy2(ROOT / "package.json", ws / "package.json")

    parts = []
    for item in timeline:
        i = item["index"]
        sc = item["scene"]
        start = item["start"]
        dur = item["duration"]
        speech_dur = item["speech_duration"]
        parts.append(
            f'<video id="video{i}" class="clip background" muted playsinline src="input/scene-{i}.mp4" '
            f'data-start="{start}" data-duration="{dur}" data-media-start="0" data-track-index="0" data-volume="0"></video>'
        )
        parts.append(
            f'<audio id="audio{i}" class="clip" src="input/voice-{i}.mp3" '
            f'data-start="{start}" data-duration="{speech_dur}" data-track-index="1"></audio>'
        )
        if i == 1:
            hook_text = str(sc.get("text") or title).strip()
            if hook_text:
                parts.append(
                    f'<h1 id="hook" class="clip" data-start="0" data-duration="{min(3.2, dur)}" '
                    f'data-track-index="3">{html.escape(hook_text)}</h1>'
                )
        credit = credits.get(i, "")
        if credit and sc.get("show_image_credit", False):
            parts.append(
                f'<div id="credit{i}" class="clip image-credit" data-start="{start}" data-duration="{dur}" '
                f'data-track-index="6">{html.escape("Nguồn: " + credit)}</div>'
            )
        for k, (a, b, ctext) in enumerate(item["cues"]):
            cdur = round(max(0.15, b - a), 3)
            cstart = round(start + a, 3)
            parts.append(
                f'<div id="sub{i}-{k}" class="clip subtitle" data-start="{cstart}" data-duration="{cdur}" '
                f'data-track-index="4">{html.escape(ctext)}</div>'
            )

    tpl = (ROOT / "templates" / "fast-reel" / "index.template.html").read_text(encoding="utf-8")
    rendered_html = (
        tpl.replace('width=1080, height=1920', f'width={w}, height={h}')
        .replace('data-width="1080" data-height="1920"', f'data-width="{w}" data-height="{h}"')
        .replace("__TITLE__", html.escape(title))
        .replace("__DURATION__", str(total_duration))
        .replace("__CLIPS__", "\n    ".join(parts))
    )
    (ws / "index.html").write_text(rendered_html, encoding="utf-8")

    # Step 4: Render via Fast Full HD Engine (default: Pillow 2x + FFmpeg, ~10-15s) or HyperFrames (multi-core)
    engine = str(script.get("engine") or "fast").strip().lower()
    final_mp4 = out_dir / "final.mp4"
    if engine == "hyperframes":
        hf = hyperframes_bin()
        workers = min(4, max(2, (os.cpu_count() or 4) // 2))
        r_val = subprocess.run(hf + ["validate"], cwd=str(ws), capture_output=True, text=True, timeout=180, stdin=subprocess.DEVNULL)
        if r_val.returncode != 0:
            raise RuntimeError(f"hyperframes validate failed: {(r_val.stderr or r_val.stdout)[-500:]}")
        r_render = subprocess.run(
            hf + ["render", ".", "--workers", str(workers), "--quality", "looks", "--fps", "30",
                  "--no-browser-gpu", "--sdr", "-o", str(final_mp4)],
            cwd=str(ws), capture_output=True, text=True, timeout=1800, stdin=subprocess.DEVNULL,
        )
        if r_render.returncode != 0 or not final_mp4.is_file():
            raise RuntimeError(f"hyperframes render failed: {(r_render.stderr or r_render.stdout)[-600:]}")
    else:
        from fast_renderer import render_fast_reel
        brand_logo = None
        brand_cfg_file = ROOT / "config" / "brand.json"
        if brand_cfg_file.is_file():
            try:
                bcfg = json.loads(brand_cfg_file.read_text(encoding="utf-8-sig"))
                if bcfg.get("enabled") and bcfg.get("logo_path") and Path(bcfg["logo_path"]).is_file():
                    brand_logo = Path(bcfg["logo_path"])
            except Exception:
                pass
        render_fast_reel(
            ffmpeg=find_bin("ffmpeg"),
            ws=ws,
            timeline=timeline,
            total_duration=total_duration,
            w=w,
            h=h,
            title=title,
            font_bold=ROOT / "assets" / "fonts" / "BeVietnamPro-Bold.ttf",
            final_mp4=final_mp4,
            logo_path=brand_logo,
        )

    # Step 5: Technical verification (ffprobe + full decode)
    probe = ffprobe_info(final_mp4)
    streams = probe.get("streams", [])
    vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
    astream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    actual_dur = float(probe["format"]["duration"])
    if (vstream.get("width"), vstream.get("height")) != (w, h):
        raise RuntimeError(f"Unexpected dimensions: {vstream.get('width')}x{vstream.get('height')} (expected {w}x{h})")
    if not astream:
        raise RuntimeError("Rendered MP4 is missing audio stream")
    if abs(actual_dur - total_duration) > 1.2:
        raise RuntimeError(f"Duration mismatch: actual={actual_dur:.2f}s expected={total_duration:.2f}s")

    ffmpeg = find_bin("ffmpeg")
    dec = subprocess.run(
        [ffmpeg, "-v", "error", "-xerror", "-i", str(final_mp4), "-f", "null", "-"],
        capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL,
    )
    if dec.returncode != 0:
        raise RuntimeError(f"Full decode check failed: {dec.stderr[-300:]}")

    # Step 6: Stage Telegram-ready copy in OpenClaw media/outbound (auto-optimize only if > 45 MB, below Telegram's 50 MB hard cap)
    OUTBOUND_DIR.mkdir(parents=True, exist_ok=True)
    outbound_mp4 = OUTBOUND_DIR / f"{slug}.mp4"
    if final_mp4.stat().st_size > 45 * 1024 * 1024:
        subprocess.run(
            [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", str(final_mp4),
             "-c:v", "libx264", "-preset", "medium", "-crf", "24",
             "-maxrate", "3500k", "-bufsize", "7000k", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(outbound_mp4)],
            check=True, timeout=300, stdin=subprocess.DEVNULL,
        )
    else:
        shutil.copy2(final_mp4, outbound_mp4)

    result = {
        "ok": True,
        "job_id": job_id,
        "version": version,
        "title": title,
        "caption": caption,
        "duration": round(actual_dur, 2),
        "width": vstream.get("width"),
        "height": vstream.get("height"),
        "size_bytes": final_mp4.stat().st_size,
        "sha256": sha256_file(final_mp4),
        "video": str(final_mp4),
        "outbound_video": str(outbound_mp4),
        "workspace": str(ws),
        "elapsed_seconds": round(time.perf_counter() - t0, 1),
    }
    (out_dir / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser(description="OpenClaw PhongBanAI-style vertical reel creator")
    ap.add_argument("--script", required=True, type=Path, help="Path to JSON script")
    args = ap.parse_args()
    try:
        res = build_reel(args.script.resolve())
        print(json.dumps(res, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
