#!/bin/bash

CLUSTER_NAME="$1"

if [ -z "$CLUSTER_NAME" ]; then
  echo "Usage: $(basename $0) <cluster-name>" >&2
  exit 1
fi

if [ -z "$GKE_PROJECT" -o -z "$GKE_ZONE" ]; then
  echo "Set GKE_PROJECT to your GKE project ID; set GKE_ZONE to your GKE zone" >&2
  exit 1
fi

export KUBECONFIG=$HOME/.kube/${CLUSTER_NAME}.yaml

gcloud beta container clusters delete "$CLUSTER_NAME" \
    --project "$GKE_PROJECT" \
    --zone "$GKE_ZONE"
