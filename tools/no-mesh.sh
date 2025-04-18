#!/bin/bash

root=$(dirname $0)
. "$root/check-env.sh"

set -e
set -o pipefail

export KUBECONFIG=$HOME/.kube/${MT_CLUSTER}.yaml

echo "Installing Gateway API"
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.1.1/experimental-install.yaml

kubectl create namespace faces
kubectl annotate namespace faces \
   linkerd.io/inject=enabled \
   config.alpha.linkerd.io/proxy-enable-native-sidecar=true
