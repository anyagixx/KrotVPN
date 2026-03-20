#!/bin/bash
#
# KrotVPN Quick Start Script
# Run this locally to deploy to both servers
#
# Usage: ./quick-start.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Server IPs
RU_IP="212.113.121.164"
DE_IP="95.216.149.110"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}          KrotVPN Quick Start                   ${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Check SSH access
echo -e "${YELLOW}Checking SSH access to servers...${NC}"

echo -e "${BLUE}Testing DE server (${DE_IP})...${NC}"
if ssh -o ConnectTimeout=5 -o BatchMode=yes root@${DE_IP} "echo ok" 2>/dev/null; then
    echo -e "${GREEN}✓ DE server accessible${NC}"
else
    echo -e "${RED}✗ Cannot connect to DE server${NC}"
    echo -e "${YELLOW}Make sure you can SSH as root without password:${NC}"
    echo -e "  ssh-copy-id root@${DE_IP}"
    exit 1
fi

echo -e "${BLUE}Testing RU server (${RU_IP})...${NC}"
if ssh -o ConnectTimeout=5 -o BatchMode=yes root@${RU_IP} "echo ok" 2>/dev/null; then
    echo -e "${GREEN}✓ RU server accessible${NC}"
else
    echo -e "${RED}✗ Cannot connect to RU server${NC}"
    echo -e "${YELLOW}Make sure you can SSH as root without password:${NC}"
    echo -e "  ssh-copy-id root@${RU_IP}"
    exit 1
fi

echo ""
echo -e "${YELLOW}================================================${NC}"
echo -e "${YELLOW}Step 1: Deploying to DE server (Exit Node)${NC}"
echo -e "${YELLOW}================================================${NC}"
echo ""

# Copy and run DE deployment script
scp deploy/deploy-de-server.sh root@${DE_IP}:/tmp/
ssh root@${DE_IP} "bash /tmp/deploy-de-server.sh"

echo ""
echo -e "${YELLOW}================================================${NC}"
echo -e "${YELLOW}Step 2: Getting DE public key${NC}"
echo -e "${YELLOW}================================================${NC}"
echo ""

DE_PUBLIC_KEY=$(ssh root@${DE_IP} "cat /etc/amnezia/amneziawg/de_public.key")
echo -e "${GREEN}DE Public Key: ${DE_PUBLIC_KEY}${NC}"

echo ""
echo -e "${YELLOW}================================================${NC}"
echo -e "${YELLOW}Step 3: Deploying to RU server (Entry Node)${NC}"
echo -e "${YELLOW}================================================${NC}"
echo ""

# Copy and run RU deployment script
scp deploy/deploy-ru-server.sh root@${RU_IP}:/tmp/
ssh root@${RU_IP} "DE_PUBLIC_KEY='${DE_PUBLIC_KEY}' bash /tmp/deploy-ru-server.sh"

echo ""
echo -e "${YELLOW}================================================${NC}"
echo -e "${YELLOW}Step 4: Getting RU client public key${NC}"
echo -e "${YELLOW}================================================${NC}"
echo ""

RU_CLIENT_PUBLIC_KEY=$(ssh root@${RU_IP} "cat /etc/amnezia/amneziawg/ru_client_public.key")
echo -e "${GREEN}RU Client Public Key: ${RU_CLIENT_PUBLIC_KEY}${NC}"

echo ""
echo -e "${YELLOW}================================================${NC}"
echo -e "${YELLOW}Step 5: Adding RU peer to DE server${NC}"
echo -e "${YELLOW}================================================${NC}"
echo ""

# Add RU peer to DE server
ssh root@${DE_IP} << EOF
# Add RU peer to DE config
if ! grep -q "${RU_CLIENT_PUBLIC_KEY}" /etc/amnezia/amneziawg/awg0.conf; then
    echo "" >> /etc/amnezia/amneziawg/awg0.conf
    echo "# RU Server" >> /etc/amnezia/amneziawg/awg0.conf
    echo "[Peer]" >> /etc/amnezia/amneziawg/awg0.conf
    echo "PublicKey = ${RU_CLIENT_PUBLIC_KEY}" >> /etc/amnezia/amneziawg/awg0.conf
    echo "AllowedIPs = 10.200.0.2/32" >> /etc/amnezia/amneziawg/awg0.conf
    
    # Restart AmneziaWG
    awg-quick down awg0 2>/dev/null || true
    awg-quick up awg0
fi
EOF

echo ""
echo -e "${YELLOW}================================================${NC}"
echo -e "${YELLOW}Step 6: Testing tunnel${NC}"
echo -e "${YELLOW}================================================${NC}"
echo ""

# Test tunnel from RU to DE
ssh root@${RU_IP} << 'EOF'
# Start AmneziaWG if not running
awg-quick up awg0 2>/dev/null || true
awg-quick up awg-client 2>/dev/null || true

# Setup routing
/usr/local/bin/setup_routing.sh

# Test ping
echo "Testing tunnel to DE server..."
if ping -c 3 10.200.0.1; then
    echo "✓ Tunnel working!"
else
    echo "✗ Tunnel not working - check configuration"
fi
EOF

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}          DEPLOYMENT COMPLETE!                  ${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "${BLUE}Access your VPN service:${NC}"
echo -e "  Frontend:    http://${RU_IP}"
echo -e "  Admin Panel: http://${RU_IP}:8080"
echo -e "  Backend API: http://${RU_IP}:8000/docs"
echo ""
echo -e "${BLUE}To create a VPN client:${NC}"
echo -e "  ssh root@${RU_IP} '/opt/KrotVPN/deploy/create-client.sh test_user'"
echo ""
