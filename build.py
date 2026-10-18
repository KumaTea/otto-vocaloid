#!/usr/bin/env python3
"""coronal-otto pipeline. Usage: uv run build.py <stage> [options]. See PLAN.md."""
import argparse
import sys

from src import common as C

STAGES = ["login", "fetch", "align", "units", "transcribe", "notes", "stack", "score", "render", "mix", "deliver",
          "from-fl", "blog"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=STAGES + ["all"])
    ap.add_argument("--only", help="comma-separated source ids, e.g. yt,p1 (fetch)")
    ap.add_argument("--force", action="store_true", help="redo work whose outputs already exist")
    ap.add_argument("--file", help="from-fl: the WAV exported from FL Studio")
    args = ap.parse_args()
    cfg = C.load_config()

    if args.stage == "login":
        from src.s0_fetch import login
        login(cfg)
    elif args.stage == "fetch":
        from src.s0_fetch import fetch
        fetch(cfg, only=args.only.split(",") if args.only else None, force=args.force)
    elif args.stage == "align":
        from src.s1_align import run
        run(cfg)
    elif args.stage == "units":
        from src.s2_units import run
        run(cfg)
    elif args.stage == "transcribe":
        from src.s3_transcribe import run
        run(cfg)
    elif args.stage == "notes":
        from src.s3_notes import run
        run(cfg)
    elif args.stage == "stack":
        from src.s3_stack import run
        run(cfg)
    elif args.stage == "score":
        from src.s4_score import run
        run(cfg, force=args.force)
    elif args.stage == "render":
        from src.s5_render import run
        run(cfg)
    elif args.stage == "mix":
        from src.s6_mix import run
        run(cfg)
    elif args.stage == "deliver":
        from src.s7_deliver import run
        run(cfg)
    elif args.stage == "blog":
        from src.blog import run
        run(cfg)
    elif args.stage == "from-fl":
        if not args.file:
            sys.exit("from-fl needs --file <the WAV exported from FL Studio>")
        from src.s7_deliver import from_fl
        from_fl(cfg, args.file)
    else:
        sys.exit(f"stage '{args.stage}' is not implemented yet")


if __name__ == "__main__":
    main()
