"""
python -m ugc fetch --profile someuser --hashtag sometrend --limit 10
python -m ugc cut inputs/video.mp4                 # just show where the hook ends
python -m ugc run inputs/*.mp4 [--cut 3.2] [--headline "..."] [--reuse]
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import video

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "headlines" / "examples.txt"
WINNERS = ROOT / "headlines" / "winners.txt"


def cmd_fetch(a):
    from .fetch import fetch
    saved = fetch(a.out, a.profile, a.hashtag, a.limit)
    print(f"{len(saved)} new videos in {a.out}")


def cmd_cut(a):
    for src in a.videos:
        t = video.find_cut(src, a.threshold)
        print(f"{src}: {'no cut found' if t is None else f'{t:.2f}s'}")


def process(src, a):
    from . import ai, seedance

    src = Path(src)
    out = Path(a.out) / src.stem
    out.mkdir(parents=True, exist_ok=True)

    cut = a.cut or video.find_cut(src, a.threshold)
    if cut is None:
        raise RuntimeError("no hook/showcase cut found; check with `python -m ugc cut` and pass --cut SECONDS")
    print(f"  cut at {cut:.2f}s")

    hook = out / "hook_720.mp4"
    frame = out / "hook_frame.png"
    video.extract_hook(src, cut, hook)
    video.extract_frame(src, min(0.5, cut / 2), frame)

    old, new = ai.headline(frame, EXAMPLES, WINNERS, reuse=a.reuse)
    if a.headline:
        new = a.headline
    print(f"  headline: {old!r} -> {new!r}")

    avatar = out / "avatar.png"
    person = ai.make_avatar(frame, avatar)
    print(f"  avatar: {person}")

    prompt = seedance.build_prompt(new, old)
    new_hook = out / "hook_new.mp4"
    task = seedance.edit(hook, avatar, prompt, new_hook, resolution=a.resolution)

    final = out / "final.mp4"
    video.join(new_hook, src, cut, final)
    (out / "info.json").write_text(json.dumps({
        "source": str(src), "cut": cut, "old_headline": old, "new_headline": new,
        "avatar": person, "seedance": task, "prompt": prompt,
    }, indent=2))
    print(f"  done: {final}")


def cmd_run(a):
    failed = []
    for src in a.videos:
        print(f"== {src}")
        try:
            process(src, a)
        except Exception as e:  # keep going with the rest of the batch
            print(f"  FAILED: {e}", file=sys.stderr)
            failed.append(src)
    if failed:
        print(f"{len(failed)} failed: {', '.join(map(str, failed))}", file=sys.stderr)
        sys.exit(1)


def main():
    load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser(prog="ugc")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="download videos from TikTok")
    f.add_argument("--profile", action="append", default=[])
    f.add_argument("--hashtag", action="append", default=[])
    f.add_argument("--limit", type=int, default=10, help="videos per profile/hashtag")
    f.add_argument("--out", default="inputs")
    f.set_defaults(fn=cmd_fetch)

    c = sub.add_parser("cut", help="detect where the hook ends")
    c.add_argument("videos", nargs="+")
    c.add_argument("--threshold", type=float, default=0.3)
    c.set_defaults(fn=cmd_cut)

    r = sub.add_parser("run", help="make new versions of videos")
    r.add_argument("videos", nargs="+")
    r.add_argument("--cut", type=float, help="hook end in seconds (skips detection)")
    r.add_argument("--threshold", type=float, default=0.3)
    r.add_argument("--headline", help="use this headline instead of generating one")
    r.add_argument("--reuse", action="store_true", help="pick a headline from headlines/winners.txt")
    r.add_argument("--resolution", default="720p", choices=["480p", "720p", "1080p"])
    r.add_argument("--out", default="outputs")
    r.set_defaults(fn=cmd_run)

    a = p.parse_args()
    if a.cmd == "fetch" and not (a.profile or a.hashtag):
        p.error("give at least one --profile or --hashtag")
    a.fn(a)


if __name__ == "__main__":
    main()
