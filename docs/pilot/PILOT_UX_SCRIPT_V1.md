# WebTerm pilot UX script v1

Status: ready for execution; no participant results have been recorded.

## Goal

Measure whether a new operator can understand the product within 30–60 seconds and complete the primary flow without coaching: install/login, add a server, connect, run one guarded action and find the audit record.

## Participants and environment

- Minimum: 10 participants who have not used this build.
- Use the same immutable test commit and a reset fixture for every participant.
- Do not expose production credentials or hosts.
- A facilitator may read the task only; hints make the attempt unsuccessful and must be recorded.

## Script

1. Show the login/first-run screen. Ask: “What is this product for?” Stop at 60 seconds and record the answer.
2. Ask the participant to complete readiness and reach the server workspace.
3. Provide a fixture host and ask them to add it.
4. Ask them to open a terminal connection.
5. Ask them to run the designated guarded action, review the confirmation and complete it.
6. Ask them to find the resulting audit entry and explain whether the action succeeded.
7. Ask one final question: “What would you do next if the server were unreachable?”

## Pass criteria

An attempt passes only when all five primary tasks complete without a hint and the participant locates the correct audit event. The Stage 1 gate is at least 90% successful attempts across at least 10 participants. Also record time-to-understanding, task duration, errors, denied/degraded states encountered and accessibility-assistance used.

## Evidence format

Copy [the v1 JSON template](PILOT_UX_RESULTS_V1.template.json) and store a privacy-safe participant code, commit SHA, environment, timestamps, each task result, hints, total pass/fail and classified environment/product errors for every attempt. Attach screenshots or recordings only with consent. Report unsuccessful attempts; never replace or exclude them to improve the rate.

Validate the completed file and save the machine-readable decision:

```bash
python scripts/verify_pilot_ux_results.py path/to/pilot-results.json \
  --output .ci-artifacts/pilot-ux-verification.json
```

The validator derives the denominator from every recorded attempt, rejects duplicate participants and inconsistent pass claims, and requires both task success and understanding within 60 seconds to reach 90% across at least 10 independent participants.

The F-12 issue remains open until real results satisfy the gate and the tested commit is traceable to CI evidence.
