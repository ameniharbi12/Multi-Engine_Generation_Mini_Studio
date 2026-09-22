"""Orchestrates a run: plan first (no side effects), then execute (journal every result).

This file knows nothing about specific engines, SQL, file paths or printing.
"""
from __future__ import annotations

from dataclasses import dataclass

from studio.engines.base import EngineAdapter, EngineError
from studio.environment import capture_environment
from studio.journal import GenerationRecord, Journal
from studio.models import Brief, GenerationRequest, RunConfig
from studio.prompts import PromptOptimizer, check_prompt
from studio.registry import Registry
from studio.store import ArtifactStore


@dataclass(frozen=True)
class Job:
    adapter: EngineAdapter
    request: GenerationRequest


@dataclass(frozen=True)
class RunResult:
    run_id: str
    records: tuple[GenerationRecord, ...]

    @property
    def ok_count(self) -> int:
        return sum(r.status == "ok" for r in self.records)

    @property
    def error_count(self) -> int:
        return len(self.records) - self.ok_count


def plan_run(brief: Brief, config: RunConfig, registry: Registry,
             optimizer: PromptOptimizer) -> list[Job]:
    """Resolve engines, build one prompt per engine, merge params. Writes nothing."""
    stray = set(config.params_overrides) - set(config.engines)
    if stray:
        raise ValueError(f"parameters given for engines that are not selected: {sorted(stray)}")

    jobs: list[Job] = []
    for name in config.engines:
        adapter = registry.get(name)                      # unknown engine fails here
        prompt = optimizer.optimize(brief, adapter.profile).prompt   # once per engine
        check_prompt(prompt, adapter.profile, adapter.name)
        params = {**adapter.default_params, **config.params_overrides.get(name, {})}
        adapter.check_params(params)                      # typos in parameter names fail here
        jobs += [Job(adapter, GenerationRequest(prompt, seed, params)) for seed in config.seeds]
    return jobs


def execute_job(job: Job, *, run_id: str, env: dict, author: str,
                store: ArtifactStore, journal: Journal) -> GenerationRecord:
    """One generation, one journal row. An engine failure becomes an error row."""
    adapter, req = job.adapter, job.request
    common = dict(run_id=run_id, engine=adapter.name, engine_version=adapter.version,
                  seed=req.seed, prompt=req.prompt, params=req.params, env=env, author=author)
    try:
        result = adapter.generate(req)
    except EngineError as exc:
        return journal.record_generation(status="error", error=str(exc), **common)
    artifact = store.save_generation(run_id, adapter.name, req.seed, result.image_bytes)
    return journal.record_generation(
        status="ok", output_path=artifact.path, output_sha256=artifact.sha256, **common)


def run_brief(brief: Brief, config: RunConfig, *, registry: Registry,
              optimizer: PromptOptimizer, store: ArtifactStore, journal: Journal) -> RunResult:
    jobs = plan_run(brief, config, registry, optimizer)
    run_id = journal.start_run(brief, config, optimizer.id)
    env = capture_environment()
    records = tuple(
        execute_job(job, run_id=run_id, env=env, author=config.author, store=store, journal=journal)
        for job in jobs
    )
    return RunResult(run_id, records)
