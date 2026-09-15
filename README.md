# Auto Abaqus Periodic Surface Pipeline

Automated Abaqus/Standard pipeline for periodic porous-surface structures:
surface equation → periodic mesh → physical model generation → real Abaqus
Data Check → real single-job solve → (next) ODB extraction and mechanics QA.

## 1. Overview

This repository contains a Python-driven automation pipeline that builds and
runs compression simulations of periodic surface structures in
Abaqus/Standard without opening Abaqus/CAE. Every stage runs in its own
immutable "attempt" directory and produces structured JSON reports plus raw
Abaqus evidence, so every success and every failure stays traceable.

The working language of the code and reports is English; several project
documents are written in Chinese.

## 2. Motivation and project background

The project was developed while studying and partially reproducing the
simulation/data-generation workflow used in diffusion-based mechanical
metamaterial research: a periodic porous surface shell uniaxially compressed
between two rigid platens, with lateral periodic boundary conditions and
General Contact.

The goal is **not** an exact replication of every material parameter,
compression target or implementation detail of the source paper. The goal is
a robust, reusable Abaqus automation pipeline supporting future
multi-surface studies and dataset generation. A validated hand-built model
(`Fig1_Compression.inp`, 20% compression) serves as the keyword-semantic
baseline, and one validation case (Fig.1) proves the automation chain end to
end.

## 3. What is implemented today

Implemented and real-tested on the development workstation (Abaqus 2026):

- Periodic mesh preparation (frozen `vendor/periodic_surface_mesher_v1.0`
  pipeline) and mesh contract validation.
- Complete physical model generation: shell mesh, material/section, rigid
  platens and reference points, boundary conditions, lateral XY periodic
  boundary equations, General Contact, Dynamic Implicit compression step and
  output requests — assembled into a top-level `physical.inp` and verified by
  13 repository-owned static checks.
- Real Abaqus Physical Data Check of the generated deck (Fig.1: 0 errors,
  10 warnings retained).
- Real single-job Abaqus/Standard solve of the accepted deck (Fig.1 20%
  validation case: completed, target step time reached, 0 errors, 17
  warnings retained, ODB artifact produced).

## 4. What is NOT implemented yet

- ODB extraction / results QA (M4) — the solve ODB has not been opened yet.
- 30% compression acceptance (a later validation target; an earlier manual
  30% attempt did not converge — see docs/TROUBLESHOOTING.md).
- Batch/multi-surface execution, retry/watchdog/recovery, dataset export.
- UMAT, n×n×n cells, 3D PBC — intentionally out of scope for now.

`dataset_eligible` is always `false` at this stage.

## 5. Pipeline overview

```
surface equation/config
        |  prepare-mesher (frozen CGAL mesher)      [implemented]
        v
periodic mesh (shell.npz + report + pairs.csv)
        |  mesh QA / contract validation            [implemented]
        v
        |  build-physical                           [implemented]
        v
physical.inp + blocks/ + ingredients/ + model_manifest.json
        |  repository static validation (13 checks) [implemented]
        v
        |  datacheck (real Abaqus)                  [implemented]
        v
datacheck_report.json (accepted deck)
        |  solve (real Abaqus/Standard)             [implemented]
        v
solve_report.json + ODB artifact
        |  M4: ODB extraction                       [NEXT]
        v
histories / fields / metadata
        |  M4+: mechanics QA, curve QA              [planned]
        v
stress-strain curve, standardized results
        |  future: multi-surface batch, ML          [future]
```

## 6. Repository structure

| Path | Content |
|---|---|
| `run.py` | CLI entry (`pixi run cli <command>`) |
| `pipeline/` | Automation modules (builder, datacheck, solve, PBC, QA, state) |
| `abaqus_worker/` | Abaqus-Python-only worker scripts (M4, not wired yet) |
| `config/` | Example configs (`*.example.json`) and machine-local configs (`*.local.json`, git-ignored) |
| `tests/` | Unit tests (synthetic fixtures only; never real Fig.1 results) |
| `docs/` | Project documentation (see Documentation index) |
| `vendor/periodic_surface_mesher_v1.0/` | Frozen, validated periodic surface mesher (do not modify) |
| `scripts/` | Pixi task wrappers and migration boundary tests |
| `work/<attempt>/` | One immutable directory per run (git-ignored) |


## 7. Requirements

- Windows, and an Abaqus/Standard installation. Abaqus 2026 is the version
  actually validated; other versions are untested.
- A working Abaqus launcher: `abaqus.bat`/`abq2026.bat` on PATH or configured
  in `config/environment.local.json` (see §10).
- [Pixi](https://pixi.sh) for the Python environments (`pixi.toml` +
  `pixi.lock` define everything; no Conda activation needed — the historical
  Conda workflow is retained in `docs/HISTORICAL_v0.1_README.md`).
- For mesh generation: the CGAL toolchain expected by the frozen mesher
  (`pixi run build-cgal --check-only` verifies it).

## 8. Python/Abaqus environment separation

Two runtimes that must never be mixed:

- **Pixi Python** (`default` environment): all pipeline code, configs, JSON
  reports, staging and process launching.
- **Abaqus Python** (shipped with Abaqus): only ODB access and
  Abaqus-internal tasks (`abaqus_worker/`, M4).

The pipeline never imports odbAccess into Pixi Python and never injects its
own environment into Abaqus. Data exchange happens through files inside the
attempt directories.

## 9. Quick start

```
pixi run check        # verify the three Pixi environments
pixi run test         # run the test suite (synthetic fixtures, no Abaqus)
pixi run plan         # print pipeline stages and implementation status
pixi run cli-help     # list all CLI commands
```

Then the real Abaqus chain (every `--out` must be a NEW directory):

```
pixi run cli build-physical --npz <shell.npz> --report <report.json> --pairs <pairs.csv> --out work/<new-attempt>
pixi run cli datacheck --build-dir work/<build-attempt> --out work/<new-attempt>
pixi run cli solve --datacheck-dir work/<datacheck-attempt> --out work/<new-attempt>
```

`build-physical` requires a validated mesh bundle (`shell.npz` +
`shell_report.json` + `periodic_pairs.csv`) produced by the frozen mesher
pipeline (see §11).

## 10. Configuration files

| File | Purpose |
|---|---|
| `config/cases/fig1.json` | Case definition of the validated baseline surface |
| `config/physics.example.json` | Boundary mode, PBC, contact, platens, compression target, step time |
| `config/materials/demo_surrogate.json` | Material definition (demo surrogate, not production data) |
| `config/numerics.example.json` | Procedure, increments, stabilization policy (step numerics) |
| `config/outputs.example.json` | ODB output requests (restart/field/history) |
| `config/quality.example.json` | Draft curve-QA policy (used from M4 on) |
| `config/environment.example.json` | Abaqus launcher and release requirement (machine-local) |
| `config/datacheck_runtime.example.json` | Data Check execution policy (cpus, standard_parallel) |
| `config/solve_runtime.example.json` | Solve execution policy (cpus, standard_parallel) |

`*.example.json` files are tracked, portable templates. Copy one to the same
name with `.local.json` (that suffix is git-ignored) to configure your
machine. Runtime policy resolution order: CLI flags → `*.local.json` →
built-in safe default. Local configs never enter the repository.

## 11. Typical workflow

1. `prepare-mesher` → run the frozen CGAL mesher → `mesh-post`/`mesh-check`
   to obtain a validated mesh bundle.
2. `build-physical` with the bundle and your physics/material configs → a
   static-validated `physical.inp` plus `model_manifest.json`.
3. `datacheck` with the build attempt → Abaqus itself judges the deck
   (`DATACHECK_PASSED` or `DATACHECK_COMPLETED_WITH_WARNINGS` are accepted;
   both require the `ANALYSIS DATACHECK COMPLETE` marker and zero errors).
4. `solve` with the datacheck attempt → real analysis, judged by return code
   + a stdout completion token naming this exact job + the `.sta` completion
   marker + fatal diagnostics + required artifacts + the target step time.
5. (M4, not implemented) extract the ODB and run mechanics/curve QA.

Every stage refuses to overwrite an existing attempt directory and keeps all
raw evidence — including failures.

## 12. Attempt / artifact structure

Each attempt directory contains (depending on the stage):

```
physical.inp                top-level deck (fixed-order *Include graph)
ingredients/                shell mesh + PBC equations + model inputs
blocks/                     material/section, platens, BCs, contact, step, outputs
model_manifest.json         M1 model identity and static-validation state
datacheck_report.json       M2: status, diagnostics, execution policy, artifacts
solve_report.json           M3: status, completion evidence, wall_time_s, ODB info
*.dat *.msg *.sta *.odb …   raw Abaqus evidence (never deleted, never cleaned)
command.json stdout.txt stderr.txt
```

Attempts are immutable: a stage never writes into another stage's directory,
and existing attempt directories are never overwritten.

## 13. Runtime profiles

Execution policies (cpus / standard_parallel) are machine/runtime-local:
they only appear on the Abaqus command line and in the reports — never
inside `physical.inp` — so the same deck can run with different profiles on
different machines, and the model identity keys never change.

- **Portable conservative fallback**: `cpus=1, standard_parallel=solver`.
- **Development workstation validated profiles**: `cpus=4, solver` and
  `cpus=8, solver` (both execution-level validated on the Fig.1 20% case;
  4 CPUs was the faster configuration on this machine — see
  docs/TROUBLESHOOTING.md).
- `standard_parallel=all` reproduces a threads-per-domain failure during
  General Contact preprocessing on the development workstation (the manual
  baseline model fails identically). Other machines must not assume they
  need the same workaround; see docs/TROUBLESHOOTING.md.

## 14. Validation evidence

- Fig.1 physical model: static validation PASS (13 checks), real Data Check
  accepted (`0 errors`, 10 warnings retained), real 20% solve completed
  (`SOLVE_COMPLETED_WITH_WARNINGS`, target step time reached, 0 errors,
  17 warnings retained, ODB artifact 16,075,836 bytes).
- Test suite: 142 core tests + 8 Pixi boundary tests, all passing (synthetic
  fixtures only; no test depends on real Abaqus or real Fig.1 results).
- The M2 warnings (double-sided General Contact facets, STRAINFREE adjustment
  ratio, 8 adjacent secondary nodes on opposite sides of the main surface)
  and the solve warnings (zero moment) are **retained as QA obligations for
  M4** — not whitelisted, not proven harmless.

## 15. Known limitations

- Single cell, lateral XY PBC only; no 3D PBC, no n×n×n.
- Demo surrogate material — not experimentally calibrated data.
- M2/M3 warnings retained (contact initialization, zero moment) need
  mechanics QA before any scientific use.
- 30% compression target is unproven in automation (a historical manual 30%
  attempt did not converge; see docs/TROUBLESHOOTING.md).
- No ODB extraction, no batch, no retry/watchdog yet; a solve timeout leaves
  incomplete structured evidence (logged as technical debt for M7).
- Validated only on the development workstation with Abaqus 2026 and the
  Fig.1 20% validation case; other machines/versions/cases are untested.

## 16. Troubleshooting

See `docs/TROUBLESHOOTING.md` — real failures from this project with their
diagnosis paths and current status: the parallel preprocessing failure, the
falsified `jleConfig` hypothesis, the `.sta` parser bug, Data Check warning
signatures, the solve timeout caveat, and how failed runs are diagnosed and
preserved.

## 17. Historical development records

Development and debugging history is deliberately preserved — including
failed hypotheses, the 30% non-convergence record, the duplicate-solve
incident and the parser false negative:

- `docs/HISTORICAL_v0.1_README.md` — the full superseded v0.1 README.
- `docs/HANDOFF_CURRENT.md` — current takeover snapshot.
- `docs/PROJECT_STATUS.md` — validated engineering facts and evidence levels.
- `docs/IMPLEMENTATION_STATUS.md` — per-milestone implementation history.
- `docs/IMPLEMENTATION_PLAN.md` — planned, active and deferred work.
- `docs/LOCAL_ENVIRONMENT.md` — development-machine evidence
  (`[LEGACY]` Conda sections retained for reproducibility; the current
  workflow is Pixi-only).
- `docs/TROUBLESHOOTING.md` — failures and debugging lessons.

## 18. Roadmap

M0 environment/baseline ✅ → M1 physical INP writer ✅ → M2 Physical Data
Check ✅ → M3 single-job solve ✅ → **M4 ODB extraction + raw-result
integrity (next)** → M5 single-case closed loop → M6 mesh automation →
M7 reliability engineering → M8 batch. Details:
`docs/PROJECT_ROADMAP.md`.

## 19. Documentation index

| Document | Role |
|---|---|
| `README.md` | Public entry point (this file) |
| `AGENTS.md` | AI/contributor coding rules |
| `docs/PROJECT_ROADMAP.md` | Stable architecture and milestone definitions |
| `docs/PROJECT_STATUS.md` | Validated engineering facts |
| `docs/IMPLEMENTATION_STATUS.md` | Detailed implementation history |
| `docs/IMPLEMENTATION_PLAN.md` | Planned and deferred work |
| `docs/HANDOFF_CURRENT.md` | Current developer/AI takeover snapshot |
| `docs/LOCAL_ENVIRONMENT.md` | Historical/current developer-machine evidence |
| `docs/TROUBLESHOOTING.md` | Failures, debugging and lessons learned |
| `docs/HISTORICAL_v0.1_README.md` | Superseded v0.1 README (historical) |
| `docs/VERIFICATION.md` | Historical verification evidence |
| `docs/Abaqus_Automation_Design_v1.0.md` | Original design document (historical architecture reference) |
| `docs/LOCAL_EVIDENCE.json` / `docs/source_inventory.json` | Historical local evidence snapshots (not portable configuration) |

## License

A repository license has not yet been selected.
