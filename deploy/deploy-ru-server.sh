#!/bin/bash
#
# KrotVPN RU Server (Entry Node) Deployment Script
# Run this script on the Russian server
#
# Usage:
#   bash deploy-ru-server.sh                           # Interactive mode
#   DE_PUBLIC_KEY=xxx bash deploy-ru-server.sh         # Non-interactive mode
# GRACE-lite operational contract:
# - This script provisions the RU entry node and local app host.
# - It generates keys, writes live VPN config and prepares Docker/runtime dependencies.
# - Output values here become production secrets and should not be logged or reused carelessly.
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

require_command() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo -e "${RED}ERROR: required command not found: ${cmd}${NC}"
        exit 1
    fi
}

verify_host_routing_tools() {
    local tools=(ip ipset iptables awg awg-quick curl awk grep)
    for tool in "${tools[@]}"; do
        require_command "$tool"
    done
    echo -e "${GREEN}Routing host tools verified${NC}"
}

# Configuration
RU_IP="${RU_IP:-212.113.121.164}"
DE_IP="${DE_IP:-95.216.149.110}"
VPN_PORT="${VPN_PORT:-51821}"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   KrotVPN RU Server (Entry Node) Deployment    ${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root${NC}"
    exit 1
fi

# Step 1: Update system
echo -e "${YELLOW}[1/10] Updating system...${NC}"
apt update -qq && apt upgrade -y -qq

# Step 2: Install Docker
echo -e "${YELLOW}[2/10] Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sh /tmp/get-docker.sh
    apt install -y -qq docker-compose-plugin
fi

# Step 3: Install dependencies
echo -e "${YELLOW}[3/10] Installing dependencies...${NC}"
apt install -y -qq software-properties-common python3-launchpadlib gnupg2 \
    linux-headers-$(uname -r) curl wget git ipset iptables ufw qrencode \
    python3-pip python3-cryptography

# Step 4: Install AmneziaWG
echo -e "${YELLOW}[4/10] Installing AmneziaWG...${NC}"
if ! command -v awg &> /dev/null; then
    add-apt-repository ppa:amnezia/ppa -y
    apt update -qq
    apt install -y -qq amneziawg amneziawg-tools
fi

# Step 5: Enable IP forwarding
echo -e "${YELLOW}[5/10] Enabling IP forwarding...${NC}"
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-krotvpn.conf
sysctl -p /etc/sysctl.d/99-krotvpn.conf > /dev/null

# Step 6: Generate keys
echo -e "${YELLOW}[6/10] Generating AmneziaWG keys...${NC}"
mkdir -p /etc/amnezia/amneziawg
cd /etc/amnezia/amneziawg

# Generate server keys (for VPN clients)
awg genkey | tee ru_server_private.key | awg pubkey > ru_server_public.key

# Generate client keys (for tunnel to DE)
awg genkey | tee ru_client_private.key | awg pubkey > ru_client_public.key

RU_SERVER_PRIVATE_KEY=$(cat ru_server_private.key)
RU_SERVER_PUBLIC_KEY=$(cat ru_server_public.key)
RU_CLIENT_PRIVATE_KEY=$(cat ru_client_private.key)
RU_CLIENT_PUBLIC_KEY=$(cat ru_client_public.key)

echo -e "${GREEN}RU Server Keys Generated:${NC}"
echo -e "  Server Public:  ${RU_SERVER_PUBLIC_KEY}"
echo -e "  Client Public:  ${RU_CLIENT_PUBLIC_KEY}"
echo -e "  Private keys stored at /etc/amnezia/amneziawg/*.key with root-only permissions"

# Step 7: Get DE public key
echo ""
if [ -z "$DE_PUBLIC_KEY" ]; then
    echo -e "${YELLOW}[7/10] Enter DE Server Public Key:${NC}"
    echo -e "${YELLOW}(Get from DE server: cat /etc/amnezia/amneziawg/de_public.key)${NC}"
    read -p "> " DE_PUBLIC_KEY
else
    echo -e "${YELLOW}[7/10] Using DE Public Key from environment${NC}"
fi

if [ -z "$DE_PUBLIC_KEY" ]; then
    echo -e "${RED}ERROR: DE Public Key is required!${NC}"
    exit 1
fi

# Create client config (tunnel to DE)
cat > /etc/amnezia/amneziawg/awg-client.conf << EOF
[Interface]
PrivateKey = ${RU_CLIENT_PRIVATE_KEY}
Address = 10.200.0.2/24
Table = off
DNS = 8.8.8.8
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
PublicKey = ${DE_PUBLIC_KEY}
Endpoint = ${DE_IP}:${VPN_PORT}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF

# Create server config (for VPN clients)
cat > /etc/amnezia/amneziawg/awg0.conf << EOF
[Interface]
PrivateKey = ${RU_SERVER_PRIVATE_KEY}
Address = 10.10.0.1/24
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
EOF

chmod 600 /etc/amnezia/amneziawg/*.conf

echo ""
echo -e "${YELLOW}================================================${NC}"
echo -e "${YELLOW}IMPORTANT: Add this key to DE server!${NC}"
echo -e "${YELLOW}================================================${NC}"
echo ""
echo -e "  RU Client Public Key: ${RU_CLIENT_PUBLIC_KEY}"
echo ""
echo -e "${YELLOW}On DE server run:${NC}"
echo -e "  echo -e '\\n[Peer]\\nPublicKey = ${RU_CLIENT_PUBLIC_KEY}\\nAllowedIPs = 10.200.0.2/32' >> /etc/amnezia/amneziawg/awg0.conf"
echo -e "  awg-quick down awg0 && awg-quick up awg0"
echo ""

# Step 8: Setup split-tunneling
echo -e "${YELLOW}[8/10] Setting up split-tunneling...${NC}"

# Create RU IP update script
cat > /usr/local/bin/update_ru_ips.sh << 'UPDATE_SCRIPT'
#!/bin/bash
ipset create ru_ips hash:net 2>/dev/null || true
ipset add ru_ips 10.0.0.0/8 2>/dev/null || true
ipset add ru_ips 192.168.0.0/16 2>/dev/null || true
ipset add ru_ips 172.16.0.0/12 2>/dev/null || true
ipset add ru_ips 127.0.0.0/8 2>/dev/null || true
curl -sL --connect-timeout 10 https://raw.githubusercontent.com/ipverse/rir-ip/master/country/ru/ipv4-aggregated.txt 2>/dev/null | \
    grep -v '^#' | grep -E '^[0-9]' | \
    while read line; do
        ipset add ru_ips $line 2>/dev/null || true
    done
COUNT=$(ipset list ru_ips 2>/dev/null | grep 'Number of entries' | awk '{print $4}')
echo "RU IPset updated: ${COUNT:-0} entries"
UPDATE_SCRIPT
chmod +x /usr/local/bin/update_ru_ips.sh

# Create routing setup script
cat > /usr/local/bin/setup_routing.sh << 'ROUTING_SCRIPT'
#!/bin/bash
CLIENT_IF="awg0"
TUNNEL_IF="awg-client"
FWMARK=255
ROUTING_TABLE=100

ipset create ru_ips hash:net 2>/dev/null || ipset flush ru_ips
ipset create custom_direct hash:net 2>/dev/null || ipset flush custom_direct
ipset create custom_vpn hash:net 2>/dev/null || ipset flush custom_vpn

ip rule del fwmark $FWMARK lookup $ROUTING_TABLE 2>/dev/null || true
ip rule add fwmark $FWMARK lookup $ROUTING_TABLE

ip route del default dev $TUNNEL_IF table $ROUTING_TABLE 2>/dev/null || true
ip route add default dev $TUNNEL_IF table $ROUTING_TABLE

iptables -t mangle -F AMNEZIA_PREROUTING 2>/dev/null || true
iptables -t mangle -N AMNEZIA_PREROUTING 2>/dev/null || iptables -t mangle -F AMNEZIA_PREROUTING
iptables -t mangle -D PREROUTING -i $CLIENT_IF -j AMNEZIA_PREROUTING 2>/dev/null || true
iptables -t mangle -A PREROUTING -i $CLIENT_IF -j AMNEZIA_PREROUTING

iptables -t mangle -A AMNEZIA_PREROUTING -m set --match-set custom_vpn dst -j MARK --set-mark $FWMARK
iptables -t mangle -A AMNEZIA_PREROUTING -m set --match-set custom_vpn dst -j RETURN
iptables -t mangle -A AMNEZIA_PREROUTING -m set --match-set custom_direct dst -j RETURN
iptables -t mangle -A AMNEZIA_PREROUTING -m set --match-set ru_ips dst -j RETURN
iptables -t mangle -A AMNEZIA_PREROUTING -j MARK --set-mark $FWMARK

iptables -t nat -D POSTROUTING -o $TUNNEL_IF -j MASQUERADE 2>/dev/null || true
iptables -t nat -A POSTROUTING -o $TUNNEL_IF -j MASQUERADE
iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null || true
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE

iptables -A FORWARD -i $CLIENT_IF -j ACCEPT
iptables -A FORWARD -o $CLIENT_IF -j ACCEPT

echo "Split-tunneling configured!"
ROUTING_SCRIPT
chmod +x /usr/local/bin/setup_routing.sh

cat > /usr/local/bin/krotvpn-sync-awg0.sh << 'SYNC_SCRIPT'
#!/bin/bash
set -e

TMP_FILE=$(mktemp)
cleanup() {
    rm -f "$TMP_FILE"
}
trap cleanup EXIT

awg-quick strip awg0 > "$TMP_FILE"
awg syncconf awg0 "$TMP_FILE"
SYNC_SCRIPT
chmod +x /usr/local/bin/krotvpn-sync-awg0.sh

# Run initial update
verify_host_routing_tools
/usr/local/bin/update_ru_ips.sh

# Step 9: Configure Firewall
echo -e "${YELLOW}[9/10] Configuring firewall...${NC}"

ufw --force reset > /dev/null
ufw allow 22/tcp > /dev/null
ufw allow 80/tcp > /dev/null
ufw allow 443/tcp > /dev/null
ufw allow 8080/tcp > /dev/null
ufw allow ${VPN_PORT}/udp > /dev/null

sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw

ufw --force enable > /dev/null

# Step 10: Clone and setup application
echo -e "${YELLOW}[10/10] Setting up KrotVPN application...${NC}"

cd /opt
if [ -d "KrotVPN" ]; then
    cd KrotVPN
    git pull
else
    git clone https://github.com/anyagixx/KrotVPN.git
    cd KrotVPN
fi

# Generate secrets
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
DATA_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@krotvpn.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")}"

# Create .env file
cat > .env << EOF
# === APPLICATION ===
APP_NAME=KrotVPN
APP_VERSION=2.4.25
DEBUG=false
ENVIRONMENT=production
HOST=0.0.0.0
PORT=8000

# === SECURITY ===
SECRET_KEY=${SECRET_KEY}
DATA_ENCRYPTION_KEY=${DATA_KEY}
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# === DATABASE ===
DB_USER=krotvpn
DB_PASSWORD=${DB_PASSWORD}
DB_NAME=krotvpn
DATABASE_URL=postgresql+asyncpg://krotvpn:${DB_PASSWORD}@db:5432/krotvpn

# === REDIS ===
REDIS_URL=redis://redis:6379/0

# === CORS ===
CORS_ORIGINS=["http://${RU_IP}","https://${RU_IP}","http://localhost"]

# === ADMIN ===
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}

# === VPN CONFIGURATION ===
VPN_SUBNET=10.10.0.0/24
VPN_PORT=${VPN_PORT}
VPN_DNS=8.8.8.8, 1.1.1.1
VPN_MTU=1360
VPN_SERVER_PUBLIC_KEY=${RU_SERVER_PUBLIC_KEY}
VPN_SERVER_ENDPOINT=${RU_IP}

# === AMNEZIAWG OBFUSCATION ===
AWG_JC=120
AWG_JMIN=50
AWG_JMAX=1000
AWG_S1=111
AWG_S2=222
AWG_H1=1
AWG_H2=2
AWG_H3=3
AWG_H4=4

# === TRIAL ===
TRIAL_DAYS=3

# === YOOKASSA (fill in later) ===
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=

# === TELEGRAM (fill in later) ===
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_URL=

# === EMAIL (optional) ===
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
EMAIL_FROM=noreply@krotvpn.com

# === REFERRAL ===
REFERRAL_BONUS_DAYS=7
REFERRAL_MIN_PAYMENT=100.0

# === DOMAIN ===
DOMAIN=${RU_IP}
EOF

chmod 600 .env
cat > /root/.krotvpn-admin-credentials << EOF
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
EOF
chmod 600 /root/.krotvpn-admin-credentials
echo -e "${YELLOW}Admin credentials saved to /root/.krotvpn-admin-credentials${NC}"

# Start AmneziaWG
echo -e "${YELLOW}Starting AmneziaWG...${NC}"
awg-quick up awg0 2>/dev/null || true
awg-quick up awg-client 2>/dev/null || true
systemctl enable awg-quick@awg0 >/dev/null 2>&1 || true
systemctl enable awg-quick@awg-client >/dev/null 2>&1 || true
ip route add 10.200.0.0/24 dev awg-client 2>/dev/null || true

# Setup routing
/usr/local/bin/setup_routing.sh

# Create systemd services
cat > /etc/systemd/system/krotvpn-routing.service << 'SERVICE'
[Unit]
Description=KrotVPN Split-Tunneling Routing
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/setup_routing.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SERVICE

cat > /etc/systemd/system/krotvpn-ru-ips.service << 'SERVICE'
[Unit]
Description=KrotVPN RU IPset Update
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/update_ru_ips.sh

[Install]
WantedBy=multi-user.target
SERVICE

cat > /etc/systemd/system/krotvpn-ru-ips.timer << 'TIMER'
[Unit]
Description=Daily RU IPset Update

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
TIMER

cat > /etc/systemd/system/krotvpn-sync-awg0.service << 'SERVICE'
[Unit]
Description=Sync awg0 peers for KrotVPN
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/krotvpn-sync-awg0.sh
SERVICE

cat > /etc/systemd/system/krotvpn-sync-awg0.path << 'PATHUNIT'
[Unit]
Description=Watch awg0 config changes for KrotVPN

[Path]
PathModified=/etc/amnezia/amneziawg/awg0.conf

[Install]
WantedBy=multi-user.target
PATHUNIT

systemctl daemon-reload
systemctl enable krotvpn-routing krotvpn-ru-ips.timer krotvpn-sync-awg0.path
systemctl start krotvpn-routing
systemctl start krotvpn-sync-awg0.path

# Build and start Docker containers
echo -e "${YELLOW}Building Docker containers...${NC}"
docker compose up -d --build

# Wait for backend
echo -e "${YELLOW}Waiting for backend to start...${NC}"
sleep 10

# Verify
echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}   RU SERVER SETUP COMPLETE!                   ${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "Server IP: ${RU_IP}"
echo -e "VPN Port: ${VPN_PORT}/udp"
echo ""
echo -e "${BLUE}Services:${NC}"
echo -e "  Frontend:    http://${RU_IP}"
echo -e "  Admin Panel: http://${RU_IP}:8080"
echo -e "  Backend API: http://${RU_IP}:8000"
echo -e "  Health:      http://${RU_IP}:8000/health"
echo ""
echo -e "${BLUE}AmneziaWG Status:${NC}"
awg show
echo ""
echo -e "${BLUE}Tunnel to DE:${NC}"
if ping -c 2 10.200.0.1 > /dev/null 2>&1; then
    echo -e "${GREEN}Tunnel OK!${NC}"
else
    echo -e "${RED}Tunnel FAILED - make sure DE server has RU peer configured${NC}"
fi
echo ""
echo -e "${BLUE}Docker Status:${NC}"
docker compose ps
echo ""
echo -e "${GREEN}Setup complete! Open http://${RU_IP} in your browser.${NC}"
