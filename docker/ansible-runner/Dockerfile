# WebTerm Ansible runner — ad-hoc container for real ansible-playbook.
# Build:
#   docker build -t webterm-ansible:latest -f docker/ansible-runner/Dockerfile .
# Or:
#   docker compose --profile ansible build ansible-runner
#
# Not a long-running service: backend starts it per playbook run (like a job).

FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ANSIBLE_FORCE_COLOR=0 \
    ANSIBLE_NOCOLOR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openssh-client \
        sshpass \
        git \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ansible-core only (no bloated ansible package); collections for common modules
RUN pip install --no-cache-dir \
        "ansible-core==2.18.18" \
        "ansible-runner==2.4.3" \
    && ansible-galaxy collection install \
        ansible.posix:2.2.2 \
        community.general:13.2.0 \
        --collections-path /usr/share/ansible/collections

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin ansible

ENV ANSIBLE_COLLECTIONS_PATH=/usr/share/ansible/collections

COPY docker/ansible-runner/validator.py /opt/webterm/validator.py
COPY docker/ansible-runner/runtime_metadata.py /opt/webterm/runtime_metadata.py
RUN python /opt/webterm/runtime_metadata.py --write /opt/webterm/runtime-manifest.json

WORKDIR /ansible
USER 10001:10001
# Default entrypoint is ansible-playbook; docker run ... webterm-ansible:latest <args>
ENTRYPOINT ["ansible-playbook"]
CMD ["--version"]
