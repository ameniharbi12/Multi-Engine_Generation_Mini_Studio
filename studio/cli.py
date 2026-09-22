"""Command line interface. The only place that builds objects and prints."""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from studio.errors import StudioError
from studio.journal import GenerationRecord, Journal
from studio.models import Brief, RunConfig
from studio.prompts import PromptOptimizer, RuleBasedOptimizer
from studio.registry import Registry
from studio.replay import replay_generation
from studio.runner import plan_run, run_brief
from studio.sheet import export_sheet
from studio.store import ArtifactStore


@dataclass
class App:
    """Everything the commands need, built once and passed in (no globals)."""
    registry: Registry
    optimizer: PromptOptimizer
    store: ArtifactStore
    journal: Journal


def build_app(db: str, out: str) -> App:
    return App(Registry().discover(), RuleBasedOptimizer(), ArtifactStore(out), Journal(db))


def default_author() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def parse_params(items: list[str] | None) -> dict[str, dict]:
    """--param engine.name=value  ->  {"engine": {"name": value}}"""
    overrides: dict[str, dict] = {}
    for item in items or []:
        key, sep, raw = item.partition("=")
        engine, dot, name = key.partition(".")
        if not (sep and dot and engine and name):
            raise ValueError(f"--param expects engine.name=value, got '{item}'")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        overrides.setdefault(engine, {})[name] = value
    return overrides


def _print_records(records: list[GenerationRecord]) -> None:
    print(f"{'id':>4}  {'engine':<10} {'seed':>4}  {'status':<6} {'kept':<4} {'sha256':<12} path or error")
    for r in records:
        detail = r.output_path if r.status == "ok" else r.error
        sha = (r.output_sha256 or "-")[:12]
        print(f"{r.id:>4}  {r.engine:<10} {r.seed:>4}  {r.status:<6} {'yes' if r.kept else '':<4} {sha:<12} {detail}")


# ----- commands ---------------------------------------------------------------------

def cmd_run(args: argparse.Namespace, app: App) -> int:
    brief = Brief.from_dict(json.loads(Path(args.brief).read_text(encoding="utf-8")))
    engines = tuple(e.strip() for e in args.engines.split(",")) if args.engines else tuple(app.registry.names())
    seeds = tuple(range(args.base_seed, args.base_seed + args.seeds))
    config = RunConfig(engines, seeds, args.author, parse_params(args.param))

    if args.dry_run:
        for job in plan_run(brief, config, app.registry, app.optimizer):
            print(f"[{job.adapter.name}] seed={job.request.seed} params={job.request.params}")
            print(f"    {job.request.prompt}")
        return 0

    result = run_brief(brief, config, registry=app.registry, optimizer=app.optimizer,
                       store=app.store, journal=app.journal)
    print(f"run {result.run_id}: {result.ok_count} ok, {result.error_count} failed")
    _print_records(list(result.records))
    if not args.no_sheet:
        print(f"contact sheet: {export_sheet(result.run_id, journal=app.journal, store=app.store)}")
    return 0 if result.error_count == 0 else 1


def cmd_replay(args: argparse.Namespace, app: App) -> int:
    result = replay_generation(args.generation_id, registry=app.registry, store=app.store,
                               journal=app.journal, author=args.author)
    print(f"generation {result.generation_id} ({result.engine}): "
          f"{'IDENTICAL' if result.identical else 'DIFFERENT'}")
    print(f"  stored sha256: {result.stored_sha256}")
    print(f"  replay sha256: {result.new_sha256}")
    print(f"  replay image:  {result.replay_path}")
    for note in result.notes:
        print(f"  note: {note}")
    return 0 if result.identical else 1


def cmd_sheet(args: argparse.Namespace, app: App) -> int:
    print(export_sheet(args.run_id, journal=app.journal, store=app.store))
    return 0


def cmd_list(args: argparse.Namespace, app: App) -> int:
    if args.run:
        app.journal.get_run(args.run)
        _print_records(app.journal.list_generations(args.run))
        return 0
    for run in app.journal.list_runs():
        print(f"{run.run_id}  {run.created_at}  {run.author:<12} "
              f"{app.journal.count_generations(run.run_id)} generations  {run.brief['scene']}")
    return 0


def cmd_keep(args: argparse.Namespace, app: App) -> int:
    rec = app.journal.mark_kept(args.generation_id, kept=not args.undo)
    print(f"generation {rec.id}: {'kept' if rec.kept else 'not kept'}")
    return 0


def cmd_engines(args: argparse.Namespace, app: App) -> int:
    for name in app.registry.names():
        adapter = app.registry.get(name)
        print(f"{name:<10} version {adapter.version:<14} prompt style {adapter.profile.style}, "
              f"{adapter.profile.min_chars} to {adapter.profile.max_chars} chars, "
              f"params {dict(adapter.default_params)}")
    return 0


# ----- wiring ------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studio", description="Multi engine generation mini studio")
    parser.add_argument("--db", default="journal.db", help="journal database (default journal.db)")
    parser.add_argument("--out", default="outputs", help="output folder (default outputs)")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a brief on several engines")
    run.add_argument("brief", help="path to a brief JSON file")
    run.add_argument("--engines", help="comma separated engine names (default: all)")
    run.add_argument("--seeds", type=int, default=2, help="number of seeds per engine (default 2)")
    run.add_argument("--base-seed", type=int, default=0, help="first seed (default 0)")
    run.add_argument("--author", default=default_author())
    run.add_argument("--param", action="append", help="engine.name=value, repeatable")
    run.add_argument("--dry-run", action="store_true", help="show the plan, generate nothing")
    run.add_argument("--no-sheet", action="store_true", help="skip the contact sheet")
    run.set_defaults(handler=cmd_run)

    replay = sub.add_parser("replay", help="replay a past generation and verify it")
    replay.add_argument("generation_id", type=int)
    replay.add_argument("--author", default=default_author())
    replay.set_defaults(handler=cmd_replay)

    sheet = sub.add_parser("sheet", help="export the contact sheet of a run")
    sheet.add_argument("run_id")
    sheet.set_defaults(handler=cmd_sheet)

    listing = sub.add_parser("list", help="list runs, or the generations of one run")
    listing.add_argument("--run", help="run id")
    listing.set_defaults(handler=cmd_list)

    keep = sub.add_parser("keep", help="mark a generation as kept")
    keep.add_argument("generation_id", type=int)
    keep.add_argument("--undo", action="store_true")
    keep.set_defaults(handler=cmd_keep)

    engines = sub.add_parser("engines", help="list available engines")
    engines.set_defaults(handler=cmd_engines)
    return parser


def _message(exc: Exception) -> str:
    return str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = build_app(args.db, args.out)
    try:
        return args.handler(args, app)
    except (StudioError, ValueError, KeyError, OSError) as exc:
        print(f"error: {_message(exc)}", file=sys.stderr)
        return 2
    finally:
        app.journal.close()
