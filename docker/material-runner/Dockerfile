FROM python:3.13.7-alpine3.22@sha256:9ba6d8cbebf0fb6546ae71f2a1c14f6ffd2fdab83af7fa5669734ef30ad48844
RUN apk add --no-cache bash=5.2.37-r0 && addgroup -g 10001 runner && adduser -D -H -u 10001 -G runner runner
COPY --chown=10001:10001 docker/material-runner/runner.py /runner.py
USER 10001:10001
ENTRYPOINT ["python", "/runner.py"]
