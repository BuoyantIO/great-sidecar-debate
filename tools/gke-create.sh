#!/bin/sh

CLUSTER_NAME="$1"
NODES="$2"

if [ -z "$CLUSTER_NAME" -o -z "$NODES" ]; then
  echo "Usage: $(basename $0) <cluster-name> <nodes>" >&2
  exit 1
fi

if [ $NODES -lt 1 ]; then
    echo "Node count must be at least 1" >&2
    exit 1
fi

if [ -z "$GKE_PROJECT" -o -z "$GKE_ZONE" ]; then
  echo "Set GKE_PROJECT to your GKE project ID; set GKE_ZONE to your GKE zone" >&2
  exit 1
fi

export KUBECONFIG=$HOME/.kube/${CLUSTER_NAME}.yaml

# MACHINE="e2-highcpu-4"
MACHINE="e2-standard-8"

gcloud beta container clusters create "$CLUSTER_NAME" \
    --project "$GKE_PROJECT" \
    --zone "$GKE_ZONE" \
    --tier "standard" \
    --no-enable-basic-auth \
    --cluster-version "1.31.6-gke.1020000" \
    --release-channel "regular" \
    --machine-type "$MACHINE" \
    --image-type "COS_CONTAINERD" \
    --disk-type "pd-balanced" \
    --disk-size "16" \
    --metadata disable-legacy-endpoints=true \
    --scopes "https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/monitoring","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly","https://www.googleapis.com/auth/trace.append" \
    --max-pods-per-node "110" \
    --spot \
    --num-nodes "$NODES" \
    --logging=SYSTEM,WORKLOAD \
    --monitoring=SYSTEM,STORAGE,POD,DEPLOYMENT,STATEFULSET,DAEMONSET,HPA,CADVISOR,KUBELET \
    --enable-ip-alias \
    --network "projects/linen-sun-453622-i5/global/networks/default" \
    --subnetwork "projects/linen-sun-453622-i5/regions/northamerica-northeast1/subnetworks/default" \
    --no-enable-intra-node-visibility \
    --default-max-pods-per-node "110" \
    --enable-ip-access \
    --security-posture=standard \
    --workload-vulnerability-scanning=disabled \
    --no-enable-google-cloud-access \
    --addons HorizontalPodAutoscaling,HttpLoadBalancing,GcePersistentDiskCsiDriver \
    --enable-autoupgrade \
    --enable-autorepair \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0 \
    --maintenance-window-start "2025-03-13T06:00:00Z" \
    --maintenance-window-end "2025-03-13T12:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR,SA,SU" \
    --binauthz-evaluation-mode=DISABLED \
    --autoscaling-profile optimize-utilization \
    --enable-managed-prometheus \
    --enable-vertical-pod-autoscaling \
    --enable-shielded-nodes \
    --shielded-integrity-monitoring \
    --no-shielded-secure-boot \
    --node-locations "northamerica-northeast1-a"
