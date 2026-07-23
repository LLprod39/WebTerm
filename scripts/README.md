# Scripts

Reusable project maintenance scripts only.

- `check_architecture_sizes.py` — architecture fitness check used by pre-commit and CI.
- `collect_release_evidence.py` — tamper-evident release evidence bundle (does not declare PASS).
- `generate_sbom.py` — CycloneDX SBOM for backend, frontend, container Dockerfiles; optional `--image` Syft/Trivy layer SBOM (F-10).
- `generate_release_checksums.py` — SHA-256 checksum files for release artifacts (F-10).
- `generate_provenance.py` — in-toto/SLSA provenance inventory; local unsigned, CI records GitHub attestation metadata (F-10).
- `github_governance.py` — audit/apply branch protection, F-11 clock start, unique-SHA sync, break-glass log (F-11).
- `github_governance_io.py` — GitHub/git I/O and break-glass log helpers used by `github_governance.py` (F-11).
- `ci_stability_clock.py` — pure 14-day / 30 unique-SHA gate evaluation and ledger math (F-11).
- `create_mega_pipeline.py` — seeds a large Studio pipeline scenario.
- `create_pipeline.sql` — SQL seed for a demo pipeline.
- `extract_i18n.py` — extracts frontend translations from `frontend/src/lib/i18n.tsx` into locale JSON files.

One-off patch/fix scripts were removed from this folder.
