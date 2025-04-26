#!/usr/bin/env python

import os
import argparse

from single import run

parser = argparse.ArgumentParser(description="Run a sequence of tests and collect metrics.")
parser.add_argument("--duration", type=str, default="1800s",
                    help="Duration of test (default: 1800s)")
parser.add_argument("--workers", type=int, default=1,
                    help="Number of workers (default: 1)")
parser.add_argument("--loadgen", type=str, default="oha",
                    help="Load generator (default: oha)")
parser.add_argument("--affinity", action="store_true",
                    help="Enable CPU affinity")
parser.add_argument("--runs", type=int, default=5,
                    help="Number of tests to run at each RPS (default: 5)")
parser.add_argument("--loops", type=int, default=1,
                    help="Number of loops over all RPSes (default: 1)")
parser.add_argument("--rps", type=str, default="60,120,240,600,1200",
                    help="Comma-separated RPS list (default: 60,120,240,600,1200)")
parser.add_argument("mesh", type=str,
                    help="Mesh name")
parser.add_argument("outdir", type=str,
                    help="Top-level output directory")

args = parser.parse_args()

# Parse the RPS list
rps_list = [int(rps) for rps in args.rps.split(",")]

# Loop over the RPS list and run the tests
for loop in range(args.loops):
    for rps in rps_list:
        for seq in range(args.runs):
            outdir = os.path.join(args.outdir, f"{args.mesh}-{loop:02d}")

            print(f"Running {args.loadgen} test {loop:02d} for {rps} RPS, sequence {seq}, outdir {outdir}...")
            run(outdir, rps, seq, args.duration, args.loadgen, args.workers, args.affinity)



