import sys

import csv
import json
import re

from collections import defaultdict

import matplotlib.pyplot as plt
import matplotlib.colors as pltcolors
import numpy as np
from numpy.polynomial import Polynomial

import crunch_utils
import argparse

def reddish(saturation):
    return pltcolors.to_hex(
        pltcolors.hsv_to_rgb(
            (0.0, saturation, 1.0)
        )
    )

def bluish(saturation):
    return pltcolors.to_hex(
        pltcolors.hsv_to_rgb(
            (240.0/360.0, saturation, 1.0)
        )
    )

def greenish(saturation):
    return pltcolors.to_hex(
        pltcolors.hsv_to_rgb(
            (120.0/360.0, saturation, 1.0)
        )
    )

PlotKeys = {
    "data-plane CPU": ("data-plane CPU", None),
    "data-plane mem": ("data-plane mem", None),
    "ztunnel mesh CPU": ("ztunnel CPU", "xkcd:salmon"),
    "ztunnel mesh mem": ("ztunnel mem", "xkcd:salmon"),
    "waypoint mesh CPU": ("waypoint CPU", "xkcd:dark pink"),
    "waypoint mesh mem": ("waypoint mem", "xkcd:dark pink"),

    "ambient P50": ("ambient P50", reddish(0.2)),
    "ambient P75": ("ambient P75", reddish(0.4)),
    "ambient P90": ("ambient P90", reddish(0.6)),
    "ambient P95": ("ambient P95", reddish(0.8)),
    "ambient P99": ("ambient P99", reddish(1.0)),

    "linkerd P50": ("linkerd P50", bluish(0.2)),
    "linkerd P75": ("linkerd P75", bluish(0.4)),
    "linkerd P90": ("linkerd P90", bluish(0.6)),
    "linkerd P95": ("linkerd P95", bluish(0.8)),
    "linkerd P99": ("linkerd P99", bluish(1.0)),

    "unmeshed P50": ("unmeshed P50", greenish(0.2)),
    "unmeshed P75": ("unmeshed P75", greenish(0.4)),
    "unmeshed P90": ("unmeshed P90", greenish(0.6)),
    "unmeshed P95": ("unmeshed P95", greenish(0.8)),
    "unmeshed P99": ("unmeshed P99", greenish(1.0)),
}


class MetricsFile:
    """
    Load a file that contains metrics. At present, we have two kinds:

    - kind=Usage: parsed from "metrics" CSV files where the columns are
      specific resource-consumption metrics (e.g. "Faces CPU" or "data-plane
      mem") and the rows are samples in time

    - kind=Latency: parsed from "wrk2" files that contain a list of latencies
      for a given percentile (e.g. "P50" or "P95") at a single point in time

    In both cases, we parse RPS and mesh from the file path, which always
    looks like "{mesh}(-\d+)?/{rps}-{seq}-metrics.csv" or
    "{mesh}(-\d+)?/{rps}-{seq}-wrk2-{pod}.log".
    """

    def __init__(self, name, infile):
        self.kind = None
        self.name = name
        self.data = {}  # Keys are field names for metrics, "P50", "P95", etc. for latencies

        if "-metrics" in name:
            # This is a Usage file.
            self.mesh, self.rps, self.seq = crunch_utils.parse_filename(self.name, "metrics.csv")
            self.parse_metrics(infile)
        elif "-wrk2-" in name:
            # This is a wrk2 Latency file.
            self.mesh, self.rps, self.seq = crunch_utils.parse_filename(self.name, "wrk2(-[a-z0-9]{5}?).log")
            self.parse_wrk2_latencies(infile)
        elif "-oha-" in name:
            # This is a wrk2 Latency file.
            self.mesh, self.rps, self.seq = crunch_utils.parse_filename(self.name, "oha(-[a-z0-9]{5}?).log")
            self.parse_oha_latencies(infile)
        else:
            raise Exception(f"Unrecognized file name {name}")

    def parse_metrics(self, infile):
        """
        Parse a Usage file, which is a CSV where each column is a specific
        kind of resource usage and each row is a sample at a given point in
        time. We end up with a dictionary where the keys are CSV field names
        and the values are lists of the data in each column.
        """

        self.kind = "Usage"

        reader = csv.DictReader(infile)
        self.fieldnames = [f for f in reader.fieldnames if f != 'timestamp']

        for row in reader:
            for fieldname in self.fieldnames:
                if row[fieldname]:
                    if fieldname not in self.data:
                        self.data[fieldname] = []

                    # The values stored are always integers, but we'll be
                    # converting them to float values.
                    value = float(row[fieldname])

                    if fieldname.endswith(" CPU"):
                        # Convert CPU usage from nanocores to millicores.
                        value /= 1_000_000
                    elif fieldname.endswith(" mem"):
                        # Convert memory usage from bytes to megabytes.
                        value /= 1_048_576

                    self.data[fieldname].append(value)

    def parse_wrk2_latencies(self, infile):
        """
        Parse a wrk2 Latency file, which contains a list of latencies for a
        given percentile (e.g. "P50" or "P95") at a single point in time. We
        end up with a dictionary where the keys are percentile names (e.g.
        "P50", "P95") and the values are single-element lists of the latencies
        for those percentiles.

        We use a single-element list rather than a scalar just for parallelism
        between the Usage files and the Latency files.
        """
        self.kind = "Latency"
        self.fieldnames = [ "P50", "P75", "P90", "P95", "P99" ]
        state = 0

        for line in infile:
            # print(f"{state}: {line.rstrip()}")
            if state == 0:
                if "Detailed Percentile spectrum" in line:
                    state = 1
                    continue

            if state == 1:
                if line.strip() == "":
                    state = 2
                    continue

            if state == 2:
                if line.startswith("#"):
                    break

                match = re.match(r'\s*(\d+\.\d+)\s+(\d+\.\d+)', line)

                if match:
                    latency = float(match.group(1))
                    bucket = float(match.group(2)) * 100.0

                    # print("Bucket %f latency %f" % (bucket, latency))

                    key = None
                    if bucket <= 50.0:
                        key = "P50"
                    elif bucket <= 75.0:
                        key = "P75"
                    elif bucket <= 90.0:
                        key = "P90"
                    elif bucket <= 95.0:
                        key = "P95"
                    elif bucket <= 99.0:
                        key = "P99"

                    if key:
                        self.data[key] = [latency]

        for bucket, latency in self.data.items():
            if not latency:
                raise Exception(f"No {bucket} found in {self.name}")

    def parse_oha_latencies(self, infile):
        """
        Parse an oha Latency file, which is JSON (but with single quotes
        instead of double quotes, sigh). The really interesting bits are in
        the "latencyPercentiles" section, which a dict with keys of "p50",
        "p75", etc. and values that are the latencies for those percentiles.
        We end up with a dictionary where the keys are percentile names,
        uppercased (e.g. "P50", "P95") and the values are single-element lists
        of the latencies.

        We use a single-element list rather than a scalar just for parallelism
        between the Usage files and the Latency files.
        """
        self.kind = "Latency"
        self.fieldnames = [ "P50", "P75", "P90", "P95", "P99" ]

        # Oha's take on JSON is... uh... kinda broken.
        oha_text = infile.read().replace("'", "\"").replace("None", "null")

        try:
            oha_data = json.loads(oha_text)
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse JSON in {self.name}: {e}")

        for bucket, latency in oha_data["latencyPercentiles"].items():
            bucket = bucket.upper()

            if bucket in self.fieldnames:
                self.data[bucket] = [latency * 1000.0]

        for bucket, latency in self.data.items():
            if not latency:
                raise Exception(f"No {bucket} found in {self.name}")

    def __str__(self):
        return f"MetricsFile({self.kind} {self.name}: {self.mesh}, {self.rps}, {self.seq})"


class CorrelatedMetrics:
    """
    Take a bunch of MetricsFile objects and correlate metrics by RPS (in
    increasing order), then by mesh, then by field name, e.g.:

    data[120]["linkerd"]["data-plane CPU"] =
        [all the data-plane CPU for all Linkerd runs at 120 RPS]

    We take _all_ the samples across all runs. If we want to filter outliers,
    that'll come later.
    """

    def __init__(self, metrics_files):
        self.rpses = []
        self.meshes = []
        self.fields = []
        self.data = {}

        rpses = set()
        meshes = set()
        fields = set()

        # native_metrics[rps][mesh][fieldname] is a list of data for that field
        # across all runs for that RPS and mesh. This is the Python-array format
        # of this; we'll make it a NumPy array later.
        native_metrics = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

        for metrics_file in metrics_files:
            for fieldname in metrics_file.fieldnames:
                if fieldname in metrics_file.data:
                    # Remember that this RPS, mesh, and fieldname have data.
                    rpses.add(metrics_file.rps)
                    meshes.add(metrics_file.mesh)
                    fields.add(fieldname)

                    # Real data that we need to save in our native-format dict.
                    native_metrics[metrics_file.rps][metrics_file.mesh][fieldname].extend(
                        metrics_file.data[fieldname]
                    )

        self.rpses = sorted(rpses)
        self.meshes = sorted(meshes)
        self.fields = sorted(fields)

        # OK, after all that is done, convert each field's data to a NumPy array...
        for rps in self.rpses:
            self.data[rps] = {}

            for mesh in self.meshes:
                self.data[rps][mesh] = {}

                for fieldname in self.fields:
                    if fieldname in native_metrics[rps][mesh]:
                        # Convert the list of data to a NumPy array.
                        dataset = np.array(native_metrics[rps][mesh][fieldname])

                        # Calculate mean and standard deviation for this data set...
                        mean = np.mean(dataset)
                        stddev = np.std(dataset)

                        # Create a filtered dataset that excludes outliers.
                        filtered_dataset = dataset[np.abs(dataset - mean) <= 1 * stddev]

                        # Store everything in our data dictionary.
                        self.data[rps][mesh][fieldname] = {
                            "mean": mean,
                            "stddev": stddev,
                            "data": dataset,
                            "filtered": filtered_dataset,
                        }

    def __str__(self):
        return f"CorrelatedMetrics({self.rpses}, {self.meshes})"

    def plot(self, title, unit, *fields):
        """
        Plot the data for a given fieldname. The X axis is RPS, the Y axis is the
        field values, and the different meshes are different series on the plot.
        We'll use a scatter plot and show a regression line for each series.
        """

        # series is a dict of mesh names to pairs of NumPy arrays: one is the X
        # values (RPS) and the other is the Y values (filtered data).}

        series = {}

        for rps in self.rpses:
            for mesh in self.meshes:
                # For each fieldname, get the data for this RPS and mesh.
                for fieldname in fields:
                    if fieldname in self.data[rps][mesh]:
                        # print(f"RPS {rps} mesh {mesh} fieldname {fieldname}")
                        data = self.data[rps][mesh][fieldname]

                        # For the X-axis, repeat the RPS value for each data point.
                        # For the Y-axis, use the filtered data.
                        x = np.array([rps] * len(data["filtered"]))
                        y = data["filtered"]

                        display_name = f"{mesh} {fieldname}"
                        display_color = None

                        for fk in [ f"{mesh} {fieldname}", fieldname ]:
                            if fk in PlotKeys:
                                display_name, display_color = PlotKeys[fk]
                                break

                        if not display_color:
                            display_color = "blue" if mesh == "linkerd" else "red"

                        series_name = f"{mesh} {fieldname}"
                        if series_name not in series:
                            series[series_name] = {
                                "name": display_name,
                                "mesh": mesh,
                                "color": display_color,
                                "x": x,
                                "y": y,
                                "mean_x": np.array([rps]),
                                "mean_y": np.array([np.mean(y)]),
                            }
                        else:
                            s = series[series_name]
                            s["x"] = np.concatenate((s["x"], x))
                            s["y"] = np.concatenate((s["y"], y))
                            s["mean_x"] = np.concatenate((s["mean_x"], np.array([rps])))
                            s["mean_y"] = np.concatenate((s["mean_y"], np.array([np.mean(y)])))

        # We'll plot regressions across 100 points that linearly span the whole
        # RPS range.
        regression_x = np.linspace(correlated_metrics.rpses[0],
                                   correlated_metrics.rpses[-1], 100)

        fig = plt.figure(figsize=(10, 6))

        ax = fig.add_axes([0.1, 0.1, 0.8, 0.8])
        ax.set_xticks(self.rpses)
        ax.set_xticklabels(self.rpses, rotation=45)
        ax.set_title(title)

        # Plot each series.
        for series_name, data in series.items():
            # Scatter plot of the data.
            x = data["x"]
            y = data["y"]
            color = data["color"]

            # print(f"plot {series_name} with color {color}")
            ax.scatter(x, y, label=series_name, color=color)

            # # Plot averages.
            # ax.scatter(data["mean_x"], data["mean_y"], color=color, s=80, marker="^", label=None)

            # Regress!
            p = Polynomial.fit(x, y, 2)
            ax.plot(regression_x, p(regression_x), color=color, linestyle="--")

        # print("plotting")

        ax.set_xlabel("RPS")
        ax.set_ylabel(unit)
        ax.legend()

        return fig


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot metrics from input files.")
    parser.add_argument("-i", "--interactive", action="store_true", help="Enable interactive mode (default: off)")
    parser.add_argument("-l", "--latency", action="store_true", help="Enable latency plot (default: off)")
    parser.add_argument("paths", nargs="+", help="Paths to metrics files")

    args = parser.parse_args()

    metrics_files = []

    for path in args.paths:
        with open(path, 'r') as infile:
            metrics_files.append(MetricsFile(path, infile))

    if metrics_files:
        correlated_metrics = CorrelatedMetrics(metrics_files)

        dp_cpu_fig = correlated_metrics.plot("Data Plane CPU", "mC",
                     "data-plane CPU", "ztunnel mesh CPU", "waypoint mesh CPU")

        if not args.interactive:
            dp_cpu_fig.savefig(f"data-plane-CPU.png")

        dp_mem_fig = correlated_metrics.plot("Data Plane Memory", "MiB",
                   "data-plane mem", "ztunnel mesh mem", "waypoint mesh mem")

        if not args.interactive:
            dp_mem_fig.savefig(f"data-plane-mem.png")

        if args.latency:
            latency_fig = correlated_metrics.plot(
                "Latency -- LOW CONFIDENCE", "ms",
                "P50", "P75", "P90", "P95", "P99"
            )

            if not args.interactive:
                latency_fig.savefig(f"latency.png")

        if args.interactive:
            plt.show()
