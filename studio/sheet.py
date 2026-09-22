"""Exports one self contained HTML contact sheet per run. Reads the journal, never calls an engine."""
from __future__ import annotations

import os
from html import escape
from pathlib import Path
from urllib.parse import quote

from studio.journal import GenerationRecord, Journal
from studio.store import ArtifactStore

CSS = """
body{font-family:system-ui,sans-serif;margin:2rem auto;max-width:1100px;padding:0 1rem;color:#1d1d1f;background:#fafafa}
h1{margin-bottom:.2rem} h2{margin-top:2.2rem;border-bottom:2px solid #ddd;padding-bottom:.3rem}
.sub{color:#666;font-size:.9rem}
.brief{background:#fff;border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}
.brief dt{font-weight:600;float:left;clear:left;width:9rem}.brief dd{margin:0 0 .3rem 9rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem}
.card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:.7rem;font-size:.85rem}
.card img{width:100%;border-radius:4px;display:block}
.card.error{border-color:#c0392b}.err{background:#fdecea;color:#7b241c;padding:1rem;border-radius:4px}
.meta{width:100%;border-collapse:collapse;margin-top:.5rem}.meta td{padding:.15rem 0;vertical-align:top}
.meta td:first-child{color:#666;width:6.5rem}
.kept{color:#b7791f;font-weight:700} code{font-size:.8rem;word-break:break-all}
details{margin-top:.4rem} summary{cursor:pointer;color:#555}
"""


def _row(label: str, value: str) -> str:
    return f"<tr><td>{escape(label)}</td><td>{value}</td></tr>"


def _card(rec: GenerationRecord, sheet_dir: Path, store: ArtifactStore) -> str:
    params = ", ".join(f"{k}={v}" for k, v in sorted(rec.params.items())) or "none"
    kept = ' <span class="kept">&#9733; kept</span>' if rec.kept else ""
    if rec.status == "ok":
        rel = os.path.relpath(store.full_path(rec.output_path), sheet_dir).replace(os.sep, "/")
        visual = f'<img src="{quote(rel)}" alt="{escape(rec.engine)} seed {rec.seed}">'
    else:
        visual = f'<div class="err"><b>Generation failed</b><br>{escape(rec.error or "unknown error")}</div>'
    sha = rec.output_sha256 or ""
    rows = [
        _row("Generation", f"#{rec.id}{kept}"),
        _row("Seed", str(rec.seed)),
        _row("Parameters", escape(params)),
        _row("Engine version", escape(rec.engine_version)),
        _row("SHA256", f'<code title="{escape(sha)}">{escape(sha[:16])}</code>' if sha else "none"),
        _row("Created", escape(rec.created_at)),
        _row("Author", escape(rec.author)),
    ]
    return (
        f'<div class="card{"" if rec.status == "ok" else " error"}">{visual}'
        f'<table class="meta">{"".join(rows)}</table>'
        f"<details><summary>Prompt sent</summary><p>{escape(rec.prompt)}</p></details></div>"
    )


def export_sheet(run_id: str, *, journal: Journal, store: ArtifactStore) -> Path:
    run = journal.get_run(run_id)
    records = journal.list_generations(run_id)
    path = store.full_path(f"{run_id}/sheet.html")
    path.parent.mkdir(parents=True, exist_ok=True)

    brief = run.brief
    elements = "".join(
        f"<li>{escape(e['what'])} ({escape(e['placement'])})</li>" for e in brief.get("elements", [])
    ) or "<li>none</li>"
    brief_html = (
        "<dl>"
        f"<dt>Scene</dt><dd>{escape(brief['scene'])}</dd>"
        f"<dt>Lighting</dt><dd>{escape(brief['lighting'])}</dd>"
        f"<dt>Time of day</dt><dd>{escape(brief['time_of_day'])}</dd>"
        f"<dt>Mood</dt><dd>{escape(brief['mood'])}</dd>"
        f"<dt>Elements</dt><dd><ul>{elements}</ul></dd></dl>"
    )

    by_engine: dict[str, list[GenerationRecord]] = {}
    for rec in records:
        by_engine.setdefault(rec.engine, []).append(rec)

    sections = []
    for engine, recs in by_engine.items():
        cards = "".join(_card(r, path.parent, store) for r in recs)
        sections.append(
            f"<h2>{escape(engine)} <span class='sub'>version {escape(recs[0].engine_version)}, "
            f"{len(recs)} generation(s)</span></h2><div class='grid'>{cards}</div>"
        )

    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>Contact sheet {escape(run_id)}</title><style>{CSS}</style></head><body>"
        f"<h1>Contact sheet</h1><div class='sub'>Run {escape(run.run_id)} | created "
        f"{escape(run.created_at)} | author {escape(run.author)} | optimizer {escape(run.optimizer_id)}</div>"
        f"<div class='brief'>{brief_html}</div>{''.join(sections)}</body></html>"
    )
    path.write_text(html, encoding="utf-8")
    return path
