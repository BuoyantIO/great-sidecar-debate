#!/bin/bash

. $(dirname $0)/check-env.sh

set -e -u
set -o pipefail

extra_args=""

if [ $MT_NODES -gt 1 ]; then
  extra_args="$extra_args --set backend.antiaffinity=true"
  extra_args="$extra_args --set face.antiaffinity=true"
  extra_args="$extra_args --set gui.antiaffinity=true"

  replicas=$MT_NODES

  if [ $MT_NODES -gt 3 ]; then
    replicas=3
    extra_args="$extra_args --set backend.affinity.key=buoyant.io/meshtest-role"
    extra_args="$extra_args --set backend.affinity.value=app"
    extra_args="$extra_args --set face.affinity.key=buoyant.io/meshtest-role"
    extra_args="$extra_args --set face.affinity.value=app"
    extra_args="$extra_args --set gui.affinity.key=buoyant.io/meshtest-role"
    extra_args="$extra_args --set gui.affinity.value=app"
  fi

  extra_args="$extra_args --set defaultReplicas=$replicas"
fi

helm install faces -n faces \
   oci://ghcr.io/buoyantio/faces-chart --version 2.0.0-rc.7 \
   -f $(dirname $0)/faces-values.yaml $extra_args \
   --wait
