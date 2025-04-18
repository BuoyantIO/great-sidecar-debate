#!/bin/bash

root=$(dirname $0)
. "$root/check-env.sh"

set -e
set -o pipefail

export KUBECONFIG=$HOME/.kube/${MT_CLUSTER}.yaml

if ! command -v linkerd &> /dev/null; then
  echo "linkerd could not be found. Please ensure it is installed and added to your PATH."
  exit 1
fi

EXTRA_ARGS="$@"

# EXTRA_ARGS that you might play with: probably none, honestly.

if [ -z "$MT_SERVICECIDR" ]; then
  # What kind of cluster is this?
  node=$(kubectl get node -o jsonpath='{ .items[0].metadata.name }')

  if [ $(echo $node | egrep -c '^k3d-') -gt 0 ]; then
    echo "Detected k3d cluster, assuming MT_SERVICECIDR is 10.43.0.0/16"
    MT_SERVICECIDR=10.43.0.0/16
  else
    if [ -z "$GKE_PROJECT" -o -z "$GKE_ZONE" ]; then
      echo "Set GKE_PROJECT to your GKE project ID; set GKE_ZONE to your GKE zone" >&2
      echo "(Alternately, set MT_SERVICECIDR.)" >&2
      exit 1
    fi

    ctx=$(kubectl config current-context)

    if [ -z "$ctx" ]; then
      echo "No Service CIDR specified and no current context" >&2
      exit 1
    fi

    if [ $(echo "$ctx" | grep -c _) -gt 0 ]; then
      echo "Current context needs to be just the cluster name, not include the region etc." >&2
      exit 1
    fi

    MT_SERVICECIDR=$(gcloud container clusters describe $ctx \
                        --project "$GKE_PROJECT" \
                        --zone "$GKE_ZONE" \
                        --format 'value(servicesIpv4Cidr)')
  fi
fi

if [ -z "$MT_SERVICECIDR" ]; then
  echo "Could not determine Service CIDR; set MT_SERVICECIDR and try again" >&2
  exit 1
fi

set -u

PodCIDRs=$(kubectl get node -o json \
               | jq -r '.items[].spec.podCIDR' \
               | tr '\012' ',' | sed -e 's/,$//')

if [ -z "$PodCIDRs" ]; then
  echo "No pod CIDRs found" >&2
  exit 1
fi

ClusterNetworks=$(echo "$MT_SERVICECIDR,$PodCIDRs" | sed -e 's/,/\\,/g')

echo "ClusterNetworks $ClusterNetworks"
# exit 0

echo "Installing Gateway API"
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.1.1/experimental-install.yaml

extra_args=""

if [ "$MT_PROFILE" == "ha" ]; then
  extra_args="--ha"
fi

set -x

linkerd install --crds $extra_args --set installGatewayAPI=false | kubectl apply -f -
linkerd install $extra_args --set clusterNetworks="$ClusterNetworks" | kubectl apply -f -
linkerd check

kubectl create namespace faces
kubectl annotate namespace faces \
   linkerd.io/inject=enabled \
   config.alpha.linkerd.io/proxy-enable-native-sidecar=true
