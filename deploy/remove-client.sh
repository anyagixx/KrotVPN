#!/bin/bash
#
# Remove VPN client
# Usage: ./remove-client.sh <client_name>
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

CONFIG_DIR="/etc/amnezia/amneziawg"
CLIENT_DIR="${CONFIG_DIR}/clients"

if [ -z "$1" ]; then
    echo "Usage: $0 <client_name>"
    echo "Example: $0 user_ivan"
    exit 1
fi

CLIENT_NAME="$1"
CLIENT_CONF="${CLIENT_DIR}/${CLIENT_NAME}.conf"
CLIENT_PUB="${CLIENT_DIR}/${CLIENT_NAME}.pub"

if [ ! -f "$CLIENT_CONF" ]; then
    echo -e "${RED}Client ${CLIENT_NAME} not found!${NC}"
    exit 1
fi

# Get public key
PUBLIC_KEY=$(cat "$CLIENT_PUB")

# Remove from running interface
echo -e "${YELLOW}Removing peer from interface...${NC}"
awg set awg0 peer "$PUBLIC_KEY" remove

# Remove from config file
echo -e "${YELLOW}Removing from config file...${NC}"
sed -i "/# Client: ${CLIENT_NAME}/,+3d" ${CONFIG_DIR}/awg0.conf

# Remove client files
echo -e "${YELLOW}Removing client files...${NC}"
rm -f "${CLIENT_DIR}/${CLIENT_NAME}.conf"
rm -f "${CLIENT_DIR}/${CLIENT_NAME}.pub"
rm -f "${CLIENT_DIR}/${CLIENT_NAME}.key"
rm -f "${CLIENT_DIR}/${CLIENT_NAME}.ip"
rm -f "${CLIENT_DIR}/${CLIENT_NAME}.png"

echo -e "${GREEN}Client ${CLIENT_NAME} removed successfully!${NC}"
