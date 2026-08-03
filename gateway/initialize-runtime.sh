#!/bin/sh
set -eu

runtime_dir=/var/lib/kubera-maintenance
mkdir -p "$runtime_dir"

if [ ! -L "$runtime_dir/active.conf" ]; then
    ln -s /etc/nginx/modes/app.conf "$runtime_dir/active.conf"
fi

if [ ! -f "$runtime_dir/state.json" ]; then
    printf '{"mode":"active"}\n' > "$runtime_dir/state.json"
fi
