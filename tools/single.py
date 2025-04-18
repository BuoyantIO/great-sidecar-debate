import os
import sys
import time
import signal
import yaml

from kubernetes import client, config
from kubernetes.utils import create_from_yaml

from metrics import AggregateUsage

node_affinity_stanza = yaml.safe_load("""
requiredDuringSchedulingIgnoredDuringExecution:
  nodeSelectorTerms:
  - matchExpressions:
    - key: buoyant.io/meshtest-role
      operator: In
      values:
      - load
""")

pod_anti_affinity_stanza = yaml.safe_load("""
preferredDuringSchedulingIgnoredDuringExecution:
- weight: 100
  podAffinityTerm:
    labelSelector:
      matchExpressions:
      - key: faces.buoyant.io/component
        operator: In
        values:
        - wrk2
    topologyKey: kubernetes.io/hostname
""")

wrk2_job_path = os.path.join(os.path.dirname(__file__), "wrk2.yaml")
wrk2_job = yaml.safe_load(open(wrk2_job_path).read())

def main(outdir, mesh, rps, seq, workers=1, affinity=False):
    config.load_kube_config()
    batch_v1 = client.BatchV1Api()
    core_v1 = client.CoreV1Api()

    outfile = os.path.join(outdir, f"{mesh}/{rps}-{seq}-metrics.csv")

    agg = AggregateUsage(outfile)

    podrps = int(rps) // workers
    print(f"Starting {outdir} {rps}-{seq}... (load pods {workers}, per-pod RPS {podrps})")

    # Delete existing job
    try:
        batch_v1.delete_namespaced_job(name="wrk2", namespace="faces", propagation_policy="Foreground")
        print("Deleted existing job")
    except client.exceptions.ApiException as e:
        if e.status != 404:
            raise
        print("No existing job to delete")

    # Customize the Job spec as needed
    wrk2_job_spec = wrk2_job["spec"]
    wrk2_template_spec = wrk2_job["spec"]["template"]["spec"]
    wrk2_template_spec["containers"][0]["command"] = [
        "/wrk",
        "-t", "8",
        "-c", "200",
        "-d", "60s",
        "-R", str(podrps),
        "--latency",
        "http://face/",
    ]

    affinity_stanza = {}

    if workers > 1:
        wrk2_job_spec["parallelism"] = workers
        wrk2_job_spec["completions"] = workers
        affinity_stanza["podAntiAffinity"] = pod_anti_affinity_stanza

    if affinity:
        affinity_stanza["nodeAffinity"] = node_affinity_stanza

    if affinity_stanza:
        wrk2_template_spec["affinity"] = affinity_stanza

    # yaml_content = yaml.safe_dump(wrk2_job, default_flow_style=False)
    create_from_yaml(client.ApiClient(), yaml_objects=[ wrk2_job ], namespace="faces")

    # Wait for job to start
    left = 10
    while left > 0:
        print(f"Waiting for wrk2 to start... ({left})")
        time.sleep(10)
        left -= 1

        job = batch_v1.read_namespaced_job(name="wrk2", namespace="faces")
        if job.status.ready == workers:
            break

    if left == 0:
        print("wrk2 did not start")
        sys.exit(1)

    print("wrk2 job running")

    # Grab samples until our job is finished...
    while True:
        now = agg.sample()
        agg.display(now)
        time.sleep(10)

        job = batch_v1.read_namespaced_job(name="wrk2", namespace="faces")
        if job.status.succeeded == workers:
            break

    # Collect for another bit longer to see a bit of tailing off...
    print("wrk2 job finished, collecting for another 60 seconds...")
    agg.state = "FINISHING"

    for _ in range(6):
        now = agg.sample()
        agg.display(now)
        time.sleep(10)

    print("wrk2 job finished")
    print("Collecting logs...")

    # Collect logs
    pods = core_v1.list_namespaced_pod(namespace="faces",
                                       label_selector="batch.kubernetes.io/job-name=wrk2")

    for i, pod in enumerate(pods.items, start=1):
        pod_name = pod.metadata.name
        log = core_v1.read_namespaced_pod_log(name=pod_name, namespace="faces")

        with open(f"{outdir}/{rps}-{seq}-{pod_name}.log", "w") as f:
            f.write(log)

    # Delete job
    batch_v1.delete_namespaced_job(name="wrk2", namespace="faces", propagation_policy="Foreground")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run wrk2 job and collect metrics.")
    parser.add_argument("--workers", type=int, default=1, help="Number of workers (default: 1)")
    parser.add_argument("--affinity", action="store_true", help="Enable CPU affinity")
    parser.add_argument("--outdir", type=str, default=".", help="Output directory (default: current directory)")
    parser.add_argument("mesh", type=str, help="Mesh name")
    parser.add_argument("rps", type=int, help="Requests per second")
    parser.add_argument("seq", type=int, help="Sequence number")

    args = parser.parse_args()

    main(args.outdir, args.mesh, args.rps, args.seq, workers=args.workers, affinity=args.affinity)
