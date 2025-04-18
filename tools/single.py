#!/usr/bin/env python

import os
import sys
import time
import yaml

from kubernetes import client, config
from kubernetes.utils import create_from_yaml

from metrics import AggregateUsage

node_affinity_stanza = """
requiredDuringSchedulingIgnoredDuringExecution:
  nodeSelectorTerms:
  - matchExpressions:
    - key: buoyant.io/meshtest-role
      operator: In
      values:
      - load
"""

pod_anti_affinity_stanza_template = """
preferredDuringSchedulingIgnoredDuringExecution:
- weight: 100
  podAffinityTerm:
    labelSelector:
      matchExpressions:
      - key: faces.buoyant.io/component
        operator: In
        values:
        - %(worker)s
    topologyKey: kubernetes.io/hostname
"""

class JobManager:
    def __init__(self, core_v1, batch_v1, name, namespace):
        base_job_path = os.path.join(os.path.dirname(__file__), f"{name}.yaml")
        self.base_job = yaml.safe_load(open(base_job_path).read())

        self.core_v1 = core_v1
        self.batch_v1 = batch_v1
        self.name = name
        self.namespace = namespace

    def delete_job(self):
        # Delete existing job
        try:
            self.batch_v1.delete_namespaced_job(name=self.name, namespace=self.namespace, propagation_policy="Foreground")
            print("Deleted existing job")

            # Wait for job to vanish
            left = 10
            while left > 0:
                print(f"...waiting for {self.name} to be deleted... ({left})")
                time.sleep(10)
                left -= 1

                some = True

                try:
                    self.batch_v1.read_namespaced_job(name=self.name, namespace=self.namespace)
                except client.exceptions.ApiException as e:
                    if e.status == 404:
                        some = False
                        break
                    raise

                if not some:
                    break

            if left == 0:
                raise RuntimeError(f"{self.name} did not delete")
        except client.exceptions.ApiException as e:
            if e.status != 404:
                raise
            print("No existing job to delete")

    def create_job(self, rps, duration, workers, affinity):
        podrps = int(rps) // workers
        print(f"...starting {self.name} ({rps} RPS, {duration}, {workers} workers, {podrps} per pod)")

        job = None

        if self.name == "wrk2":
            job = self.prep_wrk2_job(podrps, duration)
        elif self.name == "oha":
            job = self.prep_oha_job(podrps, duration)
        else:
            raise ValueError(f"Unknown job name: {self.name}")

        affinity_stanza = {}

        job_spec = job["spec"]
        job_template_spec = job["spec"]["template"]["spec"]

        if workers > 1:
            job_spec["parallelism"] = workers
            job_spec["completions"] = workers

            antiaffinity = pod_anti_affinity_stanza_template % {"worker": self.name}
            affinity_stanza["podAntiAffinity"] = yaml.safe_load(antiaffinity)

        if affinity:
            affinity_stanza["nodeAffinity"] = yaml.safe_load(node_affinity_stanza)

        if affinity_stanza:
            job_template_spec["affinity"] = affinity_stanza

        create_from_yaml(client.ApiClient(), yaml_objects=[ job ], namespace=self.namespace)

        # Wait for job to start
        left = 10
        while left > 0:
            print(f"...waiting for {self.name} to start... ({left})")
            time.sleep(10)
            left -= 1

            job = self.batch_v1.read_namespaced_job(name=self.name, namespace=self.namespace)
            if job.status.ready == workers:
                break

        if left == 0:
            raise RuntimeError(f"{self.name} did not start")

        print(f"...{self.name} running")

    def prep_wrk2_job(self, podrps, duration):
        # Customize the Job spec as needed
        job = self.base_job.copy()
        job_template_spec = job["spec"]["template"]["spec"]

        job_template_spec["containers"][0]["command"] = [
            "/wrk",
            "-t", "8",
            "-c", "200",
            "-d", str(duration),
            "-R", str(podrps),
            "--latency",
            "http://face/",
        ]

        return job

    def prep_oha_job(self, podrps, duration):
        # Customize the Job spec as needed
        job = self.base_job.copy()
        job_template_spec = job["spec"]["template"]["spec"]

        job_template_spec["containers"][0]["command"] = [
            "/bin/oha",
            "-c", "200",
            "-z", str(duration),
            "-q", str(podrps),
            "--latency-correction",
            "--no-tui",
            "--json",
            "http://face/",
        ]

        return job

    def check_job(self, workers):
        job = self.batch_v1.read_namespaced_job(name=self.name, namespace=self.namespace)

        if job.status.succeeded == workers:
            return True

        return False

    def collect_logs(self, outdir, rps, seq):
        print("...collecting logs...")

        # Collect logs
        pods = self.core_v1.list_namespaced_pod(namespace=self.namespace,
                                        label_selector=f"batch.kubernetes.io/job-name={self.name}")

        for _, pod in enumerate(pods.items, start=1):
            pod_name = pod.metadata.name
            print(f"...collecting logs from {pod_name}...")
            log = self.core_v1.read_namespaced_pod_log(name=pod_name, namespace=self.namespace)

            with open(f"{outdir}/{rps}-{seq}-{pod_name}.log", "w") as f:
                f.write(log)


def run(outdir, rps, seq, duration, loadgen, workers, affinity):
    config.load_kube_config()
    core_v1 = client.CoreV1Api()
    batch_v1 = client.BatchV1Api()

    # Create job manager
    job_manager = JobManager(core_v1, batch_v1, loadgen, "faces")

    try:
        os.makedirs(outdir, exist_ok=True)
    except OSError as e:
        print(f"Error creating output directory {outdir}: {e}")
        sys.exit(1)

    outfile = os.path.join(outdir, f"{rps}-{seq}-metrics.csv")

    agg = AggregateUsage(outfile)

    # Delete existing job
    job_manager.delete_job()

    print(f"Starting {outdir} {rps}-{seq}... ({duration}, worker count {workers})")

    # Grab samples until we see that the application has idled...

    while True:
        agg.sample(True)
        time.sleep(10)

        # Check if the aggregator has started collecting...
        if agg.is_collecting():
            print("...started collecting")
            break

    # Create job
    job_manager.create_job(rps, duration, workers, affinity)

    # Grab samples until our job is finished...
    while True:
        agg.sample(True)
        time.sleep(10)

        if job_manager.check_job(workers):
            print("...run finished")
            break

    # Collect 6 more samples, since they can lag realtime. Stop
    # early if Faces goes idle again.
    print("...collecting tail metrics")
    agg.start_draining()

    for _ in range(6):
        agg.sample(True)

        if agg.is_idle():
            print("...idle again, stopping")
            break

        time.sleep(10)

    # Stop collecting metrics...
    agg.stop_collecting()

    # Collect logs
    job_manager.collect_logs(outdir, rps, seq)

    # Delete job
    job_manager.delete_job()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run a single load pass and collect metrics.")
    parser.add_argument("--duration", type=str, default="1800s", help="Duration of test (default: 1)")
    parser.add_argument("--workers", type=int, default=1, help="Number of workers (default: 1)")
    parser.add_argument("--affinity", action="store_true", help="Enable CPU affinity")
    parser.add_argument("--outdir", type=str, default=".", help="Output directory (default: current directory)")
    parser.add_argument("--loadgen", type=str, default="oha", help="Load generator (default: oha)")
    parser.add_argument("rps", type=int, help="Requests per second")
    parser.add_argument("seq", type=int, help="Sequence number")

    args = parser.parse_args()

    run(args.outdir, args.rps, args.seq, args.duration,
        args.loadgen, args.workers, args.affinity)
