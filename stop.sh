#!/bin/bash

# ProjectsManagerWebV2Production Stop Script
# Backwards compatibility — delegates to park.sh

exec "$(dirname "$0")/park.sh" "$@"
