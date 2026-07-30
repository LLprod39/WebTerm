# Agent command sandbox

WebTrerm production agents do not open SSH sessions from the backend process.
Every full-agent, mini-agent, and Studio direct-SSH command is submitted to a
new single-shot container through `servers.services.agent_command_runner`.

## Runtime contract

- `AGENT_COMMAND_RUNTIME=docker` is mandatory outside tests.
- `AGENT_COMMAND_RUNNER_IMAGE` must be an immutable `sha256:<64 lowercase hex>`
  local image ID or `repository@sha256:<64 lowercase hex>` release reference. An empty or tagged image
  fails closed before Docker starts.
- The container is removed after one command and runs read-only, without Linux
  capabilities, with `no-new-privileges`, bounded CPU, memory, PIDs, time and
  output, and only a small no-exec tmpfs.
- SSH passwords, private keys, key passphrases, sudo input and commands are serialized only
  to container stdin. They are never placed in Docker arguments, labels, or
  environment variables.
- Trusted host keys remain mandatory. When `SSH_AUTH_SOCK` is available it is forwarded as a read-only
  socket mount and exposed only to the single-shot runner.
- Bastion tunnel configuration is carried into the runner. The runner performs
  strict host-key verification and emits one bounded JSON result.
- Production backend and agent workers do not mount `docker.sock`. They reach
  `agent-command-docker-proxy` on an internal control network; its body-aware
  policy permits only the pinned image, managed name/label, non-root user,
  exact limits, lifecycle endpoints, and optional configured SSH-agent socket.

`AGENT_COMMAND_RUNTIME=host` exists solely for automated tests and additionally
requires both Django `TESTING=True` and
`AGENT_COMMAND_ALLOW_UNSAFE_HOST_RUNTIME_FOR_TESTS=True`. Deployment checks
reject host mode and mutable runner images as `servers.E002`/`servers.E003`.

## Build and release

Build the candidate with:

```text
docker compose --profile agent-runner build agent-command-runner
```

The production installer builds and pins the local image ID when builds are
enabled. For no-build releases, publish the image, resolve its registry digest,
set `AGENT_COMMAND_RUNNER_IMAGE` to that digest reference, and run
`python manage.py check --deploy` before rollout.
