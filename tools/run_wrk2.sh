#!/bin/sh

OUTDIR="$1"
RPS="$2"
SEQ="$3"

if [ -z "$OUTDIR" -o -z "$RPS" -o -z "$SEQ" ]; then
    echo "Usage: $0 <outdir> <rps> <seq>" >&2
    exit 1
fi

echo "Waiting for metrics.py..."
pid=$(cat metrics-pid.txt)

while true; do
    sleep 2
    new_pid=$(cat metrics-pid.txt)

    if [ "$new_pid" != "$pid" ]; then
        pid=$new_pid
        break
    fi
done

podrps=$(( $RPS / 3 ))

echo "Starting $OUTDIR $RPS-$SEQ... (metrics PID $pid, per-pod RPS $podrps)"

kubectl delete -n faces jobs wrk2

sed -e "s/%RPS%/$podrps/" < wrk2.yaml.tpl | kubectl apply -n faces -f -

left=10

while [ $left -gt 0 ]; do
    echo "Waiting for wrk2 to start... ($left)"
    sleep 10
    left=$((left - 1))

    ready=$(kubectl get -n faces jobs wrk2 -o jsonpath='{ .status.ready }')
    if [ "$ready" == "3" ]; then
        break
    fi
done

if [ $left -eq 0 ]; then
    echo "wrk2 did not start"
    exit 1
fi

left=7

while [ $left -gt 0 ]; do
    echo "Waiting for wrk2 to finish... ($left)"
    sleep 60
    left=$((left - 1))

    ready=$(kubectl get -n faces jobs wrk2 -o jsonpath='{ .status.succeeded }')
    if [ "$ready" == "3" ]; then
        break
    fi
done

i=1
for pod in $(kubectl get pods -n faces -l batch.kubernetes.io/job-name=wrk2 \
                              -o jsonpath='{ .items.*.metadata.name }'); do
    kubectl logs -n faces $pod > $OUTDIR/$RPS-$SEQ-$pod.log
done

kubectl delete -n faces jobs wrk2

sleep 30

echo "Collecting metrics..."
kill $pid
mv OUT.csv $OUTDIR/$RPS-$SEQ-metrics.csv
