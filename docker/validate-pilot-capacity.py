#!/usr/bin/env python3
"""Fail-closed capacity contract for the controlled AI CLI pilot."""

from __future__ import annotations

import argparse


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

    if args.global_concurrency != 10:
        parser.error("pilot global concurrency must be exactly 10")
    if args.per_user_concurrency != 2:
        parser.error("pilot per-user concurrency must be exactly 2")
    slots = args.replicas * args.worker_concurrency
    if slots < args.global_concurrency:
        parser.error("replicas multiplied by worker concurrency must provide at least 10 local slots")

    print(f"Pilot capacity valid: database cap=10, per-user cap=2, local worker slots={slots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
