# Multi engine generation mini studio

Turns a structured creative brief into image generation runs across several engines, with a full
journal, one command replay, and an HTML contact sheet per run. Everything runs offline on the
provided mock engines.

## Setup (5 commands)

```
python -m venv .venv
.venv\Scripts\activate                # macOS and Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m studio run briefs/coastal.json --author yourname
```

The last command generates 2 engines x 2 seeds, journals them in `journal.db`, saves the images in
`outputs/`, and prints the path of the contact sheet.

## Commands

| Command | What it does |
|---|---|
| `python -m studio engines` | List the discovered engines, versions and prompt styles |
| `python -m studio run BRIEF.json` | Run a brief. Options: `--engines a,b`, `--seeds N`, `--base-seed N`, `--param engine.name=value`, `--author NAME`, `--dry-run`, `--no-sheet` |
| `python -m studio list [--run RUN_ID]` | List runs, or the generations of one run |
| `python -m studio replay ID` | Regenerate generation ID from the journal alone and compare hashes. Exit code 0 if identical, 1 if different |
| `python -m studio sheet RUN_ID` | Export (or refresh) the contact sheet of a run |
| `python -m studio keep ID [--undo]` | Mark a generation as kept (the optional selection mechanism) |

Global options go before the command: `--db journal.db` and `--out outputs`.

A brief is a JSON file: `scene`, `lighting`, `time_of_day`, `mood`, and up to five `elements`, each
with `what` and `placement`. See `briefs/`.

## Sample deliverables

Produced by this code with these commands (see `samples/`):

```
python -m studio --db samples/journal.db --out samples/outputs run briefs/coastal.json --seeds 2 --author ameni --param verbosa.quality=final
python -m studio --db samples/journal.db --out samples/outputs keep 1
python -m studio --db samples/journal.db --out samples/outputs replay 3
```

`samples/journal.db` is the journal. The contact sheet is `samples/outputs/<run id>/sheet.html`.

## Architecture

```
studio/
  models.py        shared dataclasses (imports nothing from the project)
  errors.py        expected errors the CLI prints cleanly
  engines/
    base.py        EngineAdapter contract + EngineError
    tagline.py     Engine A adapter + its prompt rules   (ADAPTER = ...)
    verbosa.py     Engine B adapter + its prompt rules   (ADAPTER = ...)
  registry.py      name -> adapter, with automatic discovery of engines/
  prompts.py       optimizer interface, rule based optimizer, LLM shaped optimizer
  store.py         saves images, computes SHA256
  journal.py       all SQL (runs, generations, replays)
  runner.py        plan then execute a run
  replay.py        replay from the journal and verify
  sheet.py         HTML contact sheet
  cli.py           argument parsing, wiring, printing
mock_engines.py    the provided SDKs, untouched
```

Dependencies point downward only. The core (`runner`, `replay`, `sheet`, `journal`, `store`,
`prompts`, `cli`) never imports `mock_engines` and never mentions an engine by name; a test enforces
this. Objects (registry, journal, store, optimizer) are built once in `cli.py` and passed in.

### Adding a third engine

Create one file in `studio/engines/` with an adapter class and a last line `ADAPTER = MyAdapter()`.
It declares its `name`, `version`, `default_params`, a `PromptProfile` (its prompt style, limits and
render function) and a `generate` method that returns bytes or raises `EngineError`.
Nothing else changes. `tests/test_extensibility.py` proves it end to end (run, replay, sheet), and
`tests/test_registry.py` proves the file discovery.

## Design choices

- **Adapter + registry + prompt profile.** The adapter hides each SDK's shape (function vs client
  object, exceptions vs status dicts, bytes vs base64). The profile lets an engine bring its own
  prompt style without touching the optimizer.
- **The final prompt is stored, not just the brief.** Replay uses only stored values (prompt, seed,
  parameters, engine version), so it never depends on the optimizer. This matters as soon as an LLM
  optimizer is used, because it can answer differently tomorrow.
- **Reproducibility is verified by hash.** Every image is fingerprinted (SHA256) when saved. Replay
  regenerates, hashes, compares, and records the outcome in its own `replays` table, so the history
  of generations stays clean and originals are never overwritten.
- **Plan first, then execute.** `plan_run` has no side effects: unknown engines, bad parameters and
  prompts that break an engine's limits fail before anything is written. `--dry-run` is free.
- **Failures are data.** An engine error becomes an `error` row and the run continues. Unexpected
  exceptions (real bugs) are not swallowed.
- **Journal normalized on run id.** The brief is stored once per run and each generation points to
  it. Each generation also stores prompt, engine and version, seed, resolved parameters, output
  path, hash, environment (Python and Pillow versions), timestamp and author.
- **LLM shaped optimizer interface.** `optimize(brief, profile) -> PromptResult`. The rule based
  optimizer is the default; `LLMOptimizer` shows the same interface backed by any completion function.

## Trade offs

- SQLite over JSON files: real queries, transactions, one file. Cost: a single writer.
- Sequential runs: simple and deterministic, and the mock engines are instant.
- Free text brief fields: creative freedom, but no protection against typos.
- Tagline prompts drop the least important tags to fit 300 characters, which is simple but not smart.
- Image paths are stored relative to the output folder, so a journal and its images can be moved
  together. The contact sheet uses relative links for the same reason.

## Known limits

- Mock engines only. Real services would need timeouts, retries, authentication and probably async.
- The rule based optimizer is not semantic. `LLMOptimizer` is an interface demonstration, tested with
  a fake completion function, never with a real model.
- Byte identical replay depends on the PNG encoder. A different Pillow version or platform could
  change the bytes for the same pixels, and replay would report DIFFERENT even though the engine is
  unchanged. The environment is journaled and replay prints any difference to help diagnose this.
- Replay needs the same engine installed. A different engine version only produces a warning note.
- The author field is self reported, and the database is not tamper proof. Only image files are
  checked against their stored hash.
- Parameter values from `--param` are parsed as JSON when possible, otherwise kept as text.
- Contact sheet is HTML only, with no interactive selection.
- No concurrency between processes beyond what SQLite provides. No CI or packaging.

## With two more days

1. A real LLM optimizer with a per engine evaluation set and prompt caching.
2. Parallel generation with a thread pool, keeping journal writes on the main thread.
3. A hash chained journal so tampering is detectable, and schema migrations.
4. Selection from inside the HTML sheet, and export of kept images only.
5. A PDF sheet and controlled vocabularies for lighting and time of day.
