#!/bin/bash
#
# KrotVPN DE Server (Exit Node) Deployment Script
# Run this script on the German server
#
# Usage: bash deploy-de-server.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
RU_IP="212.113.121.164"
DE_IP="95.216.149.110"
VPN_PORT="51821"
VPN_SUBNET="10.200.0.0/24"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   KrotVPN DE Server (Exit Node) Deployment     ${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root${NC}"
    exit 1
fi

# Step 1: Update system
echo -e "${YELLOW}[1/7] Updating system...${NC}"
apt update && apt upgrade -y

# Step 2: Install dependencies
echo -e "${YELLOW}[2/7] Installing dependencies...${NC}"
apt install -y software-properties-common python3-launchpadlib gnupg2 \
    linux-headers-$(uname -r) curl wget git ipset iptables ufw qrencode

# Step 3: Install AmneziaWG
echo -e "${YELLOW}[3/7] Installing AmneziaWG...${NC}"
if ! command -v awg &> /dev/null; then
    add-apt-repository ppa:amnezia/ppa -y
    apt update
    apt install -y amneziawg amneziawg-tools
fi

# Step 4: Enable IP forwarding
echo -e "${YELLOW}[4/7] Enabling IP forwarding...${NC}"
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-krotvpn.conf
sysctl -p /etc/sysctl.d/99-krotvpn.conf

# Step 5: Generate keys
echo -e "${YELLOW}[5/7] Generating AmneziaWG keys...${NC}"
mkdir -p /etc/amnezia/amneziawg
cd /etc/amnezia/amneziawg

# Generate server keys
awg genkey | tee de_private.key | awg pubkey > de_public.key

DE_PRIVATE_KEY=$(cat de_private.key)
DE_PUBLIC_KEY=$(cat de_public.key)

echo -e "${GREEN}DE Server Keys Generated:${NC}"
echo -e "  Private: ${DE_PRIVATE_KEY}"
echo -e "  Public:  ${DE_PUBLIC_KEY}"

# Step 6: Create AmneziaWG configuration
echo -e "${YELLOW}[6/7] Creating AmneziaWG configuration...${NC}"

# We need RU public key - ask user or generate placeholder
echo ""
echo -e "${YELLOW}You need to run deploy-ru-server.sh first on the RU server!${NC}"
echo -e "${YELLOW}Enter RU Server Public Key (from RU server /etc/amnezia/amneziawg/ru_client_public.key):${NC}"
read -p "> " RU_CLIENT_PUBLIC_KEY

if [ -z "$RU_CLIENT_PUBLIC_KEY" ]; then
    echo -e "${RED}RU Client Public Key is required!${NC}"
    echo -e "${YELLOW}Get it from RU server: cat /etc/amnezia/amneziawg/ru_client_public.key${NC}"
    exit 1
fi

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

# Peer: RU Server
[Peer]
PublicKey = ${RU_CLIENT_PUBLIC_KEY}
AllowedIPs = 10.200.0.2/32
EOF

chmod 600 /etc/amnezia/amneziawg/awg0.conf

# Step 7: Configure Firewall
echo -e "${YELLOW}[7/7] Configuring firewall...${NC}"

# Reset UFW
ufw --force reset

# Allow SSH
ufw allow 22/tcp

# Allow AmneziaWG
ufw allow ${VPN_PORT}/udp

# Enable NAT
sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw

# Add NAT rules
cat > /etc/ufw/before.rules << 'NAT'
#
# rules.before
#
# Rules that should be run before the ufw command line added rules. Custom
# rules should be added to one of these chains:
#   ufw-before-input
#   ufw-before-output
#   ufw-before-forward
#

# Don't delete these required lines, otherwise there will be errors
*filter
:ufw-before-input - [0:0]
:ufw-before-output - [0:0]
:ufw-before-forward - [0:0]
:ufw-not-local - [0:0]

# End required lines

# allow all on loopback
-A ufw-before-input -i lo -j ACCEPT
-A ufw-before-output -o lo -j ACCEPT

# quickly process packets for which we already have a connection
-A ufw-before-input -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A ufw-before-output -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
-A ufw-before-forward -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT

# drop INVALID packets (logs these in loglevel medium and higher)
-A ufw-before-input -m conntrack --ctstate INVALID -j ufw-logging-deny
-A ufw-before-input -m conntrack --ctstate INVALID -j DROP

# ok icmp codes for INPUT
-A ufw-before-input -p icmp --icmp-type destination-unreachable -j ACCEPT
-A ufw-before-input -p icmp --icmp-type time-exceeded -j ACCEPT
-A ufw-before-input -p icmp --icmp-type parameter-problem -j ACCEPT
-A ufw-before-input -p icmp --icmp-type echo-request -j ACCEPT

# ok icmp codes for OUTPUT
-A ufw-before-output -p icmp --icmp-type destination-unreachable -j ACCEPT
-A ufw-before-output -p icmp --icmp-type time-exceeded -j ACCEPT
-A ufw-before-output -p icmp --icmp-type parameter-problem -j ACCEPT
-A ufw-before-output -p icmp --icmp-type echo-request -j ACCEPT

# ok icmp codes for FORWARD
-A ufw-before-forward -p icmp --icmp-type destination-unreachable -j ACCEPT
-A ufw-before-forward -p icmp --icmp-type time-exceeded -j ACCEPT
-A ufw-before-forward -p icmp --icmp-type parameter-problem -j ACCEPT
-A ufw-before-forward -p icmp --icmp-type echo-request -j ACCEPT

# allow dhcp client to work
-A ufw-before-input -p udp --sport 67 --dport 68 -j ACCEPT

# ufw-not-local
-A ufw-before-input -j ufw-not-local

# if LOCAL, RETURN
-A ufw-not-local -m addrtype --dst-type LOCAL -j RETURN

# if MULTICAST, RETURN
-A ufw-not-local -m addrtype --dst-type MULTICAST -j RETURN

# if BROADCAST, RETURN
-A ufw-not-local -m addrtype --dst-type BROADCAST -j RETURN

# all other non-local packets are dropped
-A ufw-not-local -j DROP

# allow MULTICAST mDNS for service discovery (be sure the MULTICAST line above
# is uncommented)
#-A ufw-before-input -p udp -d 224.0.0.251 --dport 5353 -j ACCEPT

# allow MULTICAST UPnP for service discovery (be sure the MULTICAST line above
# is uncommented)
#-A ufw-before-input -p udp -d 239.255.255.250 --dport 1900 -j ACCEPT

# don't delete the 'COMMIT' line or these rules won't be processed
COMMIT

# NAT for KrotVPN
*nat
:POSTROUTING ACCEPT [0:0]
# Forward VPN traffic through this server
-A POSTROUTING -s 10.200.0.0/24 -o eth0 -j MASQUERADE
COMMIT
NAT

# Enable UFW
ufw --force enable

# Create systemd service for AmneziaWG
cat > /etc/systemd/system/awg-quick@awg0.service << 'SERVICE'
[Unit]
Description=AmneziaWG VPN Tunnel (awg0)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/awg-quick up awg0
ExecStop=/usr/bin/awg-quick down awg0

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable awg-quick@awg0

# Start AmneziaWG
echo -e "${YELLOW}Starting AmneziaWG...${NC}"
awg-quick up awg0 2>/dev/null || systemctl start awg-quick@awg0

# Verify
echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}   DE SERVER SETUP COMPLETE!                    ${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "Server IP: ${DE_IP}"
echo -e "VPN Port: ${VPN_PORT}/udp"
echo ""
echo -e "${YELLOW}IMPORTANT - Save these keys for RU server setup:${NC}"
echo -e "  DE Public Key: ${DE_PUBLIC_KEY}"
echo ""
echo -e "${BLUE}AmneziaWG Status:${NC}"
awg show
echo ""
echo -e "${GREEN}Next step: Run deploy-ru-server.sh on the RU server${NC}"
