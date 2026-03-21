#!/bin/bash
#
# KrotVPN Fully Automated Deployment Script
# Run this locally - it will deploy to both servers automatically
#
# Usage: ./deploy/deploy-all.sh [RU_IP] [DE_IP]
# Default: RU=212.113.121.164 DE=95.216.149.110
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
RU_IP="${1:-212.113.121.164}"
DE_IP="${2:-95.216.149.110}"
VPN_PORT="51821"
CLIENT_VPN_SUBNET="10.10.0.0/24"
TUNNEL_SUBNET="10.200.0.0/24"

# Print banner
echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           KrotVPN Automated Deployment v2.0.1               ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  RU Server (Entry): ${RU_IP}                            ║"
echo "║  DE Server (Exit):  ${DE_IP}                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check SSH access
echo -e "${BLUE}[CHECK] Testing SSH access...${NC}"

if ! ssh -o ConnectTimeout=5 -o BatchMode=yes root@${RU_IP} "echo ok" 2>/dev/null; then
    echo -e "${RED}ERROR: Cannot connect to RU server (${RU_IP})${NC}"
    echo -e "${YELLOW}Run: ssh-copy-id root@${RU_IP}${NC}"
    exit 1
fi
echo -e "${GREEN}✓ RU server accessible${NC}"

if ! ssh -o ConnectTimeout=5 -o BatchMode=yes root@${DE_IP} "echo ok" 2>/dev/null; then
    echo -e "${RED}ERROR: Cannot connect to DE server (${DE_IP})${NC}"
    echo -e "${YELLOW}Run: ssh-copy-id root@${DE_IP}${NC}"
    exit 1
fi
echo -e "${GREEN}✓ DE server accessible${NC}"
echo ""

# ============================================================
# PHASE 1: RU Server - Generate Keys
# ============================================================
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}PHASE 1: RU Server - Installing dependencies & generating keys${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

ssh root@${RU_IP} "bash -s" << 'REMOTE_SCRIPT'
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}[RU] Updating system...${NC}"
apt update -qq && apt upgrade -y -qq

echo -e "${BLUE}[RU] Installing dependencies...${NC}"
apt install -y -qq software-properties-common python3-launchpadlib gnupg2 \
    linux-headers-$(uname -r) curl wget git ipset iptables ufw qrencode \
    python3-pip python3-cryptography ca-certificates gnupg

echo -e "${BLUE}[RU] Installing Docker...${NC}"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sh /tmp/get-docker.sh
    apt install -y -qq docker-compose-plugin
fi

echo -e "${BLUE}[RU] Installing AmneziaWG...${NC}"
if ! command -v awg &> /dev/null; then
    add-apt-repository ppa:amnezia/ppa -y
    apt update -qq
    apt install -y -qq amneziawg amneziawg-tools
fi

echo -e "${BLUE}[RU] Enabling IP forwarding...${NC}"
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-krotvpn.conf
sysctl -p /etc/sysctl.d/99-krotvpn.conf > /dev/null

echo -e "${BLUE}[RU] Generating AmneziaWG keys...${NC}"
mkdir -p /etc/amnezia/amneziawg
cd /etc/amnezia/amneziawg

# Generate server keys (for VPN clients)
awg genkey | tee ru_server_private.key | awg pubkey > ru_server_public.key

# Generate client keys (for tunnel to DE)
awg genkey | tee ru_client_private.key | awg pubkey > ru_client_public.key

RU_SERVER_PUBLIC=$(cat ru_server_public.key)
RU_CLIENT_PUBLIC=$(cat ru_client_public.key)

echo -e "${GREEN}[RU] Keys generated:${NC}"
echo -e "  Server Public: ${RU_SERVER_PUBLIC}"
echo -e "  Client Public: ${RU_CLIENT_PUBLIC}"

# Output for parsing
echo "RU_SERVER_PUBLIC_KEY=${RU_SERVER_PUBLIC}"
echo "RU_CLIENT_PUBLIC_KEY=${RU_CLIENT_PUBLIC}"
REMOTE_SCRIPT

echo ""

# ============================================================
# PHASE 2: DE Server - Full Setup
# ============================================================
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}PHASE 2: DE Server - Full installation and configuration${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

# Get RU keys from previous output
RU_CLIENT_PUBLIC_KEY=$(ssh root@${RU_IP} "cat /etc/amnezia/amneziawg/ru_client_public.key")

ssh root@${DE_IP} "RU_CLIENT_PUBLIC_KEY='${RU_CLIENT_PUBLIC_KEY}' VPN_PORT='${VPN_PORT}' DE_IP='${DE_IP}' bash -s" << 'REMOTE_SCRIPT'
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}[DE] Updating system...${NC}"
apt update -qq && apt upgrade -y -qq

echo -e "${BLUE}[DE] Installing dependencies...${NC}"
apt install -y -qq software-properties-common python3-launchpadlib gnupg2 \
    linux-headers-$(uname -r) curl wget git ipset iptables ufw qrencode \
    ca-certificates

echo -e "${BLUE}[DE] Installing AmneziaWG...${NC}"
if ! command -v awg &> /dev/null; then
    add-apt-repository ppa:amnezia/ppa -y
    apt update -qq
    apt install -y -qq amneziawg amneziawg-tools
fi

echo -e "${BLUE}[DE] Enabling IP forwarding...${NC}"
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-krotvpn.conf
sysctl -p /etc/sysctl.d/99-krotvpn.conf > /dev/null

echo -e "${BLUE}[DE] Generating AmneziaWG keys...${NC}"
mkdir -p /etc/amnezia/amneziawg
cd /etc/amnezia/amneziawg

awg genkey | tee de_private.key | awg pubkey > de_public.key

DE_PRIVATE=$(cat de_private.key)
DE_PUBLIC=$(cat de_public.key)

echo -e "${GREEN}[DE] Keys generated:${NC}"
echo -e "  Public: ${DE_PUBLIC}"

echo -e "${BLUE}[DE] Creating AmneziaWG configuration...${NC}"
cat > /etc/amnezia/amneziawg/awg0.conf << EOF
[Interface]
PrivateKey = ${DE_PRIVATE}
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

echo -e "${BLUE}[DE] Configuring firewall...${NC}"
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

echo -e "${BLUE}[DE] Starting AmneziaWG...${NC}"
awg-quick down awg0 2>/dev/null || true
awg-quick up awg0

echo -e "${GREEN}[DE] Server ready!${NC}"
echo "DE_PUBLIC_KEY=${DE_PUBLIC}"
REMOTE_SCRIPT

echo ""

# ============================================================
# PHASE 3: RU Server - Complete Setup
# ============================================================
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}PHASE 3: RU Server - Completing configuration & Docker${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

# Get DE public key
DE_PUBLIC_KEY=$(ssh root@${DE_IP} "cat /etc/amnezia/amneziawg/de_public.key")

ssh root@${RU_IP} "DE_PUBLIC_KEY='${DE_PUBLIC_KEY}' RU_IP='${RU_IP}' DE_IP='${DE_IP}' VPN_PORT='${VPN_PORT}' bash -s" << 'REMOTE_SCRIPT'
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

cd /etc/amnezia/amneziawg

RU_CLIENT_PRIVATE=$(cat ru_client_private.key)
RU_SERVER_PRIVATE=$(cat ru_server_private.key)
RU_SERVER_PUBLIC=$(cat ru_server_public.key)

echo -e "${BLUE}[RU] Creating tunnel configuration to DE...${NC}"
cat > /etc/amnezia/amneziawg/awg-client.conf << EOF
[Interface]
PrivateKey = ${RU_CLIENT_PRIVATE}
Address = 10.200.0.2/24
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

echo -e "${BLUE}[RU] Creating VPN server configuration...${NC}"
cat > /etc/amnezia/amneziawg/awg0.conf << EOF
[Interface]
PrivateKey = ${RU_SERVER_PRIVATE}
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

echo -e "${BLUE}[RU] Setting up split-tunneling...${NC}"

# Create RU IP update script
cat > /usr/local/bin/update_ru_ips.sh << 'UPDATE_SCRIPT'
#!/bin/bash
ipset create ru_ips hash:net 2>/dev/null || ipset flush ru_ips
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

# Run initial IP update
/usr/local/bin/update_ru_ips.sh

echo -e "${BLUE}[RU] Configuring firewall...${NC}"
ufw --force reset > /dev/null
ufw allow 22/tcp > /dev/null
ufw allow 80/tcp > /dev/null
ufw allow 443/tcp > /dev/null
ufw allow 8080/tcp > /dev/null
ufw allow ${VPN_PORT}/udp > /dev/null
sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw
ufw --force enable > /dev/null

echo -e "${BLUE}[RU] Starting AmneziaWG...${NC}"
awg-quick down awg0 2>/dev/null || true
awg-quick up awg0
awg-quick down awg-client 2>/dev/null || true
awg-quick up awg-client

echo -e "${BLUE}[RU] Setting up routing...${NC}"
/usr/local/bin/setup_routing.sh

# Test tunnel
echo -e "${BLUE}[RU] Testing tunnel to DE...${NC}"
sleep 2
if ping -c 3 10.200.0.1 > /dev/null 2>&1; then
    echo -e "${GREEN}[RU] ✓ Tunnel to DE is working!${NC}"
else
    echo -e "${RED}[RU] ✗ Tunnel test failed${NC}"
fi

echo -e "${BLUE}[RU] Cloning KrotVPN...${NC}"
cd /opt
if [ -d "KrotVPN" ]; then
    cd KrotVPN && git pull
else
    git clone https://github.com/anyagixx/KrotVPN.git
    cd KrotVPN
fi

echo -e "${BLUE}[RU] Generating secrets...${NC}"
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
DATA_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

echo -e "${BLUE}[RU] Creating .env file...${NC}"
cat > .env << EOF
# === APPLICATION ===
APP_NAME=KrotVPN
APP_VERSION=2.0.1
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
ADMIN_EMAIL=admin@krotvpn.com
ADMIN_PASSWORD=ChangeMeImmediately123!

# === VPN CONFIGURATION ===
VPN_SUBNET=10.10.0.0/24
VPN_PORT=${VPN_PORT}
VPN_DNS=8.8.8.8, 1.1.1.1
VPN_MTU=1360
VPN_SERVER_PUBLIC_KEY=${RU_SERVER_PUBLIC}
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

# Create systemd services
echo -e "${BLUE}[RU] Creating systemd services...${NC}"

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

systemctl daemon-reload
systemctl enable krotvpn-routing krotvpn-ru-ips.timer
systemctl start krotvpn-routing

echo -e "${BLUE}[RU] Building and starting Docker containers...${NC}"
docker compose up -d --build

echo -e "${GREEN}[RU] Server setup complete!${NC}"
REMOTE_SCRIPT

echo ""

# ============================================================
# FINAL CHECK
# ============================================================
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}FINAL CHECK: Verifying deployment${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${BLUE}[CHECK] Tunnel RU ↔ DE...${NC}"
if ssh root@${RU_IP} "ping -c 2 10.200.0.1" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Tunnel working${NC}"
else
    echo -e "${RED}✗ Tunnel not working${NC}"
fi

echo -e "${BLUE}[CHECK] Backend health...${NC}"
sleep 5
if curl -s "http://${RU_IP}:8000/health" | grep -q "healthy\|ok"; then
    echo -e "${GREEN}✓ Backend is healthy${NC}"
else
    echo -e "${YELLOW}⚠ Backend may still be starting...${NC}"
fi

echo -e "${BLUE}[CHECK] Docker containers...${NC}"
ssh root@${RU_IP} "docker compose -f /opt/KrotVPN/docker-compose.yml ps"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              DEPLOYMENT COMPLETE!                           ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${GREEN}║  🌐 Frontend:    http://${RU_IP}                           ${NC}"
echo -e "${GREEN}║  🔧 Admin Panel: http://${RU_IP}:8080                     ${NC}"
echo -e "${GREEN}║  🔌 Backend API: http://${RU_IP}:8000                     ${NC}"
echo -e "${GREEN}║  ❤️  Health:      http://${RU_IP}:8000/health              ${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  📱 Create VPN client:                                      ${NC}"
echo -e "${GREEN}║  ssh root@${RU_IP} \"/opt/KrotVPN/deploy/create-client.sh test\"${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  ⚙️  Configure in /opt/KrotVPN/.env:                         ${NC}"
echo -e "${GREEN}║     - YOOKASSA_SHOP_ID                                       ${NC}"
echo -e "${GREEN}║     - YOOKASSA_SECRET_KEY                                    ${NC}"
echo -e "${GREEN}║     - TELEGRAM_BOT_TOKEN                                     ${NC}"
echo -e "${GREEN}║     - ADMIN_PASSWORD (change default!)                       ${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
