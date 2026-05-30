#!/usr/bin/env python3
"""
run_autograder.py

Copies each student submission into the framework directory, runs the autograder,
parses the score, and writes results to a JSON file.

Supports two submission types (set in the config file):
  single_file  - student submits one .py file (e.g. multiAgents.py)
  zip          - student submits a .zip containing multiple .py files

Supports resume: students already recorded in the results file are skipped.

Usage:
    python scripts/run_autograder.py --config configs/ma.json [options]

Options:
    --config            Path to JSON config file
    --assignments-dir   Directory containing student submission files
    --framework-dir     Directory containing autograder framework
    --results-file      Path to JSON results file
    --timeout           Seconds before killing autograder per student (default: 60)
    --submission-type   "single_file" or "zip"
    --target-file       Filename to use inside framework for single_file submissions
    --submission-files  Comma-separated list of .py filenames to extract from zip
    --student           Only run for a single student name (optional, for debugging)
    --force             Re-run even if student already has a result
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from config_loader import apply_config_defaults, load_config


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

def parse_submission_filename(filename: str) -> dict | None:
    """
    Parse a Canvas submission filename into components.

    Expected formats:
        name_CANVASID_SUBMISSIONID_originalname.ext
        name_LATE_CANVASID_SUBMISSIONID_originalname.ext
        name_LATE_CANVASID_SUBMISSIONID_originalname-1.ext  (resubmission)

    Returns a dict with keys: student_name, canvas_user_id, submission_id, is_late
    Returns None if the filename does not match.
    """
    stem = Path(filename).stem  # strip extension
    # Remove trailing resubmission suffix like -1, -2
    stem = re.sub(r"-\d+$", "", stem)
    parts = stem.split("_")

    if len(parts) < 4:
        return None

    if parts[1].upper() == "LATE":
        if len(parts) < 5:
            return None
        return {
            "student_name": parts[0],
            "is_late": True,
            "canvas_user_id": parts[2],
            "submission_id": parts[3],
        }
    else:
        return {
            "student_name": parts[0],
            "is_late": False,
            "canvas_user_id": parts[1],
            "submission_id": parts[2],
        }


def collect_submissions(assignments_dir: Path, submission_type: str) -> list[dict]:
    """
    Return a list of parsed submission dicts for all matching files in assignments_dir.
    Each dict also includes 'filepath' and 'filename'.
    Skips files that cannot be parsed.
    """
    ext = ".zip" if submission_type == "zip" else ".py"
    submissions = []
    for f in sorted(assignments_dir.iterdir()):
        if f.suffix.lower() != ext:
            continue
        info = parse_submission_filename(f.name)
        if info is None:
            print(f"  [WARN] Could not parse filename, skipping: {f.name}")
            continue
        info["filepath"] = str(f)
        info["filename"] = f.name
        submissions.append(info)
    return submissions


# ---------------------------------------------------------------------------
# File staging: copy/extract into framework, return list of paths to clean up
# ---------------------------------------------------------------------------

def stage_single_file(student: dict, framework_dir: Path, target_file: str) -> list[Path]:
    """Copy a single .py submission into the framework as target_file."""
    target = framework_dir / target_file
    shutil.copy2(student["filepath"], target)
    return [target]


def stage_zip(student: dict, framework_dir: Path, submission_files: list[str]) -> list[Path]:
    """
    Extract target .py files from a zip into framework_dir.

    Handles:
      - Files at the zip root
      - Files inside a single subdirectory (common when students zip a folder)
      - __MACOSX metadata entries (skipped)
      - .DS_Store files (skipped)

    Returns the list of files written to framework_dir.
    """
    wanted = set(submission_files)
    staged = []
    missing = set(submission_files)

    with zipfile.ZipFile(student["filepath"]) as zp:
        for entry in zp.namelist():
            # Skip macOS metadata
            if "__MACOSX" in entry or entry.endswith(".DS_Store"):
                continue
            basename = Path(entry).name
            if basename in wanted:
                data = zp.read(entry)
                target = framework_dir / basename
                target.write_bytes(data)
                staged.append(target)
                missing.discard(basename)

    if missing:
        print(f"    [WARN] Missing from zip for {student['student_name']}: {sorted(missing)}")

    return staged


def stage_submission(student: dict, framework_dir: Path, submission_type: str,
                     target_file: str, submission_files: list[str]) -> list[Path]:
    """Stage student files into framework_dir. Returns list of paths to clean up."""
    if submission_type == "zip":
        return stage_zip(student, framework_dir, submission_files)
    else:
        return stage_single_file(student, framework_dir, target_file)


def cleanup_staged(staged: list[Path]) -> None:
    for path in staged:
        if path.exists():
            path.unlink()


# ---------------------------------------------------------------------------
# Autograder execution
# ---------------------------------------------------------------------------

SCORE_PATTERN = re.compile(r"Total:\s*(\d+)/(\d+)", re.IGNORECASE)


def parse_score(output: str) -> tuple[int | None, int | None]:
    """Extract (earned, total) from autograder output. Returns (None, None) if not found."""
    match = SCORE_PATTERN.search(output)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def run_autograder(student: dict, framework_dir: Path, timeout: int,
                   submission_type: str, target_file: str,
                   submission_files: list[str]) -> dict:
    """
    Stage student files, run autograder, parse result, clean up.

    Returns a result dict with keys:
        student_name, canvas_user_id, is_late, filename,
        score, max_score, output, status, graded_at
    where status is one of: "graded", "timeout", "error"
    """
    staged = []
    output = ""
    status = "error"
    score = None
    max_score = None

    try:
        staged = stage_submission(student, framework_dir, submission_type,
                                  target_file, submission_files)
        result = subprocess.run(
            [sys.executable, "autograder.py"],
            cwd=str(framework_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        score, max_score = parse_score(output)
        if score is not None:
            status = "graded"
        else:
            status = "error"
            print(f"    [WARN] Could not find 'Total:' in output for {student['student_name']}")
    except subprocess.TimeoutExpired:
        status = "timeout"
        output = f"[TIMEOUT after {timeout}s]"
        print(f"    [TIMEOUT] {student['student_name']} exceeded {timeout}s")
    except Exception as e:
        status = "error"
        output = f"[ERROR] {e}"
        print(f"    [ERROR] {student['student_name']}: {e}")
    finally:
        cleanup_staged(staged)

    return {
        "student_name": student["student_name"],
        "canvas_user_id": student["canvas_user_id"],
        "is_late": student["is_late"],
        "filename": student["filename"],
        "score": score,
        "max_score": max_score,
        "output": output,
        "status": status,
        "graded_at": datetime.now().isoformat(),
        "upload_status": None,
    }


# ---------------------------------------------------------------------------
# Results file I/O
# ---------------------------------------------------------------------------

def load_results(results_file: Path) -> dict:
    """Load existing results JSON, or return empty structure."""
    if results_file.exists():
        with open(results_file) as f:
            return json.load(f)
    return {"students": {}}


def save_results(results: dict, results_file: Path) -> None:
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run autograder for all student submissions")
    parser.add_argument("--config", default=None, help="Path to JSON config file (e.g. configs/ma.json)")
    parser.add_argument("--assignments-dir", default=None, help="Folder with student submission files")
    parser.add_argument("--framework-dir", default=None, help="Folder with autograder.py")
    parser.add_argument("--results-file", default=None, help="JSON file to store results")
    parser.add_argument("--timeout", type=int, default=None, help="Seconds per student before timeout")
    parser.add_argument("--submission-type", default=None, choices=["single_file", "zip"],
                        help="How student files are packaged")
    parser.add_argument("--target-file", default=None,
                        help="Filename to use in framework dir (single_file mode)")
    parser.add_argument("--submission-files", default=None,
                        help="Comma-separated .py files to extract from zip (zip mode)")
    parser.add_argument("--student", default=None, help="Only run for this student name (debugging)")
    parser.add_argument("--force", action="store_true", help="Re-run even if student already has a result")
    args = parser.parse_args()

    if args.config:
        apply_config_defaults(args, load_config(args.config))

    # Final fallback defaults
    if args.assignments_dir is None:
        args.assignments_dir = "assignments/ma"
    if args.framework_dir is None:
        args.framework_dir = "frameworks/multiagent"
    if args.results_file is None:
        args.results_file = "results/ma_results.json"
    if args.timeout is None:
        args.timeout = 60
    if args.submission_type is None:
        args.submission_type = "single_file"
    if args.target_file is None:
        args.target_file = "multiAgents.py"

    # submission_files comes from config as a list, or CLI as a comma-separated string
    submission_files: list[str] = []
    if args.submission_files:
        if isinstance(args.submission_files, list):
            submission_files = args.submission_files
        else:
            submission_files = [f.strip() for f in args.submission_files.split(",")]

    assignments_dir = Path(args.assignments_dir)
    framework_dir = Path(args.framework_dir)
    results_file = Path(args.results_file)

    # Validate
    if not assignments_dir.is_dir():
        print(f"ERROR: assignments dir not found: {assignments_dir}")
        sys.exit(1)
    if not framework_dir.is_dir():
        print(f"ERROR: framework dir not found: {framework_dir}")
        sys.exit(1)
    if not (framework_dir / "autograder.py").exists():
        print(f"ERROR: autograder.py not found in {framework_dir}")
        sys.exit(1)
    if args.submission_type == "zip" and not submission_files:
        print("ERROR: --submission-files required for zip submission type")
        sys.exit(1)

    submissions = collect_submissions(assignments_dir, args.submission_type)
    if args.student:
        submissions = [s for s in submissions if s["student_name"] == args.student]
        if not submissions:
            print(f"ERROR: No submission found for student '{args.student}'")
            sys.exit(1)

    results = load_results(results_file)
    students = results["students"]

    total = len(submissions)
    skipped = 0
    ran = 0
    errors = 0

    print(f"Found {total} submissions in {assignments_dir} (type: {args.submission_type})")
    print(f"Results file: {results_file}")
    print(f"Timeout: {args.timeout}s per student")
    print("-" * 60)

    for i, student in enumerate(submissions, 1):
        name = student["student_name"]
        key = student["canvas_user_id"]

        if not args.force and key in students and students[key].get("status") in ("graded", "timeout"):
            score = students[key].get("score")
            max_s = students[key].get("max_score")
            print(f"[{i}/{total}] SKIP {name} (already {students[key]['status']}: {score}/{max_s})")
            skipped += 1
            continue

        print(f"[{i}/{total}] Running {name} ({student['filename']}) ...", end=" ", flush=True)
        result = run_autograder(
            student, framework_dir, args.timeout,
            args.submission_type, args.target_file, submission_files,
        )
        students[key] = result

        if result["status"] == "graded":
            print(f"{result['score']}/{result['max_score']}")
            ran += 1
        elif result["status"] == "timeout":
            print("TIMEOUT")
            errors += 1
        else:
            print("ERROR")
            errors += 1

        # Save after every student so a crash doesn't lose progress
        save_results(results, results_file)

    print("-" * 60)
    print(f"Done. Ran: {ran}, Skipped: {skipped}, Errors/Timeouts: {errors}")
    print(f"Results saved to: {results_file}")


if __name__ == "__main__":
    main()
