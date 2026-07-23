# Scripts

Reusable project maintenance scripts only.

- `check_architecture_sizes.py` — architecture fitness check used by pre-commit and CI.
- `collect_release_evidence.py` — tamper-evident release evidence bundle (does not declare PASS).
- `generate_sbom.py` — CycloneDX SBOM for backend, frontend, container Dockerfiles; optional `--image` Syft/Trivy layer SBOM (F-10).
- `generate_release_checksums.py` — SHA-256 checksum files for release artifacts (F-10).
- `generate_provenance.py` — in-toto/SLSA provenance inventory; local unsigned, CI records GitHub attestation metadata (F-10).
- `create_mega_pipeline.py` — seeds a large Studio pipeline scenario.
- `create_pipeline.sql` — SQL seed for a demo pipeline.
- `extract_i18n.py` — extracts frontend translations from `frontend/src/lib/i18n.tsx` into locale JSON files.

One-off patch/fix scripts were removed from this folder.
