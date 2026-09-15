# Troubleshooting and Development Lessons

Real failures, diagnoses and lessons from building this pipeline, with the
current status of each item. Nothing here is whitelisted: every warning and
every limitation still belongs to the QA obligations of the later milestones
(M4 mechanics/contact QA and beyond).

## How to read this document

Status labels:

- `RESOLVED` 鈥?root cause found and fixed; a regression test guards it.
- `WORKAROUND` 鈥?a validated bypass exists; the underlying cause is not fixed.
- `KNOWN LIMITATION` 鈥?accepted scope boundary of the current milestone.
- `DEFERRED` 鈥?deliberately moved to a later milestone.
- `HISTORICAL` 鈥?debugging evidence kept for learning; no longer active.

Evidence for every item lives in `work/<attempt>` directories (git-ignored)
and the linked project documents.

## Abaqus General Contact preprocessing / threads-per-domain failure

Status: `WORKAROUND` (machine/runtime-specific)

Running a datacheck or analysis with the default parallel mode
(`standard_parallel=all`) aborted in `pre.exe` during General Contact
connectivity processing (`pre | Elem | ElemC | Econtp | ConnectivityAtNodes`):

```
***ERROR: EXCEEDED THE MAXIMUM AMOUNT OF THREADS TO BE USED PER DOMAIN.
PLEASE REDUCE THE NUMBER OF THREADS TO BE LESS THAN OR EQUAL TO 100.
```

Diagnosis path (10 controlled attempts, see
`work/fig1_datacheck_m2_diagnostics_summary.json` in the development
workspace):

1. Clean environment (minimal PATH, cleared variables) 鈫?identical failure 鈫?
   inherited-environment pollution ruled out.
2. The manually built baseline model (`Fig1_Compression.inp`, which had
   completed a 20% solve on the same install) failed identically 鈫?the
   automatic deck was exonerated.
3. `cpus=1` did not bypass it; `threads_per_domain` is not a valid CLI
   option; `standard_parallel=mpi` is rejected.
4. A mesh-only input without General Contact completed
   (`ANALYSIS DATACHECK COMPLETE`) 鈫?the failure is specific to the General
   Contact parallel element/preprocessing path.
5. `standard_parallel=solver` (serial element operations) clears the failure:
   the same deck completes the Data Check and a real 20% solve.

Interpretation: a reproducible machine/runtime-specific failure of the
parallel element/preprocessing path. This is an experiment description, not
a claim about an Abaqus source-level defect. Other machines must not assume
they need `standard_parallel=solver`; validate before adopting a profile.

## Why standard_parallel=solver is used on the development workstation

Status: `WORKAROUND` / current safe profile

With element operations serial, the General Contact preprocessing failure
disappears while the solver still runs (optionally multi-threaded). This is
why the portable safe default is `cpus=1, standard_parallel=solver` and the
development workstation validated `cpus=4, solver` (16m33s solve) and tested
`cpus=8, solver` (see the CPU-count experiment below).

## jleConfig reqcpus hypothesis and why it was ruled out

Status: `HISTORICAL` (hypothesis falsified)

The site file `SMA/site/jleConfig.env` sets
`aba_jle_std_direct_reqcpus='32'`, more than the host's 14 cores / 20 logical
processors. A strict single-variable experiment (SHA-verified backup, exactly
one line changed `'32' 鈫?'4'`, effectiveness confirmed through
`information=environment`) still produced the identical threads/domain error,
so the hypothesis was falsified and the original value restored. Lesson:
confirm a configuration value is actually *used by the failing code path*
before blaming it, and always run one-variable experiments with verifiable
backups.

## Data Check interactive .log behavior

Status: `KNOWN LIMITATION` (handled)

Abaqus 2026 datacheck interactive runs complete without writing a `.log`
file; stdout carries the log role. The M2 required-artifact set is therefore
`.dat + .odb + stdout capture`; `.msg/.log/.exception` are collected when
present.

## M2 warning signatures (10 warnings, retained)

Status: `KNOWN LIMITATION` (QA obligations for M4)

The accepted Fig.1 Data Check reports 10 warnings, zero errors:

- 1脳 General Contact domain has double-sided facets; initial contact
  adjustments may be incorrect; single-sided surfaces are recommended.
- 1脳 STRAINFREE adjustment ratio (max incremental adjustment / average
  characteristic length = 2.55003E-02 at node 544).
- 8脳 adjacent secondary nodes on opposite sides of the double-sided main
  surface (nodes 72/71, 85/84, 83/85, 117/116, 171/169, 170/171, 169/170,
  377/376).

These match the diagnostic signature of the manual 20% baseline job 鈥?not a
new automation regression 鈥?but they are not proven harmless. The M3 solve
re-emits the same 10 warnings in its own `.dat` (signature-identical) plus 7
solver-only zero-moment warnings from the `.msg`.

## Zero-moment warnings

Status: `KNOWN LIMITATION` (QA obligations for M4)

The solve `.msg` contains 7脳
`***WARNING: THERE IS ZERO MOMENT EVERYWHERE IN THE MODEL BASED ON THE
DEFAULT CRITERION`. The historical manual 20% job showed the same class of
startup warnings. They are recorded in the solve report and left for M4
mechanics QA; no acceptance decision is derived from them.

## STRAINFREE warning

Status: `KNOWN LIMITATION` (QA obligations for M4)

The preprocessing STRAINFREE adjustment-ratio warning means Abaqus moved
secondary nodes to resolve initial overclosures. The magnitudes can be
reviewed with STRAINFREE contour/symbol plots at time=0 once M4 extraction
exists. Until then the initial contact state is not scientifically cleared.

## Double-sided contact warnings

Status: `KNOWN LIMITATION` (QA obligations for M4)

Abaqus suggests single-sided surfaces for a General Contact domain with
double-sided shell facets. The current model intentionally reproduces the
hand baseline (ALL EXTERIOR over a doubly connected shell plus platens).
Moving to single-sided surfaces is a modeling decision that must be
evaluated with real extraction evidence, not done to silence a warning.

## M3 .sta parser bug

Status: `RESOLVED`

The first real 20% solve physically completed (stdout token, `.sta`
completion marker, 0 errors), but the report said `SOLVE_FAILED` with
`last_step_time=null`: the original `.sta` parser assumed a fixed 9-column
row, while real Abaqus/Standard rows carry 6鈥? integer fields followed by up
to THREE time columns (TOTAL TIME, STEP TIME, INC OF TIME), and cutback rows
carry `U` markers (e.g. `1U`). The parser now consumes leading integer
fields generically and reads the first two float time columns, skipping
cutback rows. A regression test uses the real three-time-column format.

## Attempt 001: physical completion but parser false negative

Status: `HISTORICAL` / `RESOLVED`

`work/fig1_solve_m3_20pct_001` 鈥?wall time 鈮?5m07s, `returncode=0`,
`Abaqus JOB fig1_m3_solve COMPLETED`, analysis physically complete 鈥?but
reported `SOLVE_FAILED` because of the parser bug above. Kept as evidence;
the bug is fixed and guarded by a regression test.

## Attempt 002: accidental duplicate solve and manual termination

Status: `HISTORICAL`

`work/fig1_solve_m3_20pct_002` 鈥?an accidentally duplicated solve invocation
(鈮?m40s, analysis still in the early increments) that was manually
terminated with a process-tree kill as soon as it was noticed. It has no
command.json/solve_report.json because those are written after normal
completion. Not a valid simulation data point; kept as evidence of the
incident and of the manual cleanup path.

## Attempt 003: accepted validation solve

Status: `RESOLVED` (official M3 evidence)

`work/fig1_solve_m3_20pct_003` 鈥?wall time 鈮?6m33s after the parser fix,
59 increments, `last_step_time = 1.00 = target`, 0 errors, 17 warnings,
complete ODB. Official accepted M3 solve evidence
(`SOLVE_COMPLETED_WITH_WARNINGS`).

## 8-CPU solver experiment

Status: `HISTORICAL` (experiment result recorded; 4 CPU remains preferred)

Single-variable experiment on the same accepted deck
(`work/fig1_solve_cpu8_validation_001`, only `cpus: 4 鈫?8` changed,
`standard_parallel=solver` kept): the solve completed
(`SOLVE_COMPLETED_WITH_WARNINGS`, 59 increments, identical cutback pattern,
0 errors, 17 warnings, same ODB size 16,075,836 bytes) but took 鈮?2m51s
versus 鈮?6m33s at 4 CPUs 鈥?clearly slower. The local preferred profile
therefore stays `cpus=4, standard_parallel=solver`; the experiment is
retained as evidence that wall time on this machine is not simply monotonic
in CPU count for this nonlinear job.

## Timeout / child process tree limitation

Status: `DEFERRED` (M7 reliability)

If a solve exceeds the wall limit, `subprocess.TimeoutExpired` aborts the
Python side before `command.json`/`solve_report.json` are written, so the
attempt keeps raw outputs but incomplete structured evidence; and only the
launcher-level process is killed, leaving possible SMALauncher/standard.exe
descendants that need manual reconciliation. Watchdog, kill-tree, retry,
resume and adoption belong to the M7 reliability milestone.

## Attempt preservation policy

Status: `CURRENT`

Every attempt lives in its own `work/<attempt>` directory and is never
overwritten or cleaned. Failed attempts (including false negatives, aborted
experiments and the accidental duplicate above) are retained verbatim so any
conclusion can be re-derived from the raw `.dat/.msg/.sta/.odb` files and
reports.

## How to diagnose a failed run

1. Read `solve_report.json` / `datacheck_report.json`: `status`,
   `failure_reasons`, `diagnostics` (errors with source file and line), and
   `claims`.
2. Read `stdout.txt` for the launcher-level outcome and the
   `Abaqus JOB <name> COMPLETED` token.
3. Read `.sta` (completion marker, last increment, cutback rows) and `.dat`
   / `.msg` for `***ERROR` / `***WARNING` context.
4. Check `.exception` files for Abaqus abort call stacks.
5. Compare with the reference evidence in `work/fig1_solve_m3_20pct_003`
   (accepted solve) before suspecting the deck itself.
6. Never re-run into the same attempt directory; create a new one and state
   the reason for the new run.

## 30% compression non-convergence (historical)

Status: `HISTORICAL` / `KNOWN LIMITATION`

Earlier manual attempts to push the same model to 30% compression
(U3 = 鈭? mm) stalled before reaching the target, while 20% (U3 = 鈭? mm)
completed. This does not mean the automation pipeline is invalid: the 20%
case was intentionally used as the M3 infrastructure validation target, and
30% remains a later numerical/research validation target (M4+ extraction and
QA must come first). No parameter was changed to force convergence.
