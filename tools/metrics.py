import sys

import csv
import datetime
import os
import time

import kube_utils

from kubernetes import client, config


def clear():
    return "\033[H\033[J"


def build_field_names(nodes):
    field_names = [ "timestamp" ]

    for node in nodes.values():
        field_names.append(f"{node.name} CPU")
        field_names.append(f"{node.name} allocatable CPU")
        field_names.append(f"{node.name} mem")
        field_names.append(f"{node.name} allocatable mem")

    for element in [ "faces", "load", "iperf", "gke", "k8s",
                     "data-plane", "control-plane", "mesh", "non-mesh",
                     "business", "overhead", "total" ]:
        field_names.append(f"{element} CPU")
        field_names.append(f"{element} mem")

    for element in [ "load app", "load mesh", "wrk2 app", "wrk2 mesh",
                     "iperf app", "iperf mesh", "iperf-client app", "iperf-client mesh",
                     "faces-gui app", "faces-gui mesh", "face app", "face mesh",
                     "smiley app", "smiley mesh", "smiley2 app", "smiley2 mesh",
                     "smiley3 app", "smiley3 mesh", "color app", "color mesh",
                     "color2 app", "color2 mesh", "color3 app", "color3 mesh",
                     "linkerd-destination mesh", "linkerd-identity mesh",
                     "linkerd-proxy-injector mesh",
                     "istiod mesh", "istio-ingressgateway mesh", "waypoint mesh",
                     "ztunnel mesh" ]:
        field_names.append(f"{element} CPU")
        field_names.append(f"{element} mem")

    return field_names


def get_pod_metrics(v1, metrics_api):
    metrics = []

    pod_info = v1.list_pod_for_all_namespaces(watch=False).items

    node_map = {
        pod_info[i].metadata.name: pod_info[i].spec.node_name
        for i in range(len(pod_info))
    }

    pod_metrics = metrics_api.list_cluster_custom_object('metrics.k8s.io', 'v1beta1', 'pods')

    for pod in pod_metrics["items"]:
        pod_id, pod_name, pod_namespace = kube_utils.get_pod_id(pod)

        for container in pod["containers"]:
            cpu_usage = container["usage"]["cpu"]
            cpu_nano = kube_utils.nanocores(cpu_usage)

            memory_usage = container["usage"]["memory"]
            memory_bytes = kube_utils.bytes(memory_usage)

            metrics.append({
                "pod_id": pod_id,
                "pod": pod_name,
                "node": node_map.get(pod_name, "unknown"),
                "container": container["name"],
                "namespace": pod_namespace,
                "usage": {
                    "cpu": cpu_nano,
                    "memory": memory_bytes
                }
            })

    return metrics


class MinMax:
    '''MinMax tracks a current value plus its minimum and maximum.'''
    def __init__(self):
        self.current = 0.0
        self.min = None
        self.max = None

    def zero(self):
        '''
        Reset the current value to zero, without touching the min and max.
        '''

        self.current = 0.0

    def add(self, value):
        '''
        Add to the current value, without affecting the min and max. What's going on
        here is that since we're building up our values piecemeal, we can't know when
        the buildup is done without an external signal to tell us that it's OK to
        update the min & max.
        '''
        self.current += value

    def update(self):
        '''
        Update the min & max. What's going on here is that since we're
        building up our values piecemeal, we can't know when the buildup is
        done without an external signal to tell us that it's OK to update the
        min & max.
        '''
        if self.min is None:
            self.min = self.current
            self.max = self.current
            return

        self.min = min(self.min, self.current)
        self.max = max(self.max, self.current)

    def __str__(self):
        return f"{self.current:7.2f} ({self.min:7.2f} - {self.max:7.2f})"


class Usage:
    '''Usage tracks CPU and memory usage, using a MinMax for each.'''
    def __init__(self):
        self.cpu = MinMax()
        self.memory = MinMax()

    def zero(self):
        '''
        Zero both CPU & memory.
        '''
        self.cpu.zero()
        self.memory.zero()

    def add(self, cpu, memory):
        '''
        Add CPU & memory usage.
        '''
        self.cpu.add(cpu)
        self.memory.add(memory)

    def update(self):
        '''
        Update minimum & maximum CPU & memory.
        '''
        self.cpu.update()
        self.memory.update()

    def __str__(self):
        cpu_cur = (self.cpu.current + 999_999) // 1_000_000
        cpu_min = cpu_cur
        cpu_max = cpu_cur

        if self.cpu.min is not None:
            cpu_min = (self.cpu.min + 999_999) // 1_000_000

        if self.cpu.max is not None:
            cpu_max = (self.cpu.max + 999_999) // 1_000_000

        memory_cur = (self.memory.current + 1048575) // 1048576
        memory_min = memory_cur
        memory_max = memory_cur

        if self.memory.min is not None:
            memory_min = (self.memory.min + 1048575) // 1048576

        if self.memory.max is not None:
            memory_max = (self.memory.max + 1048575) // 1048576

        return "%5d mC (%5d - %5d), %4d MiB (%4d - %4d)" % (cpu_cur, cpu_min, cpu_max, memory_cur, memory_min, memory_max)


class Node:
    def __init__(self, node_info):
        self.name = node_info.metadata.name
        self.allocatable_cpu = kube_utils.nanocores(node_info.status.allocatable["cpu"])
        self.allocatable_memory = kube_utils.bytes(node_info.status.allocatable["memory"])
        self.reinit()

    def reinit(self):
        self.assigned = Usage()

    def zero(self):
        self.assigned.zero()

    def add(self, resource):
        self.assigned.add(resource["cpu"], resource["memory"])

    def update(self):
        self.assigned.update()

    def shortname(self, maxlen=8):
        """
        Return a short name for the node, truncated to maxlen characters.
        """
        if len(self.name) <= maxlen:
            return self.name

        return "..." + self.name[-(maxlen - 3):]

    def __str__(self):
        cpu_ratio = self.assigned.cpu.current / self.allocatable_cpu
        memory_ratio = self.assigned.memory.current / self.allocatable_memory

        return f"{cpu_ratio:6.2%} CPU, {memory_ratio:6.2%} mem: {self.assigned}"


def get_nodes(v1):
    nodes = {}

    for node_info in v1.list_node().items:
        node = Node(node_info)
        nodes[node.name] = node

    return nodes


class AggregateUsage:
    def __init__(self, client, output_path):
        self.metrics_api = client.CustomObjectsApi()
        self.v1 = client.CoreV1Api()
        self.nodes = get_nodes(self.v1)

        self.state = "STARTING"
        self.idle = False
        self.collecting = False
        self.field_names = build_field_names(self.nodes)
        self.field_names_set = set(self.field_names)

        self.classifier = kube_utils.Classifier()

        self.output_path = output_path
        self.writer = None
        self.csv_output = None

        if self.output_path:
            self.csv_output = open(self.output_path, mode='w', newline='')

            self.writer = csv.DictWriter(self.csv_output, fieldnames=self.field_names)
            self.writer.writeheader()

        self.reinit()

    def reinit(self):
        self.usages = {}
        self.pod_usages = {}

    def is_collecting(self):
        return self.collecting

    def is_idle(self):
        return self.idle

    def start_collecting(self):
        if self.state != "STARTING":
            raise RuntimeError("Cannot start collecting when not in STARTING state")

        self.collecting = True
        self.state = "RUNNING"

    def stop_collecting(self):
        self.collecting = False
        self.state = "FINISHING"

        if self.csv_output:
            self.csv_output.close()
            self.csv_output = None

        if self.writer:
            self.writer = None

    def start_draining(self):
        self.state = "DRAINING"

    def zero(self):
        if not self.collecting:
            self.reinit()

            for node in self.nodes.values():
                node.reinit()

        for type in self.usages.keys():
            for usage in self.usages[type].values():
                usage.zero()

        # Zero node assignments for a new sample
        for node in self.nodes.values():
            node.zero()

    def _add(self, type, key, cpu, memory):
        if type not in self.usages:
            self.usages[type] = {}

        if key not in self.usages[type]:
            self.usages[type][key] = Usage()

        self.usages[type][key].add(cpu, memory)

    def add(self, pod_id, classification, cpu, memory):
        type = "normal"
        include_in_real = True

        if classification.overhead:
            type = "overhead"
            include_in_real = False
        elif classification.mesh:
            self._add("pod", f"{pod_id} mesh", cpu, memory)
        else:
            self._add("pod", f"{pod_id} app", cpu, memory)

        if not classification.mesh:
            self._add(type, classification.component, cpu, memory)

        if include_in_real:
            self._add("synth", "business", cpu, memory)

            if classification.mesh:
                self._add("mesh", classification.component, cpu, memory)
                self._add("synth", "mesh", cpu, memory)
            else:
                self._add("synth", "non-mesh", cpu, memory)
        else:
            self._add("synth", "overhead", cpu, memory)

        self._add("synth", "total", cpu, memory)

    def update(self):
        for type in self.usages.keys():
            for usage in self.usages[type].values():
                usage.update()

        for node in self.nodes.values():
            node.update()

    def items(self):
        for type in [ "normal", "", "overhead", "", "mesh" ]:
            if not type:
                yield "", "", None
                continue

            if type in self.usages:
                for key, value in self.usages[type].items():
                    yield type, key, value

        synth_keys = [ "mesh", "non-mesh", "business", "", "overhead", "total" ]
        synth_keys_set = set(synth_keys)

        for key in self.usages["synth"].keys():
            if key not in synth_keys_set:
                yield "synth", key, self.usages["synth"][key]

        for key in synth_keys:
            usage = Usage()

            if key and key in self.usages["synth"]:
                usage = self.usages["synth"][key]

            yield "synth", key, usage

        yield "", "", None

        for key in sorted(self.usages["pod"].keys()):
            yield "pod", key, self.usages["pod"][key]

    def calc_ratio(self, v1, v2, limit):
        if v1 < limit or v2 < limit:
            return "--------"

        ratio = (v1 / v2) * 100.0
        return f"{ratio:7.2f}%"

    def ratio(self, type1, key1, type2, key2):
        e1 = self.usages[type1][key1]
        e2 = self.usages[type2][key2]

        if not e1 or not e2:
            return "---?--- "

        # This constant is 0.01 cores expressed in nanocores
        cpu_str = self.calc_ratio(e1.cpu.current, e2.cpu.current, 10000000)

        # This constant is 0.01 MiB expressed in bytes (rounded down)
        memory_str = self.calc_ratio(e1.memory.current, e2.memory.current, 10485)

        return (cpu_str, memory_str)

    def sample(self, interactive=False):
        """
        Grab a sample of current resource usage, and update all our various fields
        from it.
        """
        now = datetime.datetime.now()

        metrics = get_pod_metrics(self.v1, self.metrics_api)

        # This will continuously reinitialize the AggregateUsage object
        # until we explicitly mark it as ready to go.
        self.zero()

        for metric in sorted(metrics, key=lambda x: (x["namespace"], x["pod"], x["container"] == "linkerd-proxy", x["container"])):
            pod_id = metric["pod_id"]
            namespace = metric["namespace"]
            container = metric["container"]
            node = metric["node"]
            node_info = self.nodes.get(node)

            if node_info:
                node_info.add(metric["usage"])
            else:
                raise RuntimeError(f"WARNING: pod {pod_id} in {namespace} on unknown node {node}")

            classification = self.classifier.lookup(pod_id, container, namespace)

            self.add(pod_id, classification, metric["usage"]["cpu"], metric["usage"]["memory"])

        self.update()

        formatted_now = now.strftime("%Y-%m-%d %H:%M:%S")
        csv_row = { "timestamp": formatted_now }

        for node in self.nodes.values():
            csv_row[f"{node.name} CPU"] = node.assigned.cpu.current
            csv_row[f"{node.name} allocatable CPU"] = node.allocatable_cpu
            csv_row[f"{node.name} mem"] = node.assigned.memory.current
            csv_row[f"{node.name} allocatable mem"] = node.allocatable_memory

        if interactive:
            # Clear the screen and print the header before anything else.
            print(clear(), end="")
            print(f"{formatted_now} {self.state} {self.output_path}\n--------\n")

            for node in self.nodes.values():
                print(f"Node {node.shortname(15):15s} {node}")

            print("")

        last_type = None

        for type, key, usage in self.items():
            # First, save to the CSV row.
            cpu_key = key + " CPU"
            mem_key = key + " mem"

            if cpu_key in self.field_names_set:
                csv_row[cpu_key] = int(usage.cpu.current)

            if mem_key in self.field_names_set:
                csv_row[mem_key] = int(usage.memory.current)

            # Next, figure out if we need to start collecting.

            if key == "faces":
                # Is the Faces application back down to idle? We want to see it less than
                # 10 mC and 160 MiB.

                if usage.cpu.current < 100_000_000 and usage.memory.current < (1048576 * 160):
                    self.idle = True
                    if not self.collecting:
                        self.start_collecting()
                else:
                    self.idle = False

            # Finally, add more to our interactive display if we're doing that.
            if interactive:
                if not key:
                    print("")
                    continue

                if type != last_type:
                    last_type = type

                    if (type == "pod") and "mesh" in self.usages:
                        cpu_ratio, memory_ratio = self.ratio("synth", "mesh", "synth", "non-mesh")

                        print(f"Mesh CPU ratio:          {cpu_ratio:8s} (smaller is better)")
                        print(f"Mesh memory ratio:       {memory_ratio:8s} (smaller is better)")

                        cpu_ratio, memory_ratio = self.ratio("mesh", "data-plane", "synth", "non-mesh")

                        print(f"\nData plane CPU ratio:    {cpu_ratio:8s} (smaller is better)")
                        print(f"Data plane memory ratio: {memory_ratio:8s} (smaller is better)")

                        print("")

                print(f"{key:44s} {usage}")

        if self.collecting:
            if self.writer:
                self.writer.writerow(csv_row)
                self.csv_output.flush()


def main():
    config.load_kube_config()

    agg = AggregateUsage(client, sys.argv[1])

    while True:
        agg.sample(True)
        time.sleep(10)


if __name__ == "__main__":
    main()
