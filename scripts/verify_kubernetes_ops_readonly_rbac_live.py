from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kubernetes_ops.services.readonly_rbac import READONLY_SERVICE_ACCOUNT_CONTRACT  # noqa: E402
from kubernetes_ops.services.readonly_rbac_live import (  # noqa: E402
    KubectlProbeOptions,
    verify_kubernetes_readonly_rbac_live,
    write_live_rbac_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify WebTerm Kubernetes Ops read-only RBAC against a live kubectl context."
    )
    parser.add_argument("--manifest", default="artifacts/kubernetes_ops_readonly_rbac.yaml")
    parser.add_argument("--output", default="artifacts/kubernetes_ops_readonly_rbac_live_evidence.json")
    parser.add_argument(
        "--apply", action="store_true", help="Apply the manifest before running kubectl auth can-i probes."
    )
    parser.add_argument("--context", default="")
    parser.add_argument("--kubectl", default="kubectl")
    parser.add_argument("--namespace", default=READONLY_SERVICE_ACCOUNT_CONTRACT["namespace"])
    parser.add_argument("--service-account", default=READONLY_SERVICE_ACCOUNT_CONTRACT["name"])
    parser.add_argument("--probe-namespace", default="default")
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args()

    report = verify_kubernetes_readonly_rbac_live(
        KubectlProbeOptions(
            manifest_path=(ROOT / args.manifest).resolve()
            if not Path(args.manifest).is_absolute()
            else Path(args.manifest),
            apply_manifest=args.apply,
            context=args.context,
            kubectl=args.kubectl,
            service_account_namespace=args.namespace,
            service_account_name=args.service_account,
            probe_namespace=args.probe_namespace,
        )
    )
    output_path = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    write_live_rbac_evidence(report, output_path)
    print(
        json.dumps(
            {
                "status": report["status"],
                "context": report["context"],
                "errors": report["errors"],
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "ready" or args.no_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
