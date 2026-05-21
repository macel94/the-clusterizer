#!/usr/bin/env bash

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

sudo apt-get update
sudo apt-get install -y ripgrep jq podman podman-compose uidmap slirp4netns fuse-overlayfs
sudo install -m 0755 .devcontainer/bin/podman /usr/local/bin/podman
sudo install -m 0755 .devcontainer/bin/podman-compose /usr/local/bin/podman-compose

cd /workspaces/the-clusterizer/backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-test.txt

cd /workspaces/the-clusterizer/frontend
npm install
