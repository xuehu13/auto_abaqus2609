"""Small tested primitives. The release-specific .sta parser/launcher is a next-stage adapter."""
import re


FATAL = re.compile(r"\*{3}\s*ERROR\b|\bTHE ANALYSIS HAS NOT BEEN COMPLETED\b|\bABAQUS/(?:STANDARD|EXPLICIT) ANALYSIS EXITED WITH AN ERROR\b", re.I)
WARNING = re.compile(r"\*{3}\s*WARNING\b", re.I)


def classify_messages(text):
    fatal, warnings = [], []
    for number, line in enumerate(text.splitlines(), 1):
        if FATAL.search(line):
            fatal.append({"line": number, "text": line.strip()})
        elif WARNING.search(line):
            warnings.append({"line": number, "text": line.strip()})
    return {"fatal": fatal, "warnings": warnings,
            "note": "No ERROR substring matching. A lack of fatal messages is not proof of completion."}


def completion_evidence(return_code, stdout, job, files_current_and_nonempty, diagnostics):
    token = re.compile(r"\bAbaqus\s+JOB\s+" + re.escape(job) + r"\s+COMPLETED\b", re.I)
    return bool(return_code == 0 and token.search(stdout) and files_current_and_nonempty
                and not diagnostics["fatal"])


def stagnation(samples, time_period_s, window=100, min_window_wall_s=300,
               max_progress_fraction=1e-4):
    """samples = successful increments only, each with step_id, step_time_s, wall_s.

    Defaults are initial engineering proposals, not universal Abaqus tolerances.
    A controller must observe two independent windows before applying its stop policy.
    """
    if time_period_s <= 0 or len(samples) < window:
        return False
    selected = samples[-window:]
    if len({s["step_id"] for s in selected}) != 1:
        return False
    elapsed = selected[-1]["wall_s"] - selected[0]["wall_s"]
    delta = selected[-1]["step_time_s"] - selected[0]["step_time_s"]
    return elapsed >= min_window_wall_s and 0 <= delta / time_period_s < max_progress_fraction
