# Briefing

- Purpose: Automate running a Pacman multiagent autograder on student submissions and uploading scores/comments to Canvas.
- Current scope:
  - Student submissions in `assignments/ma/` (Canvas download format filenames)
  - Framework (autograder) in `frameworks/multiagent/`
  - `scripts/run_autograder.py`: copies each submission, runs autograder, parses Total: X/Y, saves to results JSON, resumes on crash
  - `scripts/upload_grades.py`: uploads grades to Canvas; attaches autograder output as comment for scores below max
  - Slash command `/run-autograder` orchestrates both scripts
  - Canvas course 1902104, assignment 11224139
  - Token at ~/local/bin/token-canvas.txt
- Key decisions:
  - Canvas user ID is the second numeric segment of the submission filename (third if LATE prefix present)
  - Results saved to `results/ma_results.json` after each student for crash safety
  - Timeout per student: 60s (configurable)
  - multiAgents.py is deleted from framework dir after each student run
- Non-goals: No AI-generated feedback or sample solutions; no grade breakdown per question.
