from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the Kaggle medicine dataset for MediScan AI.")
    parser.add_argument(
        "--dataset",
        default="shudhanshusingh/az-medicine-dataset-of-india",
        help="Kaggle dataset slug.",
    )
    parser.add_argument(
        "--file",
        default="",
        help="Specific file inside the Kaggle dataset. If omitted, the largest tabular file is used.",
    )
    parser.add_argument(
        "--output",
        default="backend/data/medicine_dataset.csv",
        help="Local output file path.",
    )
    args = parser.parse_args()

    import kagglehub

    dataset_dir = Path(kagglehub.dataset_download(args.dataset))
    source = dataset_dir / args.file if args.file else largest_tabular_file(dataset_dir)
    if source is None or not source.exists():
        raise FileNotFoundError(f"No tabular dataset file found in {dataset_dir}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    print(f"Downloaded {args.dataset}")
    print(f"Source: {source}")
    print(f"Output: {output.resolve()}")


def largest_tabular_file(directory: Path) -> Path | None:
    candidates = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in {".csv", ".parquet", ".pq", ".xlsx", ".xls"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_size)


if __name__ == "__main__":
    main()
