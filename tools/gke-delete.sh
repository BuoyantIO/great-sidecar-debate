#!/bin/bash

root=$(dirname $0)
. "$root/check-env.sh"

set -e -u
set -o pipefail

export KUBECONFIG=$HOME/.kube/${MT_CLUSTER}.yaml

if [ -z "$GKE_PROJECT" -o -z "$GKE_ZONE" ]; then
  echo "Set GKE_PROJECT to your GKE project ID; set GKE_ZONE to your GKE zone" >&2
  exit 1
fi

yes | gcloud beta container clusters delete "$MT_CLUSTER" \
    --project "$GKE_PROJECT" \
    --zone "$GKE_ZONE"
