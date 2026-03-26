#!/bin/bash
#
# Create an internal VPN client configuration through backend CLI.
# Usage: ./create-client.sh <client_name> [--reprovision] [--access-label <label>]
#

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BACKEND_CONTAINER="${BACKEND_CONTAINER:-krotvpn-backend}"
CONFIG_DIR="${CONFIG_DIR:-/etc/amnezia/amneziawg/clients}"
ACCESS_LABEL="${ACCESS_LABEL:-internal-unlimited}"
CLI_ARGS=()

usage() {
    echo "Usage: $0 <client_name> [--reprovision] [--access-label <label>]"
    echo "Example: $0 family_phone"
    echo "Example: $0 family_phone --reprovision --access-label family"
}

if [ $# -lt 1 ]; then
    usage
    exit 1
fi

CLIENT_NAME=""

while [ $# -gt 0 ]; do
    case "$1" in
        --reprovision)
            CLI_ARGS+=("--reprovision")
            shift
            ;;
        --access-label)
            if [ $# -lt 2 ]; then
                echo "Missing value for --access-label"
                exit 1
            fi
            ACCESS_LABEL="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            if [ -n "$CLIENT_NAME" ]; then
                echo "Unexpected argument: $1"
                usage
                exit 1
            fi
            CLIENT_NAME="$1"
            shift
            ;;
    esac
done

if [ -z "$CLIENT_NAME" ]; then
    usage
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "docker command not found"
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$BACKEND_CONTAINER"; then
    echo "Backend container is not running: $BACKEND_CONTAINER"
    exit 1
fi

mkdir -p "$CONFIG_DIR"

OUTPUT_PATH="${CONFIG_DIR}/${CLIENT_NAME}.conf"
PNG_PATH="${CONFIG_DIR}/${CLIENT_NAME}.png"

echo -e "${YELLOW}Issuing internal client config via backend CLI for ${CLIENT_NAME}...${NC}"
docker exec "$BACKEND_CONTAINER" python -m app.cli create-internal-client \
    --identity "$CLIENT_NAME" \
    --display-name "$CLIENT_NAME" \
    --access-label "$ACCESS_LABEL" \
    --output "$OUTPUT_PATH" \
    "${CLI_ARGS[@]}"

if [ ! -f "$OUTPUT_PATH" ]; then
    echo "Config file was not created: $OUTPUT_PATH"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Client ${CLIENT_NAME} created successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Config file: ${OUTPUT_PATH}${NC}"
echo -e "${BLUE}Access label: ${ACCESS_LABEL}${NC}"
echo ""

if command -v qrencode >/dev/null 2>&1; then
    echo -e "${YELLOW}QR Code (scan with AmneziaWG app):${NC}"
    echo ""
    qrencode -t ansiutf8 < "$OUTPUT_PATH"
    echo ""
    qrencode -o "$PNG_PATH" < "$OUTPUT_PATH"
    echo -e "${GREEN}QR code saved to: ${PNG_PATH}${NC}"
else
    echo -e "${YELLOW}qrencode not found; QR output skipped.${NC}"
fi
