# great-sidecar-debate

Tooling used for the Great Sidecar Debate date at KubeCon EU 2025 in London.

## License

This project is licensed under the Apache License, Version 2.0. See the
[LICENSE](LICENSE) file for details.

## Overview

Benchmarking is an art as much as a science; there are a quite of lot of
opinions and judgement calls in this code. The point is to be transparent so
that, if you disagree with our results, we can have a reasonable discussion
about it.

### Architecture

The benchmark used is simple: we run the [Faces demo app] and use a load
generator to supply load to its `face` workload. In turn, `face` then calls
`smiley` (using HTTP) and `color` (using gRPC). We use the Kubernetes metrics
API to get CPU and memory usage for all the pods in the cluster. Finally,
although **this benchmark is not designed for really reliable latency
results**, the load generator itself does report on latency.

[Faces demo app]: https://github.com/BuoyantIO/faces-demo

### Decisions

- **This benchmark is not designed for really reliable latency results.**
  Getting good results for resource usage while running on (probably
  virtualized) hardware in the cloud is not unreasonable, but getting good
  results for latency from that environment is a bit of a different story. We
  allow the load generator to report on latency, and we allow requesting plots
  of latency, but that's mostly because it was easy to do and we hope to be
  able to run this with dedicated on-prem hardware in the future.

- We run the load generator in the cluster: we want to benchmark the mesh
  here, not the external network or the ingress controller. Running the load
  generator as a Kubernetes Job means we don't have to worry about that.

- We run all data collection and analysis off-cluster; it's just easier. We
  are making API calls to the cluster under test while the benchmark is
  running to fetch metrics: this happens every 10 seconds and shouldn't be a
  huge burden, but in any case, it's the same for every test so it should
  factor out.

  Log collection from the load generator - for latency but more importantly to
  be certain of how many RPS we were actually able to do - happens after the
  run is complete, so it should be even lower impact.

- We let the load generator report on actual RPS and latency, because it's
  going to have a better view of these data than anything else in the system.

  - We could conceivably use the observability tools of whichever mesh we're
    running, but letting the load generator measure it from the client's PoV
    means that we don't have to load the cluster with a Prometheus stack, and
    we don't have to trust the mesh under test to get this right.

- We use the Kubernetes metrics API to get CPU and memory usage because,
  again, we don't really want to have to install a Prometheus stack in the
  cluster.

- For Istio Ambient, we always configure waypoints, even if we're not doing
  any actual L7 routing. This is because Linkerd and Istio Legacy both include
  L7 functionality, so an apples-to-apples comparison means that we need L7
  capabilities active.

### As discussed at KubeCon EU 2025

The Great Sidecar Debate talk at KubeCon EU 2025 used an older shell-based
version of this code that was _dramatically_ clumsier to run. This version is
much simpler for others to use, but the actual way in which the tests are
executed and the metrics are handled is the same code.

You can find graphs in `V1/Graphs`, and the raw metrics data in `V1/Data`. There are three directories in `V1/Data`:

- `ambient` contains the raw metrics data for an Istio Ambient sequence
- `linkerd` contains the raw metrics data for a Linkerd sequence
- `linkerd-2` contains the raw metrics data for another Linkerd sequence

The graphs committed here were generated with

```
python tools/plot.py V1/Data/{ambient,linkerd}/*.{csv,log}
```

Since V1 was using the same setup and collection mechanism, **it was also not
designed for really reliable latency numbers**. That's why there is no latency
graph in this repo.

The V1 test setup was:

- GKE cluster with 3 e2-standard-8 nodes
- 3 replicas of the Faces demo app (1 per node)
- 3 replicas of the load generator (1 per node)
- Linkerd edge-25.4.1 running in high availability mode (so 3 replicas of all
  control-plane workloads)
- Istio Ambient 1.25.0:
  - waypoint installed in the `faces` namespace per the quickstart
  - waypoint scaled to 3 replicas (1 per node) to match Linkerd HA
  - istiod scaled to 3 replicas (1 per node) to match Linkerd HA
- 5 runs each at 60, 120, 240, 600, and 1200 RPS
- 300s per run

To rerun that test setup with the current tooling:

- Set `MT_GKE_MACHINE=e2-standard-8` (without this, `tools/gke-create.sh` will
  use e2-standard-4 nodes make it possible to run four nodes on free-tier GKE
  accounts)
- Set `MT_NODES=3`
- After setting everything up, run

  `python tools/sequence.py linkerd --loadgen wrk2 --workers 3 --duration 300s`

  Do **not** set `--affinity`, since the V1 test ran the load generator on the
  application nodes.

## Usage

Broadly speaking, you're going to:

- set up your environment
- set up Python
- create a cluster
- optionally install a service mesh
- install the benchmark application
- run some benchmarks
- plot some results
- destroy the cluster

### Setting up your environment

Rather than passing things on the command line all the time, we use some
things from the environment:

- `MT_PLATFORM` is the kind of cluster you're going to use. Currently, the
  only supported values are `gke` and `k3d`, but contributions for other
  platforms would be great! If you set `MT_PLATFORM` to `gke`, you also need
  to set `GKE_PROJECT` and `GKE_ZONE` (see below).

- `MT_CLUSTER` is the name of the cluster you want to use for testing. There
  is a baked-in assumption that the file `$HOME/.kube/$MT_CLUSTER.yaml` exists
  and has the correct configuration.

  **DO NOT TRY TO USE A CLUSTER THAT IS ALREADY IN USE.** We assume that we
  can do anything we want to `$MT_CLUSTER`, notably including installing CRDs
  and service meshes.

- `MT_NODES` is the number of nodes in your cluster. Any value is OK, but be
  aware:

  - If you set `MT_NODES` to 1, we don't do any pod affinity or antiaffinity
    or the like, and `MT_PROFILE=ha` won't work for Linkerd.

  - If you set `MT_NODES` to 3, we'll do three replicas of the app, with
    antiaffinity set up so that each replica for each microservice is on a
    different node.

  - If you set `MT_NODES` higher than 3, we'll also label three of the nodes
    for the app and the rest for the load generator, and set up pod affinity
    so that the various components run only where they're supposed to.

- `MT_GKE_MACHINE` is the machine type to use for GKE clusters. The default is
  `e2-standard-4`, but you can set it to whatever you need.

- `MT_PROFILE` is the profile you want to use. The options are `ha` or `dev`;
  `ha` runs multiple replicas of the mesh control plane (and the waypoint, in
  Ambient's case), requires `MT_NODES` of at least 3, and is recommended when
  `MT_NODES` is at least 3. `dev` runs a single replica of the control plane.

- `MT_SERVICECIDR` is optional, and used only for Linkerd. If you set it,
  Linkerd will use it directly as the Service CIDR for your cluster; if you
  don't, Linkerd will try to figure out the Service CIDR directly from your
  cluster. If you're using GKE, this **requires** you to rename your cluster
  context to the short name of your GKE cluster (e.g. `test` instead of
  `gke_$project_$zone_test`).

- `GKE_PROJECT` and `GKE_ZONE` must be set if you want to use GKE clusters.

### Setting up Python

The benchmark code is written in Python, because doing everything in shell got
really awful really quickly. Start by creating a Python venv:

```bash
python3 -m venv venv
```

Then activate the venv:

```bash
source venv/bin/activate
```

Then install the dependencies:

```bash
pip install -r requirements.txt
```

At this point, you should be good to go.

### Creating a cluster

After setting up your environment, run

```bash
bash tools/cluster-create.sh
```

### Installing a service mesh

Next up, run one of

```bash
bash tools/no-mesh.sh [optional-args]
```

```bash
bash tools/linkerd.sh [optional-args]
```

```bash
bash tools/ambient.sh [optional-args]
```

or

```bash
bash tools/istio.sh [optional-args]
```

to install your mesh of choice (or, in the `no-mesh` case, no mesh at all),
and set things up to install Faces. For Istio Ambient use `ambient.sh`;
`istio.sh` is Istio **Legacy**.

At the moment, `linkerd.sh` will install whatever version of Linkerd your
`linkerd` CLI corresponds to, and `ambient.sh` and `istio.sh` will use
whatever version of `istioctl` you have installed. The `optional-args`, if
present, are passed directly to the `istioctl` or `linkerd` command, and are
ignored for `no-mesh.sh`.

### Installing the benchmark application

After installing a service mesh, run

```bash
bash tools/faces.sh
```

to install the Faces demo, which we use as a benchmark. In all cases, Faces
runs with three replicas of _everything_.

### Running the benchmark

Finally: to run a multiple-iteration sequence of benchmarks, use
`tools/sequence.py`; to run a single iteration of the benchmark, use
`tools/single.py`. Run either with `-h` to see their help and usage.

#### `sequence.py` basic usage

```bash
python tools/sequence.py MESH OUTDIR
```

(`MESH` here is really just a component of the output directory name -- if you
want to install Linkerd and then set `MESH` to `ambient`, that's fine, but it
will be a little confusing.)

By default, this will run a single loop of five runs at 60, 120, 240, 600, and
1200 RPS, writing the results into `${OUTDIR}/${MESH}-${LOOP:02d}` (which
means that each of those directories will end up with at least 50 files in it:
a metrics CSV and a logfile for each of the 5 runs for each of the 5 RPS
values).

You can also specify the number of loops to run with `--loops`, and the number
of runs to do at each RPS with `--runs`. If you have more than one loop,
you'll get `${OUTDIR}/${MESH}-00`, `${OUTDIR}/${MESH}-01`, etc. Runs translate
into sequence numbers for the files inside these output directories.

Finally, you can specify `--rps=RPS1,RPS2,...` to use a custom set of RPS
values.

**Note**: the specified RPS is across _all_ load generator pods, so if you say
`--rps 600 --workers 3` you'll get 200 RPS per load generator pod.

#### `single.py` basic usage

```bash
python tools/single.py --outdir OUTDIR RPS SEQ
```

Results will be written into

```
${OUTDIR}/${RPS}-${SEQ}-metrics.csv
```

and

```
${OUTDIR}/${RPS}-${SEQ}-oha-${POD}.log
```

where `RPS` is the requests per second you specify on the command line, and
`SEQ` is the sequence number you specify on the command line. (The sequence
number is uninterpreted; it just tracks multiple runs at the same RPS.)

**Note**: the specified RPS is across _all_ load generator pods, so if you say
`--rps 600 --workers 3` you'll get 200 RPS per load generator pod.

#### Common arguments

Both `single.py` and `sequence.py` take the following arguments:

- `--duration DURATION` sets the duration of each test run. The default is
  `1800s`.

- `--workers WORKERS` sets the number of load-generator pods. The default is
  1. If you set it higher than 1, you'll need at least that many nodes in your
  cluster since anti-affinity is automatically set.

- `--connections CONNECTIONS` sets the number of concurrent connections for
  the load generator to use. The default is 200.

- `--affinity` will require any load generator pods to be scheduled on a node
  tagged for the load generator. Without `--affinity`, load generators can go
  on any node.

- `--loadgen LOADGEN` will set the load generator. Currently supported are
  `oha` (the default) and `wrk2`:

  - `oha` is at <https://github.com/hatoo/oha>
  - `wrk2` is at <https://github.com/giltene/wrk2>

#### Interactive output

The main thing you'll see while the benchmark is running is a screen that'll
be updated every ten seconds or so:

```
2025-04-21 14:32:35 RUNNING OUT/gke-20250421T1429/linkerd-00/60-0-metrics.csv
--------

Node ...abe7a33-0f80  5.71% CPU,  2.68% mem:   224 mC (   24 -   245),  356 MiB ( 333 -  361)
Node ...abe7a33-7s8p  6.63% CPU,  3.04% mem:   260 mC (   23 -   269),  404 MiB ( 381 -  407)
Node ...abe7a33-j3vc  6.88% CPU,  2.12% mem:   270 mC (   25 -   270),  282 MiB ( 253 -  282)
Node ...abe7a33-khnq  4.62% CPU,  3.59% mem:   182 mC (   35 -   182),  478 MiB ( 458 -  481)

faces                                          405 mC (    1 -   408),   99 MiB (  47 -   99)
load                                            21 mC (   20 -    24),   12 MiB (   9 -   12)

gke                                             25 mC (   23 -    29),  269 MiB ( 256 -  269)
k8s                                            207 mC (   61 -   207),  806 MiB ( 794 -  806)

data-plane                                     267 mC (    6 -   267),  112 MiB (  93 -  112)
control-plane                                   13 mC (   11 -    16),  222 MiB ( 222 -  236)
mesh                                           279 mC (   17 -   279),  334 MiB ( 329 -  345)
non-mesh                                       425 mC (    1 -   427),  111 MiB (  47 -  111)
business                                       704 mC (   17 -   704),  444 MiB ( 375 -  453)

overhead                                       232 mC (   89 -   232), 1074 MiB (1050 - 1074)
total                                          935 mC (  106 -   935), 1518 MiB (1424 - 1526)

Mesh CPU ratio:            65.58% (smaller is better)
Mesh memory ratio:        303.36% (smaller is better)

Data plane CPU ratio:      62.70% (smaller is better)
Data plane memory ratio:  101.68% (smaller is better)

color app                                       45 mC (    1 -    45),   22 MiB (   6 -   23)
color mesh                                      34 mC (    1 -    34),   13 MiB (  12 -   13)
color2 app                                       1 mC (    0 -     1),    6 MiB (   6 -    6)
color2 mesh                                      1 mC (    1 -     1),   12 MiB (  12 -   12)
color3 app                                       1 mC (    0 -     1),    6 MiB (   6 -    6)
color3 mesh                                      1 mC (    1 -     1),   12 MiB (  12 -   12)
face app                                       310 mC (    1 -   313),   26 MiB (   7 -   26)
face mesh                                      142 mC (    1 -   143),   19 MiB (  12 -   19)
faces-gui app                                    1 mC (    0 -     1),    7 MiB (   7 -    7)
faces-gui mesh                                   1 mC (    1 -     1),   12 MiB (  12 -   12)
linkerd-destination mesh                        10 mC (    8 -    11),  118 MiB ( 118 -  123)
linkerd-identity mesh                            2 mC (    2 -     2),   45 MiB (  45 -   49)
linkerd-proxy-injector mesh                      2 mC (    2 -     3),   60 MiB (  60 -   65)
oha app                                         21 mC (   20 -    24),   12 MiB (   9 -   12)
oha mesh                                        38 mC (   29 -    38),    9 MiB (   9 -    9)
smiley app                                      51 mC (    1 -    51),   23 MiB (   6 -   23)
smiley mesh                                     52 mC (    1 -    53),   16 MiB (  12 -   16)
smiley2 app                                      1 mC (    0 -     1),    6 MiB (   6 -    6)
smiley2 mesh                                     1 mC (    1 -     1),   12 MiB (  12 -   12)
smiley3 app                                      1 mC (    0 -     1),    6 MiB (   6 -    6)
smiley3 mesh                                     1 mC (    1 -     1),   12 MiB (  12 -   12)
```

This shows the current run, the name of the output file, and a summary of the
results so far. Notes for making sense of things;

- CPU and memory usage is reported the same everywhere: `$CPU mC ( $min - $max
  ), $MEM MiB ( $min - $max)` where `$CPU` is the average CPU usage in
  millicores, `$MEM` is the average memory usage in MiB, and `$min` and `$max`
  are the minimum and maximum values for that metric over the life of the run.

- The first line will show the state: `STARTING`, `RUNNING`, or `DRAINING`.

  - `STARTING` means waiting for the Faces app to drop back to idle (below 10
    mC and 160MiB), since there's no point in letting noise from a previous
    interrupted run dirty up data collected. In this state, you won't see the
    minima and maxima for metrics actually get updated, and no results are
    being saved to disk.

  - `RUNNING` means that the benchmark is running. You'll see minima and
    maxima get updated, and metrics will be written to the output CSV shown on
    the top line.

  - `DRAINING` means that the test run is done and we're reading a few extra
    samples since the Kubernetes metrics API lags the real world. If Faces
    becomes idle again during this period, draining is stopped; otherwise, it
    will go for a maximum of 60 seconds. Data _are_ recorded during this
    phase.

- The "Node" lines show the CPU and memory actually allocated for each node in
  the cluster, shown both as a percentage of the node's available CPU and
  memory, and as actual usage. Remember that you won't see the minima and
  maxima updating correctly during the `STARTING` phase.

- After the node lines come the usage lines, all of which are the same. Again,
  you won't see the minima and maxima update correctly during the `STARTING`
  phase.

- The top several lines are aggregates of several components:

  - `faces` is the sum of _all_ the application components: everything in the
    `faces` namespace, but not counting sidecars (if any are present).

  - `load` is the load generator pods (either `wrk2` or `oha`), again not
    counting sidecars (if any are present).

  - `data-plane` is the sum of _all_ the data plane proxies. For Linkerd, this
    includes the sidecars for _every_ pod in the cluster, except for the
    Linkerd control plane components. For Istio Ambient, this includes all
    ztunnels and all waypoints. For Istio Legacy, it includes all Istio
    sidecars.

  - `control-plane` is the sum of all the control plane components. For
    Linkerd, this is everything in the `linkerd` namespace; for Istio (either
    mode), it's everything in the `istio-system` namespace.

  - `k8s` is the Kubernetes control plane (everything in the `kube-system`
    namespace).

  - `gke` is extra overhead for GKE clusters (everything in namespaces
    starting with `gke-` or `gmp-`).

  - `overhead` is the sum of `k8s` and `gke`.

  - `mesh` is the sum of `data-plane` and `control-plane`.

  - `non-mesh` is the sum of `faces` and `load`.

  - `business` is the sum of `mesh` and `non-mesh`: the minimum resource
    consumed to actually run stuff to meet your business goals (we assume the
    mesh is needed).

  - `total` is everything in the cluster (the sum of `business` and `overhead`).

  The math always operates in nanocores and bytes, then the results are
  rounded for display.

- `Mesh CPU ratio` and `Mesh memory ratio` are the average CPU and memory
  usage of the mesh (control plane plus data plane) divided by the average CPU
  and memory usage of the non-mesh part of the cluster (the application and
  load generator). Since the mesh would be zero-cost in a perfect world, lower
  is better.

  This is displayed just because I was curious. It's not stored in the output
  files.

- `Data plane CPU ratio` and `Data plane memory ratio` are like the `Mesh`
  ratios, but it's the data-plane resource usage rather than the entire mesh.
  Again, lower is better, and again, it's only displayed, not stored.

- At the bottom, you'll see many things broken down by component, as a sanity
  check. Note that things with multiple replicas get summed together into a
  single component.

### Plotting results

To plot the results, run

```bash
python [--interactive] [--latency] tools/plot.py OUTDIR/*
```

and you'll get plots of the data plane CPU and memory usage. With `--latency`, you'll also get a latency graph.

With `--interactive`, the plots will be displayed on screen and not saved
anywhere. Without `--interactive`, the plots will be saved as
`data-plane-CPU.png` and `data-plane-MEM.png` in your current directory (and
`latency.png` if requested).


### Destroying the cluster

Just run

```bash
bash tools/delete-cluster.sh
```

to destroy the cluster you created.
