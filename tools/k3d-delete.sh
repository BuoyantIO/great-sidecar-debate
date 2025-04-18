#/bin/bash

. $(dirname $0)/check-env.sh

set -e -u
set -o pipefail

export KUBECONFIG=$HOME/.kube/${MT_CLUSTER}.yaml

k3d cluster delete $MT_CLUSTER
