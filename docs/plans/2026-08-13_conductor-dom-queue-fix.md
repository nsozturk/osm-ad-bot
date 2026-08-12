# Conductor DOM Queue Fix Checklist

- [x] Map the fatal traceback to the exact DOM queue access.
- [x] Confirm all ways the page-scoped queue can disappear.
- [x] Make missing/invalid queue state non-fatal and reinstall its observer.
- [x] Prevent duplicate observer installation during self-healing.
- [x] Add targeted tests for empty, populated, missing, replaced-body, and transient-error states.
- [x] Run syntax and regression checks without starting a live ad session.
