#!/usr/bin/env python3
"""Fail-closed capacity contract for the controlled AI CLI pilot."""

from __future__ import annotations

import argparse


MAX_GLOBAL_CONCURRENCY = 10
MAX_PER_USER_CONCURRENCY = 2


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--global-concurrency", required=True, type=_positive_int)
    parser.add_argument("--per-user-concurrency", required=True, type=_positive_int)
    parser.add_argument("--replicas", required=True, type=_positive_int)
    parser.add_argument("--worker-concurrency", required=True, type=_positive_int)
    args = parser.parse_args()

    if args.global_concurrency > MAX_GLOBAL_CONCURRENCY:
        parser.error(
            f"pilot global concurrency must not exceed {MAX_GLOBAL_CONCURRENCY}"
        )
    if args.per_user_concurrency > MAX_PER_USER_CONCURRENCY:
        parser.error(
            f"pilot per-user concurrency must not exceed {MAX_PER_USER_CONCURRENCY}"
        )
    if args.per_user_concurrency > args.global_concurrency:
        parser.error("pilot per-user concurrency must not exceed global concurrency")
    slots = args.replicas * args.worker_concurrency
    if slots < args.global_concurrency:
        parser.error(
            "replicas multiplied by worker concurrency must provide at least "
            f"{args.global_concurrency} local slots"
        )

    print(
        "Pilot capacity valid: "
        f"database cap={args.global_concurrency}, "
        f"per-user cap={args.per_user_concurrency}, "
        f"local worker slots={slots}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
