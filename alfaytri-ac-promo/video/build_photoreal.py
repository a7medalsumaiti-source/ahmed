#!/usr/bin/env python3
"""Photorealistic version of the Alfaytri promo, generated with Google Vertex AI (Veo) and
assembled with the brand captions, end card, colour grade and music/SFX bed.

Steps (each is resumable; finished clips are cached in video/clips/):
  1. generate  - one Veo clip per storyboard shot (prompts read from STORYBOARD.md section 5)
  2. assemble  - trim each clip to its storyboard slot, grade, add captions + end card + audio

Usage:
  python3 build_photoreal.py generate [--only 1A,3E] [--model veo-3.0-fast-generate-001]
  python3 build_photoreal.py assemble
  python3 build_photoreal.py all

Configuration (environment variables):
  GOOGLE_CLOUD_PROJECT            project with the Vertex AI API enabled and Veo access (required)
  GOOGLE_CLOUD_LOCATION           default us-central1
  GOOGLE_APPLICATION_CREDENTIALS  path to a service-account JSON (role: Vertex AI User), or
  GCP_SA_KEY_JSON                 the service-account JSON itself; otherwise falls back to
                                  `gcloud auth print-access-token`
  VEO_MODEL                       default veo-3.0-generate-001

Optional keyframes: put video/keyframes/<shot>.png (e.g. 1A.png) to drive that shot as
image-to-video, which keeps the people and the room more consistent between clips.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CLIPS = HERE / "clips"
KEYFRAMES = HERE / "keyframes"
OUT = ROOT / "exports"
FINAL = OUT / "alfaytri_ac_promo_30s_photoreal.mp4"
W, H, FPS = 1080, 1920, 30

# storyboard slots (same order and timings as the animated version)
SHOT_IDS = ["1A", "1B", "1C", "1D", "2A", "2B", "2C",
            "3A", "3B", "3C", "3D", "3E", "3F", "3G", "3H", "4A", "4B", "4C"]
SLOTS = [(0, 2), (2, 3.5), (3.5, 5.5), (5.5, 7), (7, 8.5), (8.5, 10), (10, 11),
         (11, 12.5), (12.5, 13.5), (13.5, 14.5), (14.5, 16), (16, 18), (18, 19), (19, 20.5), (20.5, 23),
         (23, 24.5), (24.5, 26), (26, 27)]
CAPTION_TIMES = {  # overlay file -> (start, end), matching animatic/build_branded.py
    "s1_warm_air": (0.8, 7.0), "s2_call": (7.3, 11.0), "s3_1_inspection": (11.5, 23.0),
    "s3_2_maintenance": (16.5, 23.0), "s4_comfort": (23.3, 27.0),
}


# ---------- prompts from the storyboard ----------

def load_prompts():
    md = (ROOT / "STORYBOARD.md").read_text(encoding="utf-8")
    bible = {}
    for key, name in (("ROOM", "ROOM"), ("AC UNIT", "AC UNIT"), ("RESIDENT", "RESIDENT"),
                      ("TECHNICIAN", "TECHNICIAN"), ("UNIFORM", "UNIFORM")):
        m = re.search(rf"^\*\*{re.escape(name)}\*\* — (.+)$", md, re.M)
        bible[key] = m.group(1).strip().rstrip(".")
    style = re.search(r"\*\*Style suffix.*?\n> (.+)", md).group(1).strip()
    negative = re.search(r"\*\*Negative prompt.*?\n> (.+)", md).group(1).strip()
    short = {"ROOM": "the living room", "AC UNIT": "the split AC unit", "RESIDENT": "the man",
             "TECHNICIAN": "the technician", "UNIFORM": "his uniform"}
    label = {"ROOM": "Setting", "AC UNIT": "AC unit", "RESIDENT": "The man", "TECHNICIAN": "The technician",
             "UNIFORM": "Technician's uniform"}
    prompts = {}
    for sid, body in re.findall(r"^\*\*([1-4][A-H])\*\* — \*(.+?)\*", md, re.M):
        # continuity descriptions first (only the ones this shot uses), then the action in plain words
        used = [k for k in bible if "{" + k + "}" in body]
        if "TECHNICIAN" in used and "UNIFORM" not in used:
            used.append("UNIFORM")
        setup = " ".join(f"{label[k]}: {bible[k]}." for k in used)
        for k in bible:
            body = body.replace("{" + k + "}", short[k])
        body = re.sub(r"(^|[.!?]\s+)the ", lambda m: m.group(1) + "The ", body)
        prompts[sid] = f"{setup} Shot: {body} {style}".strip()
    missing = set(SHOT_IDS) - set(prompts)
    if missing:
        raise SystemExit(f"STORYBOARD.md is missing prompts for {sorted(missing)}")
    return prompts, negative


# ---------- Vertex AI auth + calls ----------

def access_token():
    sa_json = os.environ.get("GCP_SA_KEY_JSON")
    sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if sa_json or sa_path:
        from google.oauth2 import service_account  # pip install google-auth requests
        import google.auth.transport.requests
        info = json.loads(sa_json) if sa_json else json.loads(Path(sa_path).read_text())
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())
        return creds.token
    return subprocess.run(["gcloud", "auth", "print-access-token"], check=True,
                          capture_output=True, text=True).stdout.strip()


def api(url, body, token):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Vertex AI error {e.code}: {e.read().decode()[:600]}")


def generate(only=None, model=None):
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("CLOUDSDK_CORE_PROJECT")
    if not project:
        raise SystemExit("Set GOOGLE_CLOUD_PROJECT to the Google Cloud project that has Vertex AI / Veo enabled.")
    loc = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    model = model or os.environ.get("VEO_MODEL", "veo-3.0-generate-001")
    base = f"https://{loc}-aiplatform.googleapis.com/v1/projects/{project}/locations/{loc}/publishers/google/models/{model}"
    prompts, negative = load_prompts()
    CLIPS.mkdir(exist_ok=True)
    token, token_t = access_token(), time.time()
    todo = [s for s in SHOT_IDS if (not only or s in only) and not (CLIPS / f"{s}.mp4").exists()]
    pending = {}
    for sid in todo:
        slot = dict(zip(SHOT_IDS, SLOTS))[sid]
        dur = 4 if slot[1] - slot[0] <= 2 else 6  # Veo clip lengths are 4, 6 or 8 s; trimmed later
        inst = {"prompt": prompts[sid]}
        kf = KEYFRAMES / f"{sid}.png"
        if kf.exists():
            inst["image"] = {"bytesBase64Encoded": base64.b64encode(kf.read_bytes()).decode(), "mimeType": "image/png"}
        body = {"instances": [inst], "parameters": {
            "aspectRatio": "9:16", "durationSeconds": dur, "sampleCount": 1, "negativePrompt": negative,
            "personGeneration": "allow_adult", "generateAudio": False, "resolution": "1080p"}}
        op = api(f"{base}:predictLongRunning", body, token)
        pending[sid] = op["name"]
        print(f"  {sid}: submitted ({dur}s{' + keyframe' if kf.exists() else ''})", flush=True)
    while pending:
        time.sleep(15)
        if time.time() - token_t > 2700:
            token, token_t = access_token(), time.time()
        for sid, name in list(pending.items()):
            op = api(f"{base}:fetchPredictOperation", {"operationName": name}, token)
            if not op.get("done"):
                continue
            del pending[sid]
            if "error" in op:
                print(f"  {sid}: FAILED {op['error'].get('message', op['error'])}", flush=True)
                continue
            vids = op.get("response", {}).get("videos", [])
            if not vids or "bytesBase64Encoded" not in vids[0]:
                print(f"  {sid}: no video returned (it may have been filtered); response keys: "
                      f"{list(op.get('response', {}))}", flush=True)
                continue
            (CLIPS / f"{sid}.mp4").write_bytes(base64.b64decode(vids[0]["bytesBase64Encoded"]))
            print(f"  {sid}: saved", flush=True)
    missing = [s for s in SHOT_IDS if not (CLIPS / f"{s}.mp4").exists()]
    print("All clips ready." if not missing else f"Still missing: {', '.join(missing)} (re-run generate)")


# ---------- assembly ----------

def grade_filter(start):
    if start < 11:  # warm, hazy
        return "colorbalance=rs=0.08:gs=0.02:bs=-0.08:rm=0.06:bm=-0.06,eq=saturation=1.05"
    if start >= 23:  # fresh, cool
        return "colorbalance=rs=-0.05:bs=0.07:rm=-0.04:bm=0.06,eq=brightness=0.02:saturation=0.98"
    return "eq=saturation=1.02"


def assemble():
    missing = [s for s in SHOT_IDS if not (CLIPS / f"{s}.mp4").exists()]
    if missing:
        raise SystemExit(f"Missing clips: {', '.join(missing)}. Run `generate` first.")
    work = HERE / "_work"
    work.mkdir(exist_ok=True)
    parts = []
    for sid, (a, b) in zip(SHOT_IDS, SLOTS):
        part = work / f"{sid}.mp4"
        # take the clip from 0.5 s in (Veo openings can be static), fill 9:16, grade, fixed fps
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
              f"{grade_filter(a)},format=yuv420p")
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "0.5", "-i", str(CLIPS / f"{sid}.mp4"),
                        "-t", f"{b - a:.3f}", "-an", "-vf", vf, "-c:v", "libx264", "-crf", "17", "-preset", "medium",
                        str(part)], check=True)
        parts.append(part)
    # end card from the brand renderer
    sys.path.insert(0, str(ROOT / "animatic"))
    import build_branded as bb
    if not (OUT / "end_card.mp4").exists():
        bb.main()
    parts.append(OUT / "end_card.mp4")
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    body = work / "body.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-an", "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-crf", "17", str(body)], check=True)
    # captions + music/SFX bed (shared with the animated version)
    sys.path.insert(0, str(HERE))
    import build_video as bv
    wav = work / "audio.wav"
    bv.build_audio(wav)
    inputs, chain, last = [], [], "[0:v]"
    for i, (name, (a, b)) in enumerate(CAPTION_TIMES.items(), start=1):
        inputs += ["-loop", "1", "-i", str(OUT / "overlays" / f"{name}.png")]
        nxt = f"[v{i}]"
        chain.append(f"[{i}:v]format=rgba,fade=t=in:st={a}:d=0.3:alpha=1,fade=t=out:st={b - 0.2}:d=0.2:alpha=1[o{i}];"
                     f"{last}[o{i}]overlay=0:0:shortest=1{nxt}")
        last = nxt
    n_audio = len(CAPTION_TIMES) + 1
    OUT.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(body), *inputs, "-i", str(wav),
                    "-filter_complex", ";".join(chain), "-map", last, "-map", f"{n_audio}:a",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-crf", "19", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-t", "30",
                    "-movflags", "+faststart", str(FINAL)], check=True)
    print("Wrote", FINAL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["generate", "assemble", "all", "prompts"])
    ap.add_argument("--only", help="comma-separated shot ids, e.g. 1A,3E")
    ap.add_argument("--model")
    a = ap.parse_args()
    if a.step == "prompts":
        prompts, negative = load_prompts()
        for sid in SHOT_IDS:
            print(f"[{sid}] {prompts[sid]}\n")
        print("NEGATIVE:", negative)
        return
    if a.step in ("generate", "all"):
        generate(set(a.only.split(",")) if a.only else None, a.model)
    if a.step in ("assemble", "all"):
        assemble()


if __name__ == "__main__":
    main()
