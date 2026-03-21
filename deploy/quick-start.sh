#!/bin/bash
#
# KrotVPN Quick Start - One command deployment
# This is a wrapper for deploy-all.sh
#
# Usage: ./deploy/quick-start.sh [RU_IP] [DE_IP]
# Default: RU=212.113.121.164 DE=95.216.149.110
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec "${SCRIPT_DIR}/deploy-all.sh" "$@"
