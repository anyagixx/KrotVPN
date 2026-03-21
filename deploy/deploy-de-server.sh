#!/bin/bash
#
# KrotVPN DE Server (Exit Node) Deployment Script
# Run this script on the German server
#
# Usage: 
#   bash deploy-de-server.sh                           # Interactive mode
#   RU_CLIENT_PUBLIC_KEY=xxx bash deploy-de-server.sh  # Non-interactive mode
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
RU_IP="${RU_IP:-212.113.121.164}"
DE_IP="${DE_IP:-95.216.149.110}"
VPN_PORT="${VPN_PORT:-51821}"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   KrotVPN DE Server (Exit Node) Deployment     ${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root${NC}"
    exit 1
fi

# Get RU Client Public Key
if [ -z "$RU_CLIENT_PUBLIC_KEY" ]; then
    echo -e "${YELLOW}Enter RU Server Public Key:${NC}"
    echo -e "${YELLOW}(Get from RU server: cat /etc/amnezia/amneziawg/ru_client_public.key)${NC}"
    read -p "> " RU_CLIENT_PUBLIC_KEY
fi

if [ -z "$RU_CLIENT_PUBLIC_KEY" ]; then
    echo -e "${RED}ERROR: RU Client Public Key is required!${NC}"
    exit 1
fi

# Step 1: Update system
echo -e "${YELLOW}[1/6] Updating system...${NC}"
apt update -qq && apt upgrade -y -qq

# Step 2: Install dependencies
echo -e "${YELLOW}[2/6] Installing dependencies...${NC}"
apt install -y -qq software-properties-common python3-launchpadlib gnupg2 \
    linux-headers-$(uname -r) curl wget git ipset iptables ufw qrencode

# Step 3: Install AmneziaWG
echo -e "${YELLOW}[3/6] Installing AmneziaWG...${NC}"
if ! command -v awg &> /dev/null; then
    add-apt-repository ppa:amnezia/ppa -y
    apt update -qq
    apt install -y -qq amneziawg amneziawg-tools
fi

# Step 4: Enable IP forwarding
echo -e "${YELLOW}[4/6] Enabling IP forwarding...${NC}"
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-krotvpn.conf
sysctl -p /etc/sysctl.d/99-krotvpn.conf > /dev/null

# Step 5: Generate keys
echo -e "${YELLOW}[5/6] Generating AmneziaWG keys...${NC}"
mkdir -p /etc/amnezia/amneziawg
cd /etc/amnezia/amneziawg

awg genkey | tee de_private.key | awg pubkey > de_public.key

DE_PRIVATE_KEY=$(cat de_private.key)
DE_PUBLIC_KEY=$(cat de_public.key)

echo -e "${GREEN}DE Server Keys Generated:${NC}"
echo -e "  Private: ${DE_PRIVATE_KEY}"
echo -e "  Public:  ${DE_PUBLIC_KEY}"

# Step 6: Create configuration
echo -e "${YELLOW}[6/6] Creating configuration...${NC}"

cat > /etc/amnezia/amneziawg/awg0.conf << EOF
[Interface]
PrivateKey = ${DE_PRIVATE_KEY}
Address = 10.200.0.1/24
ListenPort = ${VPN_PORT}
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
PublicKey = ${RU_CLIENT_PUBLIC_KEY}
AllowedIPs = 10.200.0.2/32
EOF

chmod 600 /etc/amnezia/amneziawg/awg0.conf

# Configure firewall
echo -e "${YELLOW}Configuring firewall...${NC}"
ufw --force reset > /dev/null
ufw allow 22/tcp > /dev/null
ufw allow ${VPN_PORT}/udp > /dev/null
sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw

# Add NAT rules
cat > /etc/ufw/before.rules << 'NAT'
#
# rules.before
#
*filter
:ufw-before-input - [0:0]
:ufw-before-output - [0:0]
:ufw-before-forward - [0:0]
:ufw-not-local - [0:0]

-A ufw-before-input -i lo -j ACCEPT
-A ufw-before-output -o lo -j ACCEPT
-A ufw-before-input -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A ufw-before-output -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A ufw-before-forward -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A ufw-before-input -m conntrack --ctstate INVALID -j ufw-logging-deny
-A ufw-before-input -m conntrack --ctstate INVALID -j DROP
-A ufw-before-input -p icmp --icmp-type destination-unreachable -j ACCEPT
-A ufw-before-input -p icmp --icmp-type time-exceeded -j ACCEPT
-A ufw-before-input -p icmp --icmp-type parameter-problem -j ACCEPT
-A ufw-before-input -p icmp --icmp-type echo-request -j ACCEPT
-A ufw-before-output -p icmp --icmp-type destination-unreachable -j ACCEPT
-A ufw-before-output -p icmp --icmp-type time-exceeded -j ACCEPT
-A ufw-before-output -p icmp --icmp-type parameter-problem -j ACCEPT
-A ufw-before-output -p icmp --icmp-type echo-request -j ACCEPT
-A ufw-before-forward -p icmp --icmp-type destination-unreachable -j ACCEPT
-A ufw-before-forward -p icmp --icmp-type time-exceeded -j ACCEPT
-A ufw-before-forward -p icmp --icmp-type parameter-problem -j ACCEPT
-A ufw-before-forward -p icmp --icmp-type echo-request -j ACCEPT
-A ufw-before-input -p udp --sport 67 --dport 68 -j ACCEPT
-A ufw-before-input -j ufw-not-local
-A ufw-not-local -m addrtype --dst-type LOCAL -j RETURN
-A ufw-not-local -m addrtype --dst-type MULTICAST -j RETURN
-A ufw-not-local -m addrtype --dst-type BROADCAST -j RETURN
-A ufw-not-local -j DROP
COMMIT

*nat
:POSTROUTING ACCEPT [0:0]
-A POSTROUTING -s 10.200.0.0/24 -o eth0 -j MASQUERADE
COMMIT
NAT

ufw --force enable > /dev/null

# Start AmneziaWG
echo -e "${YELLOW}Starting AmneziaWG...${NC}"
awg-quick down awg0 2>/dev/null || true
awg-quick up awg0

# Verify
echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}   DE SERVER SETUP COMPLETE!                    ${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "Server IP: ${DE_IP}"
echo -e "VPN Port: ${VPN_PORT}/udp"
echo ""
echo -e "${YELLOW}IMPORTANT - Save this key for RU server setup:${NC}"
echo -e "  DE Public Key: ${DE_PUBLIC_KEY}"
echo ""
echo -e "${BLUE}AmneziaWG Status:${NC}"
awg show
