"""Run the pipeline end to end, or one stage at a time.

    python run_pipeline.py --all        simulate, build, export marts
    python run_pipeline.py --simulate   raw parquet event log only
    python run_pipeline.py --build      rebuild the DuckDB warehouse
    python run_pipeline.py --marts      re-export the CSVs in data/marts
"""

import argparse
import sys
import time

sys.path.insert(0, "src")

from ga4_growth import config


def main():
    parser = argparse.ArgumentParser(description="GA4 growth analytics pipeline")
    parser.add_argument("--simulate", action="store_true", help="generate raw GA4 shaped events")
    parser.add_argument("--build", action="store_true", help="build the DuckDB warehouse")
    parser.add_argument("--marts", action="store_true", help="export CSV marts for Power BI")
    parser.add_argument("--all", action="store_true", help="run all three stages")
    args = parser.parse_args()

    if not any([args.simulate, args.build, args.marts, args.all]):
        parser.print_help()
        return 1

    config.ensure_dirs()
    started = time.time()

    if args.simulate or args.all:
        from ga4_growth import simulate

        print("[1/3] simulating raw events")
        simulate.main()

    if args.build or args.all:
        from ga4_growth import warehouse

        print("[2/3] building warehouse")
        warehouse.build()

    if args.marts or args.all:
        from ga4_growth import metrics

        print("[3/3] exporting marts")
        written = metrics.export_marts()
        for name in written:
            print(f"  {name}")

    print(f"done in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
