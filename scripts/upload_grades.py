#!/usr/bin/env python3
"""
upload_grades.py

Reads a results JSON file produced by run_autograder.py and uploads each
student's grade (and autograder output as a comment, if score < max) to Canvas.

Supports resume: students whose upload_status is already "success" are skipped.

Usage:
    python scripts/upload_grades.py [options]

Options:
    --results-file      Path to JSON results file (default: results/ma_results.json)
    --course-id         Canvas course ID (default: 1902104)
    --assignment-id     Canvas assignment ID (default: 11224139)
    --canvas-server     Canvas base URL (default: https://canvas.uw.edu)
    --token-file        Path to file containing Canvas API token
                        (default: ~/local/bin/token-canvas.txt)
    --dry-run           Print what would be uploaded without actually uploading
    --force             Re-upload even if upload_status is already "success"
    --student           Only upload for this student name (debugging)
"""

import argparse
import json
import sys
from pathlib import Path

import requests

from config_loader import apply_config_defaults, load_config


# ---------------------------------------------------------------------------
# Canvas API helpers
# ---------------------------------------------------------------------------

def load_token(token_file: Path) -> str:
    """Read and return the Canvas API token, stripping whitespace."""
    path = Path(token_file).expanduser()
    if not path.exists():
        print(f"ERROR: Token file not found: {path}")
        sys.exit(1)
    return path.read_text().strip()


def canvas_put(url: str, token: str, data: dict, dry_run: bool) -> requests.Response | None:
    """
    Send a PUT request to the Canvas API.
    Returns the Response on success, or None on error.
    In dry_run mode, prints the request and returns None.
    """
    if dry_run:
        print(f"    [DRY RUN] PUT {url}")
        print(f"    [DRY RUN] data={data}")
        return None

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.put(url, headers=headers, data=data, timeout=30)
    return response


def upload_grade(
    canvas_server: str,
    course_id: str,
    assignment_id: str,
    canvas_user_id: str,
    score: int | None,
    max_score: int | None,
    autograder_output: str,
    token: str,
    dry_run: bool,
) -> str:
    """
    Upload a grade (and optional comment) for one student.

    Returns "success", "skipped" (score unavailable), or "error:<message>".
    """
    if score is None:
        return "skipped:no_score"

    url = (
        f"{canvas_server}/api/v1/courses/{course_id}"
        f"/assignments/{assignment_id}/submissions/{canvas_user_id}"
    )

    # Build payload: grade + optional comment in a single PUT
    data: dict = {"submission[posted_grade]": str(score)}
    if max_score is not None and score < max_score:
        data["comment[text_comment]"] = autograder_output

    response = canvas_put(url, token, data, dry_run)

    if dry_run:
        return "dry_run"

    if response is None:
        return "error:no_response"

    if response.status_code in (200, 201):
        return "success"

    return f"error:HTTP_{response.status_code}:{response.text[:200]}"


# ---------------------------------------------------------------------------
# Results file I/O
# ---------------------------------------------------------------------------

def load_results(results_file: Path) -> dict:
    if not results_file.exists():
        print(f"ERROR: Results file not found: {results_file}")
        sys.exit(1)
    with open(results_file) as f:
        return json.load(f)


def save_results(results: dict, results_file: Path) -> None:
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Upload autograder results to Canvas")
    parser.add_argument("--config", default=None, help="Path to JSON config file (e.g. configs/ma.json)")
    parser.add_argument("--results-file", default=None)
    parser.add_argument("--course-id", default=None)
    parser.add_argument("--assignment-id", default=None)
    parser.add_argument("--canvas-server", default=None)
    parser.add_argument("--token-file", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Do not actually upload")
    parser.add_argument("--force", action="store_true", help="Re-upload already-uploaded grades")
    parser.add_argument("--student", default=None, help="Only upload for this student name")
    args = parser.parse_args()

    if args.config:
        apply_config_defaults(args, load_config(args.config))

    # Final fallback defaults (if no config and no CLI arg)
    if args.results_file is None:
        args.results_file = "results/ma_results.json"
    if args.course_id is None:
        args.course_id = "1902104"
    if args.assignment_id is None:
        args.assignment_id = "11224139"
    if args.canvas_server is None:
        args.canvas_server = "https://canvas.uw.edu"
    if args.token_file is None:
        args.token_file = "~/local/bin/token-canvas.txt"

    results_file = Path(args.results_file)
    results = load_results(results_file)
    students = results["students"]

    token = load_token(args.token_file) if not args.dry_run else "DRY_RUN_TOKEN"

    total = len(students)
    uploaded = 0
    skipped = 0
    errors = 0

    print(f"Canvas: {args.canvas_server}/courses/{args.course_id}/assignments/{args.assignment_id}")
    print(f"Results file: {results_file}")
    if args.dry_run:
        print("DRY RUN mode: no changes will be made to Canvas")
    print("-" * 60)

    entries = list(students.items())
    if args.student:
        entries = [(k, v) for k, v in entries if v.get("student_name") == args.student]
        if not entries:
            print(f"ERROR: No result found for student '{args.student}'")
            sys.exit(1)

    for i, (canvas_user_id, data) in enumerate(entries, 1):
        name = data.get("student_name", canvas_user_id)
        status = data.get("status")
        upload_status = data.get("upload_status")

        # Skip if already successfully uploaded, unless --force
        if not args.force and upload_status == "success":
            score = data.get("score")
            max_s = data.get("max_score")
            print(f"[{i}/{total}] SKIP {name} (already uploaded: {score}/{max_s})")
            skipped += 1
            continue

        # Skip if autograder did not produce a score
        if status not in ("graded", "timeout", "error"):
            print(f"[{i}/{total}] SKIP {name} (no autograder result recorded)")
            skipped += 1
            continue

        score = data.get("score")
        max_score = data.get("max_score")
        output = data.get("output", "")
        late_tag = " [LATE]" if data.get("is_late") else ""

        print(f"[{i}/{total}] Uploading {name}{late_tag}: {score}/{max_score} ...", end=" ", flush=True)

        result = upload_grade(
            canvas_server=args.canvas_server,
            course_id=args.course_id,
            assignment_id=args.assignment_id,
            canvas_user_id=canvas_user_id,
            score=score,
            max_score=max_score,
            autograder_output=output,
            token=token,
            dry_run=args.dry_run,
        )

        data["upload_status"] = result
        print(result)

        if result in ("success", "dry_run"):
            uploaded += 1
        elif result.startswith("skipped"):
            skipped += 1
        else:
            errors += 1

        # Persist after every student
        if not args.dry_run:
            save_results(results, results_file)

    print("-" * 60)
    print(f"Done. Uploaded: {uploaded}, Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    main()
