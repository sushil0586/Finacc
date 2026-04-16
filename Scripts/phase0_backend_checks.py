from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    print(f"\n> {' '.join(args)}", flush=True)
    completed = subprocess.run(args, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    run(sys.executable, "manage.py", "check")
    run(
        sys.executable,
        "manage.py",
        "test",
        "vouchers.tests",
        "catalog.tests",
        "payments.tests",
        "receipts.tests",
        "sales.tests.SalesInvoiceViewUnitTests",
        "--keepdb",
        "--noinput",
    )
    run(sys.executable, "-m", "compileall", "helpers", "vouchers", "catalog", "payments", "receipts", "sales")


if __name__ == "__main__":
    main()
