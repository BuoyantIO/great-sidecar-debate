#!/bin/bash

root=$(dirname $0)
. "$root/check-env.sh"

set -e -u
set -o pipefail

export KUBECONFIG=$HOME/.kube/${MT_CLUSTER}.yaml

agents=""

# Create a k3d cluster with the specified name and number of nodes
k3d cluster create "$MT_CLUSTER" \
    --k3s-arg '--disable=traefik@server:*' \
    --agents $(( $MT_NODES - 1 )) \
    --no-lb

if [ $MT_NODES -gt 1 ]; then
  # Label the k3d agents for the Faces app.
  i=0

  while [ $i -lt $(( $MT_NODES -1 )) ]; do
    nodename="k3d-${MT_CLUSTER}-agent-$i"
    kubectl label node $nodename buoyant.io/meshtest-role=app
    i=$(( $i + 1 ))
  done

  # Label the k3d server for the load generator.
  kubectl label node k3d-${MT_CLUSTER}-server-0 \
    buoyant.io/meshtest-role=load
fi

if [ -f "$root/IMAGES" ]; then
  k3d image load --cluster $MT_CLUSTER $(cat "$root/IMAGES")
fi