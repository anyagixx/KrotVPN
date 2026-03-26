#!/bin/bash
#
# KrotVPN Fully Automated Deployment Script
# Uses SSH password authentication
#
# Usage: ./deploy/deploy-all.sh
# Environment variables: RU_IP, RU_USER, RU_PASS, DE_IP, DE_USER, DE_PASS
# GRACE-lite operational contract:
# - This is a high-risk script: it provisions servers, writes secrets and mutates host networking.
# - It relies on `sshpass` and disabled host key verification; do not treat it as a safe baseline.
# - Default credentials, port exposure and generated `.env` values here directly affect production security.
# - Any meaningful change must be reviewed as an infrastructure/security change, not just shell refactoring.
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration from environment or defaults
RU_IP="${RU_IP:-212.113.121.164}"
RU_USER="${RU_USER:-root}"
RU_PASS="${RU_PASS:-}"
DE_IP="${DE_IP:-95.216.149.110}"
DE_USER="${DE_USER:-root}"
DE_PASS="${DE_PASS:-}"
VPN_PORT="51821"

# SSH command wrapper
ssh_ru() {
    sshpass -p "$RU_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=30 -o LogLevel=ERROR "$RU_USER@$RU_IP" "$@"
}

ssh_de() {
    sshpass -p "$DE_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=30 -o LogLevel=ERROR "$DE_USER@$DE_IP" "$@"
}

# Print banner
echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           KrotVPN Automated Deployment v2.4.25              ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  RU Server (Entry): ${RU_IP}                            ║"
echo "║  DE Server (Exit):  ${DE_IP}                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check credentials
if [ -z "$RU_PASS" ] || [ -z "$DE_PASS" ]; then
    echo -e "${RED}ERROR: SSH passwords not set${NC}"
    echo -e "${YELLOW}Set environment variables: RU_PASS and DE_PASS${NC}"
    exit 1
fi

# Check connections
echo -e "${BLUE}[CHECK] Testing SSH connections...${NC}"

if ! ssh_ru "echo ok" 2>/dev/null | grep -q "ok"; then
    echo -e "${RED}ERROR: Cannot connect to RU server${NC}"
    exit 1
fi
echo -e "${GREEN}✓ RU server accessible${NC}"

if ! ssh_de "echo ok" 2>/dev/null | grep -q "ok"; then
    echo -e "${RED}ERROR: Cannot connect to DE server${NC}"
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

ssh_ru "bash -s" << 'REMOTE_SCRIPT'
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

require_command() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo -e "${RED}[RU] Missing required command: ${cmd}${NC}"
        exit 1
    fi
}

verify_host_routing_tools() {
    local tools=(ip ipset iptables awg awg-quick curl awk grep)
    for tool in "${tools[@]}"; do
        require_command "$tool"
    done
    echo -e "${GREEN}[RU] Host routing toolchain verified${NC}"
}

echo -e "${BLUE}[RU] Updating system...${NC}"
apt update -qq && apt upgrade -y -qq

echo -e "${BLUE}[RU] Installing dependencies...${NC}"
apt install -y -qq software-properties-common python3-launchpadlib gnupg2 \
    linux-headers-$(uname -r) curl wget git ipset iptables ufw qrencode \
    python3-pip python3-cryptography ca-certificates gnupg openssl

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
verify_host_routing_tools

echo -e "${BLUE}[RU] Enabling IP forwarding...${NC}"
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-krotvpn.conf
sysctl -p /etc/sysctl.d/99-krotvpn.conf > /dev/null

echo -e "${BLUE}[RU] Generating AmneziaWG keys...${NC}"
mkdir -p /etc/amnezia/amneziawg
cd /etc/amnezia/amneziawg

awg genkey | tee ru_server_private.key | awg pubkey > ru_server_public.key
awg genkey | tee ru_client_private.key | awg pubkey > ru_client_public.key

RU_SERVER_PUBLIC=$(cat ru_server_public.key)
RU_CLIENT_PUBLIC=$(cat ru_client_public.key)

echo -e "${GREEN}[RU] Keys generated:${NC}"
echo -e "  Server Public: ${RU_SERVER_PUBLIC}"
echo -e "  Client Public: ${RU_CLIENT_PUBLIC}"
REMOTE_SCRIPT

echo ""

# ============================================================
# PHASE 2: DE Server - Full Setup
# ============================================================
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}PHASE 2: DE Server - Full installation and configuration${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

# Get RU client public key
RU_CLIENT_PUBLIC_KEY=$(ssh_ru "cat /etc/amnezia/amneziawg/ru_client_public.key")

ssh_de "RU_CLIENT_PUBLIC_KEY='${RU_CLIENT_PUBLIC_KEY}' VPN_PORT='${VPN_PORT}' bash -s" << 'REMOTE_SCRIPT'
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

require_command() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo -e "${RED}[DE] Missing required command: ${cmd}${NC}"
        exit 1
    fi
}

verify_host_routing_tools() {
    local tools=(ip iptables awg awg-quick curl grep)
    for tool in "${tools[@]}"; do
        require_command "$tool"
    done
    echo -e "${GREEN}[DE] Host routing toolchain verified${NC}"
}

echo -e "${BLUE}[DE] Updating system...${NC}"
apt update -qq && apt upgrade -y -qq

echo -e "${BLUE}[DE] Installing dependencies...${NC}"
apt install -y -qq software-properties-common python3-launchpadlib gnupg2 \
    linux-headers-$(uname -r) curl wget git ipset iptables ufw qrencode ca-certificates

echo -e "${BLUE}[DE] Installing AmneziaWG...${NC}"
if ! command -v awg &> /dev/null; then
    add-apt-repository ppa:amnezia/ppa -y
    apt update -qq
    apt install -y -qq amneziawg amneziawg-tools
fi
verify_host_routing_tools

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

cat > /etc/ufw/before.rules << 'NAT'
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
-A ufw-before-input -m conntrack --ctstate INVALID -j DROP
-A ufw-before-input -p icmp --icmp-type echo-request -j ACCEPT
-A ufw-before-output -p icmp --icmp-type echo-request -j ACCEPT
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
DE_PUBLIC_KEY=$(ssh_de "cat /etc/amnezia/amneziawg/de_public.key")

ssh_ru "DE_PUBLIC_KEY='${DE_PUBLIC_KEY}' RU_IP='${RU_IP}' DE_IP='${DE_IP}' VPN_PORT='${VPN_PORT}' bash -s" << 'REMOTE_SCRIPT'
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

cat > /usr/local/bin/update_ru_ips.sh << 'UPDATE_SCRIPT'
#!/bin/bash
ipset create ru_ips hash:net 2>/dev/null || true
ipset add ru_ips 10.0.0.0/8 2>/dev/null || true
ipset add ru_ips 192.168.0.0/16 2>/dev/null || true
ipset add ru_ips 172.16.0.0/12 2>/dev/null || true
ipset add ru_ips 127.0.0.0/8 2>/dev/null || true
curl -sL --connect-timeout 10 https://raw.githubusercontent.com/ipverse/rir-ip/master/country/ru/ipv4-aggregated.txt 2>/dev/null | \
    grep -v '^#' | grep -E '^[0-9]' | while read line; do
        ipset add ru_ips $line 2>/dev/null || true
    done
echo "RU IPset updated"
UPDATE_SCRIPT
chmod +x /usr/local/bin/update_ru_ips.sh

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

/usr/local/bin/update_ru_ips.sh

echo -e "${BLUE}[RU] Configuring firewall...${NC}"
ufw --force reset > /dev/null
ufw allow 22/tcp > /dev/null
ufw allow 80/tcp > /dev/null
ufw allow 443/tcp > /dev/null
ufw allow 8080/tcp > /dev/null
ufw allow 8443/tcp > /dev/null
ufw allow 8000/tcp > /dev/null
ufw allow ${VPN_PORT}/udp > /dev/null
sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw
ufw --force enable > /dev/null

echo -e "${BLUE}[RU] Starting AmneziaWG...${NC}"
awg-quick down awg0 2>/dev/null || true
awg-quick up awg0
systemctl enable awg-quick@awg0 >/dev/null 2>&1 || true
awg-quick down awg-client 2>/dev/null || true
awg-quick up awg-client
systemctl enable awg-quick@awg0 >/dev/null 2>&1 || true
systemctl enable awg-quick@awg-client >/dev/null 2>&1 || true
ip route add 10.200.0.0/24 dev awg-client 2>/dev/null || true

echo -e "${BLUE}[RU] Setting up routing...${NC}"
/usr/local/bin/setup_routing.sh

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

echo -e "${BLUE}[RU] Generating SSL certificate...${NC}"
mkdir -p /opt/KrotVPN/ssl
cd /opt/KrotVPN/ssl
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout server.key -out server.crt \
    -subj "/C=RU/ST=Moscow/L=Moscow/O=KrotVPN/OU=IT/CN=krotvpn.local" 2>/dev/null
chmod 600 server.key
chmod 644 server.crt
echo -e "${GREEN}[RU] SSL certificate generated${NC}"

echo -e "${BLUE}[RU] Generating secrets...${NC}"
cd /opt/KrotVPN
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
DATA_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@krotvpn.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")}"

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
CORS_ORIGINS=["https://${RU_IP}","http://${RU_IP}","http://localhost"]

# === ADMIN ===
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}

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

# === YOOKASSA ===
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=

# === TELEGRAM ===
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_URL=

# === EMAIL ===
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
echo -e "${YELLOW}[RU] Admin credentials saved to /root/.krotvpn-admin-credentials${NC}"

# Systemd services
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
if ssh_ru "ping -c 2 10.200.0.1" 2>/dev/null | grep -q "bytes from"; then
    echo -e "${GREEN}✓ Tunnel working${NC}"
else
    echo -e "${RED}✗ Tunnel not working${NC}"
fi

echo -e "${BLUE}[CHECK] Docker containers...${NC}"
sleep 5
ssh_ru "docker compose -f /opt/KrotVPN/docker-compose.yml ps"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              DEPLOYMENT COMPLETE!                           ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${GREEN}║  🌐 Frontend:    https://${RU_IP}                           ${NC}"
echo -e "${GREEN}║  🔧 Admin Panel: https://${RU_IP}:8443                     ${NC}"
echo -e "${GREEN}║  🔌 Backend API: https://${RU_IP}:8000                     ${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${YELLOW}║  ⚠️  Browser will warn about self-signed certificate.       ${NC}"
echo -e "${YELLOW}║     Click 'Advanced' → 'Proceed' to continue.               ${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
