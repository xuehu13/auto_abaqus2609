# -*- coding: utf-8 -*-

"""Step 07 — Automatically classify the Abaqus Data-Check result.

Purpose
-------
Scan Abaqus .dat/.msg (and optional .sta) for fatal mesh-related messages such as
ERROR, distortion, high aspect ratio, shell-normal, negative-area, or zero-area
problems.  Missing .sta is allowed for a pure datacheck run.

Input : Abaqus files in cases/<case>/abaqus_meshcheck
Output: <case>_meshcheck_datacheck_report.json
"""
import json
import re


from meshlib.config import CFG

JOB = CFG.meshcheck_job
WORKDIR = CFG.abaqus_dir
REPORT = WORKDIR / f"{JOB}_datacheck_report.json"
FILES = {
    "dat": WORKDIR / f"{JOB}.dat",
    "msg": WORKDIR / f"{JOB}.msg",
    "sta": WORKDIR / f"{JOB}.sta",
}


# Messages that are genuinely important for automatic FE jobs.
PATTERNS = {

    "error":
        re.compile(
            r"\bERROR\b|\*\*\*ERROR",
            re.IGNORECASE
        ),

    "warning":
        re.compile(
            r"\bWARNING\b|\*\*\*WARNING",
            re.IGNORECASE
        ),

    "distorted":
        re.compile(
            r"DISTORT",
            re.IGNORECASE
        ),

    "aspect_ratio":
        re.compile(
            r"ASPECT\s+RATIO",
            re.IGNORECASE
        ),

    "shell_normal":
        re.compile(
            r"SHELL\s+NORMAL|ErrElemShellNormal",
            re.IGNORECASE
        ),

    "negative_area":
        re.compile(
            r"NEGATIVE\s+AREA",
            re.IGNORECASE
        ),

    "zero_area":
        re.compile(
            r"ZERO\s+AREA",
            re.IGNORECASE
        ),
}


def scan_file(path):

    result = {
        key: []
        for key in PATTERNS
    }

    if not path.exists():

        return result


    text = path.read_text(
        encoding="utf-8",
        errors="ignore"
    )


    for line_number, line in enumerate(
        text.splitlines(),
        start=1
    ):

        for key, pattern in PATTERNS.items():

            if pattern.search(line):

                result[key].append(
                    {
                        "line":
                            line_number,

                        "text":
                            line.strip(),
                    }
                )

    return result


def main():

    print()
    print(
        "=============================================="
    )

    print(
        "STEP 07 - ABAQUS DATACHECK VALIDATOR"
    )

    print(
        "=============================================="
    )


    scans = {}

    # --------------------------------------------------------
    # Abaqus datacheck file policy
    #
    # .dat and .msg are required for our automatic validator.
    #
    # .sta is OPTIONAL here:
    # Abaqus normally writes increment summaries to .sta during
    # an actual analysis/continue/recover run. A pure datacheck
    # run does not necessarily create it.
    # --------------------------------------------------------

    required_suffixes = (
        "dat",
        "msg",
    )

    optional_suffixes = (
        "sta",
    )


    missing = []

    optional_missing = []


    for suffix, path in FILES.items():

        if not path.exists():

            if suffix in required_suffixes:

                missing.append(
                    str(path)
                )

            elif suffix in optional_suffixes:

                optional_missing.append(
                    str(path)
                )


        scans[suffix] = scan_file(
            path
        )


    counts = {
        key: 0
        for key in PATTERNS
    }


    for file_result in scans.values():

        for key in counts:

            counts[key] += len(
                file_result[key]
            )


    fatal_count = (
        counts["error"]
        +
        counts["distorted"]
        +
        counts["aspect_ratio"]
        +
        counts["shell_normal"]
        +
        counts["negative_area"]
        +
        counts["zero_area"]
    )


    # Warnings are reported separately.
    # Not every Abaqus WARNING means the mesh must be rejected.
    pass_status = bool(

        len(missing) == 0

        and

        fatal_count == 0
    )


    print()

    print(
        "Files:"
    )


    for suffix, path in FILES.items():

        print(
            f"  {suffix:<4} : "
            f"{path.exists()}  "
            f"{path}"
        )


    if optional_missing:

        print()

        print(
            "Optional files not created:"
        )

        for item in optional_missing:

            print(
                " ",
                item
            )

        print(
            "  -> This is normal for a pure Abaqus datacheck run."
        )


    print()

    print(
        "Detected messages:"
    )


    for key, value in counts.items():

        print(
            f"  {key:<15} = "
            f"{value}"
        )


    print()

    print(
        "fatal count =",
        fatal_count
    )


    report = {

        "job":
            JOB,

        "files":
            {
                key:
                    str(value)

                for key, value
                in FILES.items()
            },

        "missing_required_files":
            missing,

        "missing_optional_files":
            optional_missing,

        "counts":
            counts,

        "messages":
            scans,

        "fatal_count":
            fatal_count,

        "pass":
            pass_status,
    }


    with REPORT.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )


    print()

    print(
        "Report:"
    )

    print(
        " ",
        REPORT
    )


    print()

    print(
        "=============================================="
    )


    if pass_status:

        print(
            "ABAQUS DATACHECK STATUS: PASS"
        )

    else:

        print(
            "ABAQUS DATACHECK STATUS: FAIL"
        )


    print(
        "=============================================="
    )


    if not pass_status:

        raise SystemExit(3)


if __name__ == "__main__":

    main()
