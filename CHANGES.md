# Changes

Format: `YYYY-MM-DD [type] description` (max 200 chars). Types: decision, plan, doc, scope, code, note.

2026-05-08 [note] Initialized.
2026-05-08 [plan] Designed autograder pipeline: run_autograder.py + upload_grades.py + /run-autograder slash command for Canvas MA assignment grading.
2026-05-08 [code] Added config file support: configs/ma.json + scripts/config_loader.py; both scripts accept --config to load assignment/canvas settings.
2026-05-08 [doc] Wrote README.md covering architecture, setup, usage, flags, and results JSON format.
2026-05-08 [scope] Added zip submission support for reinforcement assignment; configs/re.json, updated run_autograder.py with stage_zip handling nested dirs and __MACOSX.
