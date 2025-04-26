special_ids = [
    "pdcsi-node",
    "kube-proxy",
    "collector",
    "ztunnel",
    "oha",
    "wrk2",
]

def get_pod_id(pod):
    pod_name = None
    pod_namespace = None
    pod_labels = None

    if hasattr(pod, "metadata"):
        pod_name = pod.metadata.name
        pod_namespace = pod.metadata.namespace
        pod_labels = pod.metadata.labels
    elif "metadata" in pod:
        pod_name = pod["metadata"]["name"]
        pod_namespace = pod["metadata"]["namespace"]
        pod_labels = pod["metadata"]["labels"]

    if not pod_name:
        raise ValueError("pod has no name")

    if not pod_namespace:
        raise ValueError("pod has no namespace")

    if not pod_labels:
        raise ValueError("pod has no labels")

    pod_id = pod_name

    if "pod-template-hash" in pod_labels:
        pthash = pod_labels["pod-template-hash"]
        pod_id = pod_id.split(f"-{pthash}")[0]
    elif "component" in pod_labels:
        pod_id = pod_labels["component"]
    else:
        for special_id in special_ids:
            if pod_name.startswith(special_id):
                pod_id = special_id
                break

    return pod_id, pod_name, pod_namespace


def old_get_pod_id(pod):
    """
    Take a pod data structure as returned by the Kubernetes API and
    return a string that identifies the pod: e.g. if the Pod is named
    gmp-operator-69bfb6d858-hrnjd and is owned by the gmp-operator-69bfb6d858
    ReplicaSet, return 'gmp-operator'. The idea is to get the simplest name
    that groups all related pods together.
    """

    pod_name = pod.metadata.name
    pfx = pod.metadata.generate_name

    if pfx and pfx.endswith("-"):
        pfx = pfx[:-1]

    orefs = pod.metadata.owner_references
    owner_type = None
    owner_name = None

    for oref in orefs:
        if oref.kind and oref.name:
            owner_type = oref.kind
            owner_name = oref.name
            break

    if owner_type == "ReplicaSet":
        pfx = "-".join(pfx.split("-")[:-1])

    pod_id = pod_name

    if pfx and pod_id.startswith(f"{pfx}-"):
        pod_id = pfx
    elif (not pfx) and pod_id.endswith(f"-{owner_name}"):
        # This is a special case for the GKE (at least) kube-proxy.
        pod_id = pod_id[:-len(owner_name)-1]

    return pod_id


class Classification:
    def __init__(self, mesh, overhead, component, process):
        self.mesh = mesh
        self.overhead = overhead
        self.component = component
        self.process = process

    @classmethod
    def data_plane(cls, process):
        return cls(True, False, "data-plane", process)

    @classmethod
    def control_plane(cls, process):
        return cls(True, False, "control-plane", process)

    @classmethod
    def iperf(cls, process):
        return cls(False, False, "iperf", process)

    @classmethod
    def faces(cls, process):
        return cls(False, False, "faces", process)

    @classmethod
    def load(cls, process):
        return cls(False, False, "load", process)

    @classmethod
    def gke(cls, process):
        return cls(False, True, "gke", process)

    @classmethod
    def k8s(cls, process):
        return cls(False, True, "k8s", process)

    @classmethod
    def unknown(cls, process):
        return cls(False, False, "unknown", process)

    def __str__(self):
        return f"M:{self.mesh} O:{self.overhead} C:{self.component} P:{self.process}"


class Classifier:
    gke_namespaces = { "gke-managed-cim",
                       "gke-managed-system",
                       "gke-managed-volumepopulator",
                       "gmp-public",
                       "gmp-system" }

    k8s_namespaces = { "kube-node-lease", "kube-public", "kube-system" }

    def __init__(self):
        self.cache = {}

    def lookup(self, prefix, container, namespace):
        ckey = f"{prefix}/{container}/{namespace}"

        if ckey in self.cache:
            return self.cache[ckey]

        if namespace == "linkerd":
            # Stuff in the linkerd namespace is defined to be the mesh control
            # plane.
            classification = Classification.control_plane(prefix)
        elif container == "linkerd-proxy":
            # The Linkerd proxy container, when outside of the linkerd
            # namespace, is part of the mesh data plane.
            classification = Classification.data_plane("linkerd-proxy")
        elif container == "istio-proxy":
            # Same for the Istio proxy.
            classification = Classification.data_plane("istio-proxy")
        elif prefix == "waypoint":
            # Same for the waypoint.
            classification = Classification.data_plane("waypoint")
        elif prefix == "ztunnel":
            # Same for the ztunnel.
            classification = Classification.data_plane("ztunnel")
        elif (prefix == "iperf") or (prefix == "iperf-client"):
            # The iperf and iperf-client containers are not part of the mesh.
            classification = Classification.iperf(prefix)
        elif (prefix == "load") or (prefix == "wrk2") or (prefix == "oha"):
            # The load, wrk2, and oha containers are load generators.
            classification = Classification.load(prefix)
        elif namespace == "faces":
            # Other things in the faces namespace are part of Faces.
            classification = Classification.faces(prefix)
        elif namespace == "istio-system":
            # Other things in the istio-sytem namespace are part of the mesh
            # control plane.
            classification = Classification.control_plane(prefix)
        elif namespace in self.gke_namespaces:
            # Other things in the GKE-managed namespaces are part of the GKE
            # control plane.
            classification = Classification.gke(prefix)
        elif namespace in self.k8s_namespaces:
            # Other things in the Kubernetes-managed namespaces are part of the
            # Kubernetes control plane.
            classification = Classification.k8s(prefix)
        else:
            # Everything else is unknown.
            classification = Classification.unknown(prefix)

        self.cache[ckey] = classification
        return classification


def nanocores(cpu_usage):
    try:
        if cpu_usage.endswith('n'):
            return int(cpu_usage[:-1])
        elif cpu_usage.endswith('u'):
            return int(cpu_usage[:-1]) * 1000
        elif cpu_usage.endswith('m'):
            return int(cpu_usage[:-1]) * 1000000
        else:
            return int(cpu_usage) * 1000000000
    except ValueError:
        raise ValueError(f"invalid CPU value: {cpu_usage}")

def bytes(memory_usage):
    try:
        if memory_usage.endswith('K'):
            return int(memory_usage[:-1]) * 1024
        elif memory_usage.endswith('Ki'):
            return int(memory_usage[:-2]) * 1024
        elif memory_usage.endswith('M'):
            return int(memory_usage[:-1]) * 1024 * 1024
        elif memory_usage.endswith('Mi'):
            return int(memory_usage[:-2]) * 1024 * 1024
        elif memory_usage.endswith('G'):
            return int(memory_usage[:-1]) * 1024 * 1024 * 1024
        elif memory_usage.endswith('Gi'):
            return int(memory_usage[:-2]) * 1024 * 1024 * 1024
        elif memory_usage.endswith('T'):
            return int(memory_usage[:-1]) * 1024 * 1024 * 1024 * 1024
        elif memory_usage.endswith('Ti'):
            return int(memory_usage[:-2]) * 1024 * 1024 * 1024 * 1024
        elif memory_usage.endswith('P'):
            return int(memory_usage[:-1]) * 1024 * 1024 * 1024 * 1024 * 1024
        elif memory_usage.endswith('Pi'):
            return int(memory_usage[:-2]) * 1024 * 1024 * 1024 * 1024 * 1024
        elif memory_usage.endswith('E'):
            return int(memory_usage[:-1]) * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
        elif memory_usage.endswith('Ei'):
            return int(memory_usage[:-2]) * 1024 * 1024 * 1024 * 1024 * 1024 * 1024
        else:
            return int(memory_usage)
    except ValueError:
        raise ValueError(f"invalid memory value: {memory_usage}")