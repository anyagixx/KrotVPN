#!/bin/bash
#
# Create VPN client configuration
# Usage: ./create-client.sh <client_name>
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
RU_IP="212.113.121.164"
VPN_PORT="51821"
VPN_SUBNET="10.10.0.0/24"
CONFIG_DIR="/etc/amnezia/amneziawg"

if [ -z "$1" ]; then
    echo "Usage: $0 <client_name>"
    echo "Example: $0 user_ivan"
    exit 1
fi

CLIENT_NAME="$1"
CLIENT_DIR="${CONFIG_DIR}/clients"

# Create clients directory
mkdir -p "$CLIENT_DIR"

# Generate keys
echo -e "${YELLOW}Generating keys for ${CLIENT_NAME}...${NC}"
PRIVATE_KEY=$(awg genkey)
PUBLIC_KEY=$(echo "$PRIVATE_KEY" | awg pubkey)

# Get server public key
SERVER_PUBLIC_KEY=$(cat ${CONFIG_DIR}/ru_server_public.key)

# Find next available IP
USED_IPS=$(awg show awg0 allowed-ips 2>/dev/null | grep -oP '\d+\.\d+\.\d+\.\d+' | sort -u)
CLIENT_IP="10.10.0.2"

for i in $(seq 2 254); do
    IP="10.10.0.${i}"
    if ! echo "$USED_IPS" | grep -q "^${IP}$"; then
        CLIENT_IP="$IP"
        break
    fi
done

echo -e "${GREEN}Assigned IP: ${CLIENT_IP}${NC}"

# Create client config
cat > "${CLIENT_DIR}/${CLIENT_NAME}.conf" << EOF
[Interface]
PrivateKey = ${PRIVATE_KEY}
Address = ${CLIENT_IP}/32
DNS = 8.8.8.8, 1.1.1.1
MTU = 1360
Jc = 120
Jmin = 50
Jmax = 1000
S1 = 111
S2 = 222
H1 = 1
H2 = 2
H3 = 3
H4 = 4

[Peer]
PublicKey = ${SERVER_PUBLIC_KEY}
Endpoint = ${RU_IP}:${VPN_PORT}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF

# Save keys for reference
echo "$PUBLIC_KEY" > "${CLIENT_DIR}/${CLIENT_NAME}.pub"
echo "$PRIVATE_KEY" > "${CLIENT_DIR}/${CLIENT_NAME}.key"
echo "$CLIENT_IP" > "${CLIENT_DIR}/${CLIENT_NAME}.ip"

# Add peer to server
echo -e "${YELLOW}Adding peer to server...${NC}"
awg set awg0 peer "$PUBLIC_KEY" allowed-ips "${CLIENT_IP}/32"

# Also add to config file for persistence
echo "" >> ${CONFIG_DIR}/awg0.conf
echo "# Client: ${CLIENT_NAME}" >> ${CONFIG_DIR}/awg0.conf
echo "[Peer]" >> ${CONFIG_DIR}/awg0.conf
echo "PublicKey = ${PUBLIC_KEY}" >> ${CONFIG_DIR}/awg0.conf
echo "AllowedIPs = ${CLIENT_IP}/32" >> ${CONFIG_DIR}/awg0.conf

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Client ${CLIENT_NAME} created successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Config file: ${CLIENT_DIR}/${CLIENT_NAME}.conf${NC}"
echo -e "${BLUE}Public Key:  ${PUBLIC_KEY}${NC}"
echo -e "${BLUE}IP Address:  ${CLIENT_IP}${NC}"
echo ""

# Generate QR code
echo -e "${YELLOW}QR Code (scan with AmneziaWG app):${NC}"
echo ""
qrencode -t ansiutf8 < "${CLIENT_DIR}/${CLIENT_NAME}.conf"
echo ""

# Also save QR as PNG
qrencode -o "${CLIENT_DIR}/${CLIENT_NAME}.png" < "${CLIENT_DIR}/${CLIENT_NAME}.conf"
echo -e "${GREEN}QR code saved to: ${CLIENT_DIR}/${CLIENT_NAME}.png${NC}"
