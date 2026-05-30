"""
config_loader.py

Loads a JSON config file and merges it with argparse defaults.
Config values serve as defaults; explicit CLI arguments override them.

Config file format:
{
  "assignment": {
    "name":             "...",
    "assignments_dir":  "...",
    "framework_dir":    "...",
    "results_file":     "...",
    "timeout":          60,
    "submission_type":  "single_file" | "zip",
    "target_file":      "multiAgents.py",          (single_file only)
    "submission_files": ["a.py", "b.py", "c.py"]   (zip only)
  },
  "canvas": {
    "server":        "https://canvas.uw.edu",
    "course_id":     "...",
    "assignment_id": "...",
    "token_file":    "..."
  }
}
"""

import json
import sys
from pathlib import Path


def load_config(config_path: str) -> dict:
    """Load and return parsed JSON config. Exits on missing file or bad JSON."""
    path = Path(config_path)
    if not path.exists():
        print(f"ERROR: Config file not found: {path}")
        sys.exit(1)
    with open(path) as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON in {path}: {e}")
            sys.exit(1)


def apply_config_defaults(args, config: dict) -> None:
    """
    Fill in argparse Namespace fields from config where the CLI arg was not set (i.e. is None).

    Mapping from config keys to argparse attribute names:
      assignment.assignments_dir  -> args.assignments_dir
      assignment.framework_dir    -> args.framework_dir
      assignment.results_file     -> args.results_file
      assignment.timeout          -> args.timeout
      assignment.submission_type  -> args.submission_type
      assignment.target_file      -> args.target_file
      assignment.submission_files -> args.submission_files
      canvas.server               -> args.canvas_server
      canvas.course_id            -> args.course_id
      canvas.assignment_id        -> args.assignment_id
      canvas.token_file           -> args.token_file
    """
    assignment = config.get("assignment", {})
    canvas = config.get("canvas", {})

    mapping = {
        "assignments_dir":  assignment.get("assignments_dir"),
        "framework_dir":    assignment.get("framework_dir"),
        "results_file":     assignment.get("results_file"),
        "timeout":          assignment.get("timeout"),
        "submission_type":  assignment.get("submission_type"),
        "target_file":      assignment.get("target_file"),
        "submission_files": assignment.get("submission_files"),
        "canvas_server":    canvas.get("server"),
        "course_id":        canvas.get("course_id"),
        "assignment_id":    canvas.get("assignment_id"),
        "token_file":       canvas.get("token_file"),
    }

    for attr, value in mapping.items():
        # Only apply if the arg is currently None (i.e. not explicitly set by user)
        if value is not None and getattr(args, attr, None) is None:
            setattr(args, attr, value)
