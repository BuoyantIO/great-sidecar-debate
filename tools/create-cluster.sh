#!/bin/bash

root=$(dirname $0)
. "$root/check-env.sh"

set -e -u
set -o pipefail

$SHELL ${root}/${MT_PLATFORM}-create.sh "$@"
