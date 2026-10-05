"""ffmpeg helpers: find the hook/showcase cut, extract the hook, join the final video."""
import json
import re
import subprocess
from pathlib import Path

W, H, FPS = 1080, 1920, 30


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def has_audio(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return bool(out.strip())


def find_cut(path, threshold=0.3, min_t=0.8, max_t=8.0):
    """Return the time (s) of the first hard scene change after min_t, or None."""
    res = subprocess.run(
        ["ffmpeg", "-hide_banner", "-t", str(max_t), "-i", str(path),
         "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", res.stderr)]
    return next((t for t in times if t >= min_t), None)


def extract_hook(src, cut, out):
    """Hook as 720x1280 silent mp4, the format Seedance accepts as a reference video."""
    run(["ffmpeg", "-y", "-i", str(src), "-t", f"{cut:.3f}", "-an",
         "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1",
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(out)])


def extract_frame(src, t, out):
    run(["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", str(out)])


def join(new_hook, src, cut, out):
    """New hook (video only) + original hook audio, then the original showcase. 1080x1920 @ 30fps."""
    norm = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
    if has_audio(src):
        audio = (f"[1:a]atrim=0:{cut:.3f},asetpts=PTS-STARTPTS[a0];"
                 f"[1:a]atrim=start={cut:.3f},asetpts=PTS-STARTPTS[a1];")
    else:
        total = duration(src)
        audio = (f"anullsrc=r=44100:cl=stereo,atrim=0:{cut:.3f}[a0];"
                 f"anullsrc=r=44100:cl=stereo,atrim=0:{total - cut:.3f}[a1];")
    graph = (
        # Seedance output can be a bit shorter than the input: pad with the last frame, then trim to the cut.
        f"[0:v]{norm},tpad=stop_mode=clone:stop_duration=2,trim=duration={cut:.3f},setpts=PTS-STARTPTS[v0];"
        f"[1:v]trim=start={cut:.3f},setpts=PTS-STARTPTS,{norm}[v1];"
        + audio
        + "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )
    run(["ffmpeg", "-y", "-i", str(new_hook), "-i", str(src), "-filter_complex", graph,
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
