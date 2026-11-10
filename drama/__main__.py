"""python -m drama            -> opens the dashboard
python -m drama make "premise" [--product "..."] [--seconds 45]   -> whole ad in one go, no clicking"""
import argparse

from dotenv import load_dotenv

from . import pipeline as P

load_dotenv(P.ROOT / ".env")


def main():
    ap = argparse.ArgumentParser(prog="drama")
    sub = ap.add_subparsers(dest="cmd")
    mk = sub.add_parser("make", help="premise -> finished video")
    mk.add_argument("premise")
    mk.add_argument("--product", default="")
    mk.add_argument("--seconds", type=int, default=45)
    mk.add_argument("--resolution", default="720p", choices=["480p", "720p", "1080p"])
    a = ap.parse_args()
    if a.cmd == "make":
        name = P.new_project(a.premise, a.product, a.seconds)
        print(P.run_all(name, a.resolution))
    else:
        from .web import main as web
        web()


if __name__ == "__main__":
    main()
