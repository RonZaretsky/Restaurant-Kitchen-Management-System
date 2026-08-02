# secrets/

Local-only directory for anything that must never reach the public GitHub remote: API keys (OpenAI, etc.), and restricted/private source material (e.g. course PDFs marked "do not distribute", correspondence with the instructor).

This directory is gitignored except for this README. Nothing else placed here is committed — verify with `git status` before committing if you're unsure.

Currently holds:
- `source-course-guidelines.md` — verbatim extract of the course's final-project guidelines PDF (watermarked, restricted).
- `source-proposal.md` — verbatim copy of the approved project-proposal email to the instructor.

Both were used as source material during PRD Discovery (`_bmad-output/planning-artifacts/prds/.../`); the PRD and addendum reference them by filename only, not by reproducing their content.
