"""The drama ad pipeline. Every step reads and writes plain files in projects/<name>/, so any step can be redone.

premise.json -> script.json -> characters/<Name>/{front,side,back}.png -> clips.json -> clips/NN.mp4 -> final.mp4
"""
import json
import re
import subprocess
import time
from pathlib import Path

from . import apimart

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
PROMPTS = Path(__file__).resolve().parent / "prompts"
VIEWS = {
    "front": None,
    "side": "Same exact person, same outfit, same light and backdrop, seen in strict side profile (facing left), full body.",
    "back": "Same exact person, same outfit, same light and backdrop, seen from directly behind, full body.",
}


# ---------- small helpers ----------

def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "ad"


def pdir(name):
    return PROJECTS / name


def read(name, file, default=None):
    p = pdir(name) / file
    return json.loads(p.read_text()) if p.exists() else default


def write(name, file, data):
    p = pdir(name) / file
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def logger(name):
    path = pdir(name) / "log.txt"

    def log(msg):
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line)
        with open(path, "a") as f:
            f.write(line + "\n")
    return log


def prompt_file(n):
    return (PROMPTS / n).read_text()


def upload_cached(name, path):
    """Upload a local image once per version of the file."""
    cache = read(name, "uploads.json", {})
    key = f"{Path(path).relative_to(pdir(name))}@{Path(path).stat().st_mtime_ns}"
    if key not in cache:
        cache[key] = apimart.upload(path)
        write(name, "uploads.json", cache)
    return cache[key]


def char_dir(name, char):
    return pdir(name) / "characters" / slug(char)


# ---------- steps ----------

def new_project(premise, product="", seconds=45, title=None):
    name = slug(title or premise)
    base = name
    i = 2
    while pdir(name).exists():
        name, i = f"{base}-{i}", i + 1
    write(name, "premise.json", {"premise": premise, "product": product, "seconds": int(seconds)})
    return name


def write_script(name, notes=""):
    """Premise -> beat-by-beat script (Claude)."""
    log = logger(name)
    p = read(name, "premise.json")
    user = f"Premise:\n{p['premise']}\n\nProduct being advertised:\n{p['product'] or '(none given, invent nothing; keep it a pure story hook)'}\n\nTarget length: {p['seconds']} seconds."
    old = read(name, "script.json")
    if old and notes:
        user += f"\n\nHere is the current script:\n{json.dumps(old, ensure_ascii=False)}\n\nRewrite it with these notes: {notes}"
    log("writing script")
    script = apimart.chat_json(prompt_file("writer.md"), user)
    write(name, "script.json", script)
    log(f"script ready: {len(script.get('beats', []))} beats, {len(script.get('characters', []))} characters")
    return script


def make_character(name, char):
    """Front, side and back reference images for one character (GPT Image 2). Side/back use the front as reference."""
    log = logger(name)
    look = next(c["look"] for c in read(name, "script.json")["characters"] if c["name"] == char)
    d = char_dir(name, char)
    d.mkdir(parents=True, exist_ok=True)
    base = prompt_file("character.md").replace("{look}", look)
    log(f"{char}: front")
    apimart.image(base, d / "front.png", log=log)
    front_url = upload_cached(name, d / "front.png")
    for view in ("side", "back"):
        log(f"{char}: {view}")
        apimart.image(f"{VIEWS[view]}\n\n{base}", d / f"{view}.png", refs=[front_url], log=log)


def make_characters(name, only=None):
    for c in read(name, "script.json")["characters"]:
        if only and c["name"] != only:
            continue
        if not only and (char_dir(name, c["name"]) / "back.png").exists():
            continue
        make_character(name, c["name"])


def direct(name, notes=""):
    """Script -> clips with exact lengths and second-by-second prompts (Claude as director)."""
    log = logger(name)
    p, script = read(name, "premise.json"), read(name, "script.json")
    user = (f"Target length: {p['seconds']} seconds.\nProduct: {p['product'] or '(none)'}\n\n"
            f"Script:\n{json.dumps(script, ensure_ascii=False, indent=1)}")
    if notes:
        user += f"\n\nCurrent shot list:\n{json.dumps(read(name, 'clips.json'), ensure_ascii=False)}\n\nRedo it with these notes: {notes}"
    log("directing")
    plan = apimart.chat_json(prompt_file("director.md"), user)
    for i, c in enumerate(plan["clips"], 1):
        c["n"] = i
        c["duration"] = max(4, min(15, int(round(float(c["duration"])))))
    write(name, "clips.json", plan)
    total = sum(c["duration"] for c in plan["clips"])
    log(f"shot list ready: {len(plan['clips'])} clips, {total}s")
    return plan


def seedance_prompt(name, clip):
    """Attach character cards (+ product) as @image refs and swap {Name} placeholders for them."""
    images, header, prompt = [], [], clip["prompt"]
    for char in clip.get("characters", []):
        d = char_dir(name, char)
        if not (d / "front.png").exists():
            raise RuntimeError(f"No character card for {char} yet")
        n = len(images) + 1
        images += [upload_cached(name, d / f"{v}.png") for v in ("front", "side", "back")]
        header.append(f"{char} is the person in @image{n} (front), @image{n + 1} (side) and @image{n + 2} (back); keep this exact face, hair, body and outfit.")
        prompt = prompt.replace("{" + char + "}", f"{char} (@image{n})")
    product = pdir(name) / "product.png"
    if (clip.get("uses_product") or "{Product}" in prompt) and product.exists():
        images.append(upload_cached(name, product))
        header.append(f"The product is exactly as shown in @image{len(images)}.")
        prompt = prompt.replace("{Product}", f"the product (@image{len(images)})")
    prompt = re.sub(r"\{([^}]+)\}", r"\1", prompt)  # any leftover placeholders become plain names
    rules = "Photorealistic, vertical 9:16, natural real people. No subtitles, no on-screen text, no background music."
    return "\n".join(header + ["", prompt, "", rules]), images


def make_clip(name, n, resolution="720p"):
    log = logger(name)
    plan = read(name, "clips.json")
    clip = next(c for c in plan["clips"] if c["n"] == n)
    prompt, images = seedance_prompt(name, clip)
    out = pdir(name) / "clips" / f"{n:02d}.mp4"
    out.parent.mkdir(exist_ok=True)
    log(f"clip {n}: {clip['duration']}s, {len(images)} reference images")
    (out.with_suffix(".prompt.txt")).write_text(prompt)
    data = apimart.video(prompt, out, clip["duration"], images=images, resolution=resolution, log=log)
    log(f"clip {n} done (cost {data.get('cost', '?')})")


def make_clips(name, resolution="720p"):
    for c in read(name, "clips.json")["clips"]:
        if not (pdir(name) / "clips" / f"{c['n']:02d}.mp4").exists():
            make_clip(name, c["n"], resolution)


def has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return bool(out.strip())


def join(name):
    """Glue the clips in order, nothing trimmed. 720x1280 @ 30fps."""
    log = logger(name)
    files = [pdir(name) / "clips" / f"{c['n']:02d}.mp4" for c in read(name, "clips.json")["clips"]]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        raise RuntimeError(f"Clips not made yet: {', '.join(missing)}")
    args, graph = [], ""
    for i, f in enumerate(files):
        args += ["-i", str(f)]
        graph += f"[{i}:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=30,setsar=1[v{i}];"
        if has_audio(f):
            graph += f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}];"
        else:
            graph += f"anullsrc=r=44100:cl=stereo,atrim=0:{clip_len(f):.3f}[a{i}];"
    graph += "".join(f"[v{i}][a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=1:a=1[v][a]"
    out = pdir(name) / "final.mp4"
    subprocess.run(["ffmpeg", "-y", *args, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(out)], check=True, capture_output=True)
    log(f"final video ready: {out.relative_to(ROOT)}")
    return out


def clip_len(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return float(out.strip() or 0)


def run_all(name, resolution="720p"):
    """Everything after the premise, skipping steps whose files already exist."""
    if not read(name, "script.json"):
        write_script(name)
    make_characters(name)
    if not read(name, "clips.json"):
        direct(name)
    make_clips(name, resolution)
    return join(name)
