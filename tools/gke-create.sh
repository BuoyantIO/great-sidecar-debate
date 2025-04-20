#!/bin/sh

root=$(dirname $0)
. "$root/check-env.sh"

export KUBECONFIG=$HOME/.kube/${MT_CLUSTER}.yaml

if [ -z "$GKE_PROJECT" -o -z "$GKE_ZONE" ]; then
  echo "Set GKE_PROJECT to your GKE project ID; set GKE_ZONE to your GKE zone" >&2
  exit 1
fi

# Use e2-standard-4 unless MT_GKE_MACHINE overrides it.
MACHINE="${MT_GKE_MACHINE:-e2-standard-4}"

set -e -u
set -o pipefail

gcloud beta container clusters create "$MT_CLUSTER" \
    --project "$GKE_PROJECT" \
    --zone "$GKE_ZONE" \
    --tier "standard" \
    --no-enable-basic-auth \
    --cluster-version "1.31.6-gke.1064001" \
    --release-channel "regular" \
    --machine-type "$MACHINE" \
    --image-type "COS_CONTAINERD" \
    --disk-type "pd-balanced" \
    --disk-size "16" \
    --metadata disable-legacy-endpoints=true \
    --scopes "https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/monitoring","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly","https://www.googleapis.com/auth/trace.append" \
    --max-pods-per-node "110" \
    --spot \
    --num-nodes "$MT_NODES" \
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

if [ $MT_NODES -gt 1 ]; then
  # Label the k3d agents for the Faces app.
  i=0

  app_nodes=$MT_NODES
  load_nodes=0

  if [ $app_nodes -gt 3 ]; then
    app_nodes=3
  fi

  load_nodes=$(( $MT_NODES - $app_nodes ))

  for node in $(kubectl get nodes -o name); do
    if [ $i -lt $app_nodes ]; then
      echo "Labeling $node as app"
      kubectl label $node buoyant.io/meshtest-role=app
    else
      echo "Labeling $node as load"
      kubectl label $node buoyant.io/meshtest-role=load
    fi

    i=$(( $i + 1 ))
  done
fi
