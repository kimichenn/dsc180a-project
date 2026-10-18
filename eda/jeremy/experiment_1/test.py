"""Terminal version of test.ipynb; save the CUDA check to experiment_1/results/environment.json."""

import argparse
import json
from pathlib import Path
import sys

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    args = parser.parse_args(argv)
    results_dir = args.results_dir.expanduser().resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    report = {"python": sys.version.split()[0], "executable": sys.executable}
    try:
        import torch

        available = torch.cuda.is_available()
        report.update(torch_version=torch.__version__, cuda_available=available,
                      device_count=torch.cuda.device_count() if available else 0)
        if available:
            report["gpu"] = torch.cuda.get_device_name(0)
        print("CUDA available:", available)
        if available:
            print("GPU:", report["gpu"])
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print("CUDA check failed:", report["error"], file=sys.stderr)
    output = results_dir / "environment.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Environment report saved:", output)
    return 1 if "error" in report else 0


if __name__ == "__main__":
    sys.exit(main())
