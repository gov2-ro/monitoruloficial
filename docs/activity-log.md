# Activity Log

## Docs / repo hygiene

### 2026-06-25 — Refresh docs after monorepo extraction
- Rewrote `CLAUDE.md` to hold only the general approach (orientation + the two operational
  footguns: run-from-root, no requirements file) plus persona / coding principles / project
  tracking. Moved all architecture, usage, scripts, data-model, and conventions detail into
  `readme.md`.
- Fixed post-move stale paths in `mof-convert-txt.py` and `toolbench/cleanup-p3folder.py`
  (were `../../data/mo/...`; now repo-root-relative `data/...`).
- Removed cross-project leftovers from the docs (full-stack persona, non-existent
  "site specific readme / config" references, typos).
- Why: repo was extracted from a larger monorepo, so paths and docs no longer matched reality.
