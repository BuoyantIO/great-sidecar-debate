#!/bin/bash

root=$(dirname $0)
. "$root/check-env.sh"

set -e
set -o pipefail

export KUBECONFIG=$HOME/.kube/${MT_CLUSTER}.yaml

if ! command -v istioctl &> /dev/null; then
  echo "istioctl could not be found. Please ensure it is installed and added to your PATH."
  exit 1
fi

EXTRA_ARGS="$@"

# EXTRA_ARGS that you might play with:
# --set values.global.waypoint.resources.limits.cpu
# --set values.global.waypoint.resources.limits.memory

if [ "$MT_PROFILE" = "ha" ]; then
  EXTRA_ARGS="$EXTRA_ARGS --set values.pilot.autoscaleMin=3"
fi

echo "Installing Gateway API"
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.1/standard-install.yaml

if [ "$MT_PLATFORM" == "gke" ]; then
  kubectl create clusterrolebinding cluster-admin-binding \
      --clusterrole=cluster-admin \
      --user=$(gcloud config get-value core/account)

  kubectl create namespace istio-system

  kubectl apply -f - <<EOF
apiVersion: v1
kind: ResourceQuota
metadata:
  name: gcp-critical-pods
  namespace: istio-system
spec:
  hard:
    pods: 1000
  scopeSelector:
    matchExpressions:
    - operator: In
      scopeName: PriorityClass
      values:
      - system-node-critical
EOF
fi

set -x
istioctl install --set profile=ambient --set values.global.platform=$MT_PLATFORM $EXTRA_ARGS -y

kubectl create namespace faces
kubectl label namespace faces istio.io/dataplane-mode=ambient
istioctl waypoint apply --for all -n faces --enroll-namespace --overwrite

if [ "$MT_PROFILE" == "ha" ]; then
  kubectl patch deployment -n istio-system istiod --type='json' -p='[{"op": "add", "path": "/spec/template/spec/affinity", "value": {"podAntiAffinity": {"preferredDuringSchedulingIgnoredDuringExecution": [{"weight": 100, "podAffinityTerm": {"labelSelector": {"matchExpressions": [{"key": "app.kubernetes.io/name", "operator": "In", "values": ["istiod"]}]}, "topologyKey": "kubernetes.io/hostname"}}]}}}]'
  kubectl patch deployment -n faces waypoint --type='json' -p='[{"op": "add", "path": "/spec/template/spec/affinity", "value": {"podAntiAffinity": {"preferredDuringSchedulingIgnoredDuringExecution": [{"weight": 100, "podAffinityTerm": {"labelSelector": {"matchExpressions": [{"key": "gateway.networking.k8s.io/gateway-name", "operator": "In", "values": ["waypoint"]}]}, "topologyKey": "kubernetes.io/hostname"}}]}}}]'

  if [ "$MT_NODES" -gt 3 ]; then
    kubectl patch deployment -n faces waypoint --type='json' -p='[{"op": "add", "path": "/spec/template/spec/affinity/nodeAffinity", "value": {"requiredDuringSchedulingIgnoredDuringExecution": {"nodeSelectorTerms": [{"matchExpressions": [{"key": "buoyant.io/meshtest-role", "operator": "In", "values": ["app"]}]}]}}}]'
  fi

  kubectl scale -n istio-system deployment istiod --replicas=3
  kubectl scale -n faces deployment waypoint --replicas=3

  kubectl rollout status -n istio-system deployment istiod
  kubectl rollout status -n faces deployment waypoint

  # Restart the deployments to make _certain_ the new affinity settings take.
  kubectl rollout restart -n istio-system deployment istiod
  kubectl rollout restart -n faces deployment waypoint

  kubectl rollout status -n istio-system deployment istiod
  kubectl rollout status -n faces deployment waypoint
fi
