#!/bin/bash

root=$(dirname $0)
. "$root/check-env.sh"

set -e -u
set -o pipefail

bash ${root}/${MT_PLATFORM}-delete.sh "$@"
