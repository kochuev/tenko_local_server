#!/bin/sh
set -eu
cd "$(dirname "$0")"
docker build --tag "${IMAGE_NAME:-tenko-local:latest}" .
