"""Command line entry point: `aimuse spike | generate | analyze | presets | prompt`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .analysis import analyze, decode
from .engines import FakeEngine, LyriaEngine, MusicEngine
from .models import Intent
from .pipeline import Budget, BudgetExceeded, generate_track, rank, write_normalized, write_recipe
from .presets import list_presets, load_style
from .prompt import compile_prompt
from .spike import ARMS, run_spike

HARD_COST_LIMIT_USD = 20.0


def _engine(args) -> MusicEngine:
    if args.engine == "fake":
        return FakeEngine()
    return LyriaEngine(
        api_key=os.environ.get("GEMINI_API_KEY", ""), model=args.model, output_format=args.format
    )


def _check_cost(value: float) -> float:
    if value < 0 or value > HARD_COST_LIMIT_USD:
        sys.exit(f"--max-cost must be between 0 and {HARD_COST_LIMIT_USD}")
    return value


def _add_engine_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--engine", choices=["lyria", "fake"], default="lyria")
    p.add_argument("--model", default="lyria-3.5")
    p.add_argument("--format", choices=["mp3", "wav"], default="mp3")
    p.add_argument("--max-cost", type=float, default=1.0, help="hard spending cap in USD")
    p.add_argument("--normalize", action="store_true", help="write -14 LUFS FLAC of chosen tracks")
    p.add_argument("--out", type=Path, default=Path("out"))


def cmd_spike(args) -> int:
    report = run_spike(
        _engine(args),
        load_style(args.preset),
        args.out,
        tracks=args.tracks,
        candidates=args.candidates,
        arms=[a.strip() for a in args.arms.split(",") if a.strip()],
        max_cost_usd=_check_cost(args.max_cost),
        normalize=args.normalize,
    )
    print((args.out / "report.md").read_text())
    with_audio = sum(s.tracks_with_audio for s in report.summaries)
    return 0 if with_audio > 0 else 1


def cmd_generate(args) -> int:
    style = load_style(args.preset)
    intent = Intent(
        label=args.label, text=args.text, theme=args.theme, mood=args.mood, energy=args.energy
    )
    engine = _engine(args)
    budget = Budget(_check_cost(args.max_cost))
    try:
        track = generate_track(
            engine,
            style,
            intent,
            name=args.label,
            arm="generate",
            out_dir=args.out,
            budget=budget,
            candidates=args.candidates,
            use_anchor_image=args.anchor_image,
        )
    except BudgetExceeded as e:
        sys.exit(str(e))
    rank([track])
    if args.normalize:
        write_normalized(track, args.out)
    path = write_recipe(track, style, args.out)
    print(f"recipe: {path}  (spent ${budget.spent_usd:.2f})")
    return 0 if track.chosen is not None else 1


def cmd_analyze(args) -> int:
    for f in args.files:
        a = analyze(*decode(Path(f).read_bytes()))
        print(json.dumps({"file": f, **a.model_dump(exclude={"embedding"})}, indent=2))
    return 0


def cmd_prompt(args) -> int:
    style = load_style(args.preset)
    for intent in style.example_intents or [Intent()]:
        p = compile_prompt(style, intent, use_anchor_image=args.anchor_image)
        print(f"--- {intent.label or 'default'} ({len(p.images)} image)\n{p.text}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aimuse")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("spike", help="run the consistency experiment for one station")
    p.add_argument("--preset", default="rainy-morning-indie")
    p.add_argument("--tracks", type=int, default=4)
    p.add_argument("--candidates", type=int, default=1)
    p.add_argument("--arms", default=",".join(ARMS), help="comma list of: text,image")
    _add_engine_args(p)
    p.set_defaults(func=cmd_spike)

    p = sub.add_parser("generate", help="generate one track")
    p.add_argument("--preset", default="rainy-morning-indie")
    p.add_argument("--label", default="track")
    p.add_argument("--text")
    p.add_argument("--theme")
    p.add_argument("--mood")
    p.add_argument("--energy", type=float)
    p.add_argument("--candidates", type=int, default=1)
    p.add_argument("--anchor-image", action="store_true")
    _add_engine_args(p)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("analyze", help="analyse audio files")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("prompt", help="show compiled prompts for a preset (no API calls)")
    p.add_argument("--preset", default="rainy-morning-indie")
    p.add_argument("--anchor-image", action="store_true")
    p.set_defaults(func=cmd_prompt)

    p = sub.add_parser("presets", help="list built-in stations")
    p.set_defaults(func=lambda a: print("\n".join(list_presets())) or 0)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
