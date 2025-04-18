PATH=$HOME/istio-1.25.0/bin:$PATH

kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.1/standard-install.yaml

EXTRA_ARGS="--set values.pilot.autoscaleMin=3"

if [ -n "$1" ]; then
   EXTRA_ARGS="$EXTRA_ARGS --set values.global.platform=$1"

  if [ -n "$2" ]; then
    EXTRA_ARGS="$EXTRA_ARGS --set values.global.waypoint.resources.limits.cpu=$2"

    if [ -n "$3" ]; then
      EXTRA_ARGS="$EXTRA_ARGS --set values.global.waypoint.resources.limits.memory=$3"
    fi
  fi
fi

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

echo istioctl install --set profile=ambient $EXTRA_ARGS -y
istioctl install --set profile=ambient $EXTRA_ARGS -y

kubectl create namespace faces
kubectl annotate namespace faces \
   linkerd.io/inject=enabled \
   config.alpha.linkerd.io/proxy-enable-native-sidecar=true

kubectl label namespace faces istio.io/dataplane-mode=ambient
istioctl waypoint apply --for all -n faces --enroll-namespace --overwrite

kubectl patch deployment -n istio-system istiod --type='json' -p='[{"op": "add", "path": "/spec/template/spec/affinity", "value": {"podAntiAffinity": {"preferredDuringSchedulingIgnoredDuringExecution": [{"weight": 100, "podAffinityTerm": {"labelSelector": {"matchExpressions": [{"key": "app.kubernetes.io/name", "operator": "In", "values": ["istiod"]}]}, "topologyKey": "kubernetes.io/hostname"}}]}}}]'
kubectl patch deployment -n faces waypoint --type='json' -p='[{"op": "add", "path": "/spec/template/spec/affinity", "value": {"podAntiAffinity": {"preferredDuringSchedulingIgnoredDuringExecution": [{"weight": 100, "podAffinityTerm": {"labelSelector": {"matchExpressions": [{"key": "gateway.networking.k8s.io/gateway-name", "operator": "In", "values": ["waypoint"]}]}, "topologyKey": "kubernetes.io/hostname"}}]}}}]'

kubectl scale -n istio-system deployment istiod --replicas=3
kubectl scale -n faces deployment waypoint --replicas=3

bash init-faces.sh
