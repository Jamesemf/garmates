#!/usr/bin/env sh
# Start the dashboard from the conda env (macOS/Linux counterpart of start.cmd).
# Extra arguments pass through, e.g.  ./start.sh --port 9000
set -e
cd "$(dirname "$0")"

if [ ! -f frontend/dist/index.html ]; then
    echo "Building the web app first - this takes a minute the first time..."
    (cd frontend && conda run -n garmates --no-capture-output npm install \
        && conda run -n garmates --no-capture-output npm run build)
fi

exec conda run -n garmates --no-capture-output garmates serve "$@"
