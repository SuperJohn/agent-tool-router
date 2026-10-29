"""Command line: bench, record, serve."""

from __future__ import annotations

import argparse
import os

from toolrouter.bench import format_report, run_benchmark, write_results, write_site
from toolrouter.provider import provider_from_env
from toolrouter.dataset import load_dataset
from toolrouter.serve import serve


def _build_provider_and_report(args: argparse.Namespace) -> dict:
    dataset = load_dataset()
    provider = provider_from_env(dataset.recordings)
    max_retries = args.max_retries
    if max_retries is None:
        max_retries = int(os.environ.get("HL_MAX_RETRIES", "2"))
    return run_benchmark(dataset, provider, max_retries=max_retries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="toolrouter")
    sub = parser.add_subparsers(dest="cmd", required=True)

    bench = sub.add_parser("bench", help="run with-router and without-router, write results/runs")
    bench.add_argument("--max-retries", type=int, default=None)

    record = sub.add_parser("record", help="bench, then publish site/data for the mock provider")
    record.add_argument("--max-retries", type=int, default=None)
    record.add_argument("--publish", action="store_true", help="write site/data even for a non-mock provider")
    record.add_argument("--no-publish", action="store_true", help="write results/runs only")

    serve_cmd = sub.add_parser("serve", help="serve the replay site and /api/run on 127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=None)
    serve_cmd.add_argument("--host", default="127.0.0.1")

    args = parser.parse_args(argv)
    if args.cmd == "serve":
        serve(host=args.host, port=args.port)
        return 0

    report = _build_provider_and_report(args)
    path = write_results(report)
    print(format_report(report))
    print(f"\nwrote {path}")
    if args.cmd == "record":
        publish = False
        if args.no_publish:
            publish = False
        elif args.publish or report["provider"] == "mock":
            publish = True
        if publish:
            scoreboard, traces = write_site(report)
            print(f"wrote {scoreboard}")
            print(f"wrote {traces}")
        else:
            print("site/data left unchanged (pass --publish to replace the replay)")
    return 0
