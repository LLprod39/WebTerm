# WebTerm Ansible runner — ad-hoc container for real ansible-playbook.
# Build:
#   docker build -t webterm-ansible:latest -f docker/ansible-runner/Dockerfile .
# Or:
#   docker compose --profile ansible build ansible-runner
#
# Not a long-running service: backend starts it per playbook run (like a job).

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ANSIBLE_HOST_KEY_CHECKING=False \
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
        "ansible-core>=2.16,<2.19" \
        "ansible-runner>=2.3" \
    && ansible-galaxy collection install \
        ansible.posix \
        community.general \
        --collections-path /usr/share/ansible/collections

ENV ANSIBLE_COLLECTIONS_PATH=/usr/share/ansible/collections

WORKDIR /ansible
# Default entrypoint is ansible-playbook; docker run ... webterm-ansible:latest <args>
ENTRYPOINT ["ansible-playbook"]
CMD ["--version"]
