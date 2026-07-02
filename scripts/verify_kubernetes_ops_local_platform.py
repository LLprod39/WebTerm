from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kubernetes_ops.services.local_platform_evidence import (  # noqa: E402
    LocalPlatformProbeOptions,
    verify_kubernetes_local_platform,
    write_local_platform_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the local kind Rancher/Fleet/Devtron platform from a host with kubectl access."
    )
    parser.add_argument("--output", default="artifacts/kubernetes_ops_local_platform_evidence.json")
    parser.add_argument("--context", default="kind-webterm-k8s")
    parser.add_argument("--kubectl", default="kubectl")
    parser.add_argument("--no-context-requirement", action="store_true")
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args()

    report = verify_kubernetes_local_platform(
        LocalPlatformProbeOptions(
            context=str(args.context or ""),
            kubectl=str(args.kubectl or "kubectl"),
            require_context=not bool(args.no_context_requirement),
        )
    )
    output_path = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    write_local_platform_evidence(report, output_path)
    print(
        json.dumps(
            {
                "status": report["status"],
                "context": report["context"],
                "summary": report["summary"],
                "errors": report["errors"],
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "ready" or args.no_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
