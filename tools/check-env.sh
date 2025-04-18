#!/bin/sh

if [ -z "$MT_CLUSTER" ]; then
    echo "MT_CLUSTER is not set. Please set it to the cluster name."
    exit 1
fi

if [ -z "$MT_NODES" ]; then
    echo "MT_NODES is not set. Please set it to the number of nodes desired."
    exit 1
fi

if [ $MT_NODES -lt 1 ]; then
    echo "MT_NODES must be at least 1."
    exit 1
fi

if [ \( "$MT_PROFILE" != "ha" \) -a \( "$MT_PROFILE" != "dev" \) ]; then
    echo "MT_PROFILE must be either 'ha' or 'dev'."
    exit 1
fi

if [ -z "$MT_PLATFORM" ]; then
    echo "MT_PLATFORM is not set. Please set it to the platform you are using."
    exit 1
fi
