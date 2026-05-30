# run-student-assignments

Automates running a Python autograder on Canvas student submissions and uploading scores (and output comments) back to Canvas.

---

## Architecture

```
run-student-assignments/
  configs/              Assignment-specific config files
    ma.json             Multiagent assignment (single .py file per student)
    re.json             Reinforcement assignment (zip file per student)
  assignments/          Student submission folders (one per assignment)
    ma/                 Multiagent submissions downloaded from Canvas
    re/                 Reinforcement submissions downloaded from Canvas
  frameworks/           Autograder framework folders (one per assignment)
    multiagent/         Pacman multiagent autograder (autograder.py lives here)
    reinforcement/      Pacman reinforcement autograder (autograder.py lives here)
  results/              Output JSON files written by run_autograder.py
    ma_results.json     Results for the multiagent assignment
    re_results.json     Results for the reinforcement assignment
  scripts/
    config_loader.py    Shared config file loader
    run_autograder.py   Grades all students; writes results JSON
    upload_grades.py    Reads results JSON; uploads grades to Canvas
  venv/                 Python virtual environment (requests installed here)
```

### How it works

1. `run_autograder.py` scans the submissions folder for student files (`.py` or `.zip` depending on `submission_type`).
2. For each student it stages their files into the framework directory, runs `python autograder.py` with a timeout, parses the `Total: X/Y` line from output, and saves the result to the JSON results file. All staged files are deleted after each run.
3. For zip submissions, the script extracts only the target `.py` files, handling nested subdirectories and skipping macOS metadata (`__MACOSX`).
4. Results are saved after each student, so the script can be interrupted and resumed safely.
5. `upload_grades.py` reads the results JSON and PUTs each grade to the Canvas API. For students who scored below the maximum, the full autograder output is included as a text comment visible in SpeedGrader.

### Submission filename format

Canvas downloads submissions with filenames in this format:

```
studentname_CANVASID_SUBMISSIONID_originalname.py
studentname_LATE_CANVASID_SUBMISSIONID_originalname.py   (late submission)
studentname_LATE_CANVASID_SUBMISSIONID_originalname-1.py (resubmission)
```

The Canvas user ID (second numeric segment) is used as the key for the Canvas grade upload API.

---

## Setup

```bash
python3 -m venv venv
venv/bin/pip install requests
```

Place your Canvas API token in `~/local/bin/token-canvas.txt` (one line, no extra whitespace).

---

## Config files

Each assignment has a JSON config in `configs/`. Copy and edit to add a new assignment.

```json
{
  "assignment": {
    "name":            "Multiagent",
    "assignments_dir": "assignments/ma",
    "framework_dir":   "frameworks/multiagent",
    "results_file":    "results/ma_results.json",
    "timeout":         60
  },
  "canvas": {
    "server":        "https://canvas.uw.edu",
    "course_id":     "1902104",
    "assignment_id": "11224139",
    "token_file":    "~/local/bin/token-canvas.txt"
  }
}
```

| Field | Description |
|---|---|
| `assignments_dir` | Folder containing student submission files downloaded from Canvas |
| `framework_dir` | Folder containing `autograder.py` and supporting files |
| `results_file` | Path where the results JSON is written |
| `timeout` | Seconds before killing a student's autograder run |
| `submission_type` | `"single_file"` (one .py) or `"zip"` (zip containing multiple .py files) |
| `target_file` | (single_file only) Filename to use inside the framework dir, e.g. `"multiAgents.py"` |
| `submission_files` | (zip only) List of .py filenames to extract from the zip, e.g. `["valueIterationAgents.py", "qlearningAgents.py", "analysis.py"]` |
| `canvas.server` | Canvas base URL |
| `canvas.course_id` | Found in the Canvas course URL |
| `canvas.assignment_id` | Found in the Canvas assignment URL |
| `canvas.token_file` | Path to file containing the Canvas API token |

---

## Usage

### Run everything for an assignment

```bash
venv/bin/python scripts/run_autograder.py --config configs/ma.json
venv/bin/python scripts/upload_grades.py  --config configs/ma.json
```

If interrupted, re-run the same commands. Already-graded students and already-uploaded grades are skipped automatically.

### Test a single student before running all

```bash
# Grade one student only (no Canvas interaction)
venv/bin/python scripts/run_autograder.py --config configs/ma.json --student yookhyobin

# Preview what would be uploaded (no changes to Canvas)
venv/bin/python scripts/upload_grades.py --config configs/ma.json --student yookhyobin --dry-run

# Upload for real for that one student
venv/bin/python scripts/upload_grades.py --config configs/ma.json --student yookhyobin
```

Then spot-check the student in Canvas SpeedGrader before running all.

### Slash command

From within Claude Code:

```
/run-autograder configs/ma.json
```

This runs both scripts in order and reports a summary.

### Re-run a student

Use `--force` to overwrite an existing result or re-upload an existing grade:

```bash
venv/bin/python scripts/run_autograder.py --config configs/ma.json --student yookhyobin --force
venv/bin/python scripts/upload_grades.py  --config configs/ma.json --student yookhyobin --force
```

---

## Script reference

### `scripts/run_autograder.py`

| Flag | Default | Description |
|---|---|---|
| `--config` | (none) | JSON config file |
| `--assignments-dir` | `assignments/ma` | Folder with student submission files |
| `--framework-dir` | `frameworks/multiagent` | Folder with `autograder.py` |
| `--results-file` | `results/ma_results.json` | Output JSON |
| `--timeout` | `60` | Seconds per student |
| `--submission-type` | `single_file` | `single_file` or `zip` |
| `--target-file` | `multiAgents.py` | Filename to use in framework (single_file mode) |
| `--submission-files` | (none) | Comma-separated .py files to extract (zip mode) |
| `--student` | (all) | Run only this student name |
| `--force` | off | Re-run already-graded students |

### `scripts/upload_grades.py`

| Flag | Default | Description |
|---|---|---|
| `--config` | (none) | JSON config file |
| `--results-file` | `results/ma_results.json` | Input JSON |
| `--course-id` | `1902104` | Canvas course ID |
| `--assignment-id` | `11224139` | Canvas assignment ID |
| `--canvas-server` | `https://canvas.uw.edu` | Canvas base URL |
| `--token-file` | `~/local/bin/token-canvas.txt` | API token file |
| `--student` | (all) | Upload only this student name |
| `--dry-run` | off | Print actions without uploading |
| `--force` | off | Re-upload already-uploaded grades |

---

## Results JSON format

`results/ma_results.json` records one entry per student keyed by Canvas user ID:

```json
{
  "students": {
    "4458188": {
      "student_name":   "yookhyobin",
      "canvas_user_id": "4458188",
      "is_late":        false,
      "filename":       "yookhyobin_4458188_149334121_multiAgents.py",
      "score":          22,
      "max_score":      25,
      "output":         "...",
      "status":         "graded",
      "graded_at":      "2026-05-08T10:00:00",
      "upload_status":  "success"
    }
  }
}
```

| Field | Values | Description |
|---|---|---|
| `status` | `graded`, `timeout`, `error` | Autograder run outcome |
| `upload_status` | `null`, `success`, `error:...`, `dry_run` | Canvas upload outcome |
