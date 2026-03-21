#!/bin/bash
#
# KrotVPN Server Deployment Script v2.3.0
# Run this script ON the RU server
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

VPN_PORT="51821"

# Read configuration from file
if [ -f /tmp/krotvpn_deploy.conf ]; then
    echo -e "${BLUE}[CONFIG] Loading configuration from file...${NC}"
    source /tmp/krotvpn_deploy.conf
else
    echo -e "${RED}[ERROR] Configuration file not found: /tmp/krotvpn_deploy.conf${NC}"
    echo "Please run install.sh first"
    exit 1
fi

# Decode base64 passwords
if [ -n "$DE_PASS_B64" ]; then
    DE_PASS=$(echo "$DE_PASS_B64" | base64 -d)
    echo -e "${GREEN}[CONFIG] DE password decoded${NC}"
else
    echo -e "${RED}[ERROR] DE_PASS_B64 not found in config${NC}"
    exit 1
fi

if [ -n "$RU_PASS_B64" ]; then
    RU_PASS=$(echo "$RU_PASS_B64" | base64 -d)
    echo -e "${GREEN}[CONFIG] RU password decoded${NC}"
else
    echo -e "${RED}[ERROR] RU_PASS_B64 not found in config${NC}"
    exit 1
fi

# Validate required variables
if [ -z "$DE_IP" ] || [ -z "$DE_USER" ] || [ -z "$DE_PASS" ]; then
    echo -e "${RED}[ERROR] Missing required configuration${NC}"
    echo "Required: DE_IP, DE_USER, DE_PASS"
    exit 1
fi

# Get RU IPv4 address (force IPv4, multiple fallbacks)
echo -e "${BLUE}[DETECT] Getting RU server IPv4 address...${NC}"
RU_IP=$(curl -4 -s --connect-timeout 5 https://api4.ipify.org 2>/dev/null || \
        curl -4 -s --connect-timeout 5 https://ipv4.icanhazip.com 2>/dev/null || \
        curl -4 -s --connect-timeout 5 https://v4.ident.me 2>/dev/null || \
        ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1' | head -1)

if [ -z "$RU_IP" ] || [[ "$RU_IP" == *":"* ]]; then
    echo -e "${RED}[ERROR] Could not detect IPv4 address${NC}"
    exit 1
fi
echo -e "${GREEN}[OK] RU IPv4: ${RU_IP}${NC}"

# Print banner
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║           KrotVPN Automated Deployment v2.3.0               ║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║  RU Server (Entry): ${RU_IP}                            ║${NC}"
echo -e "${CYAN}║  DE Server (Exit):  ${DE_IP}                            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Install sshpass FIRST (needed for DE connection test)
echo -e "${BLUE}[PREP] Installing sshpass for DE connection...${NC}"
apt update -qq 2>/dev/null
apt install -y -qq sshpass 2>/dev/null
echo -e "${GREEN}✓ sshpass installed${NC}"

# SSH wrapper for DE server
ssh_de() {
    sshpass -p "$DE_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=30 -o LogLevel=ERROR "$DE_USER@$DE_IP" "$@"
}

# Test connection to DE
echo -e "${BLUE}[CHECK] Testing connection to DE server...${NC}"
if ssh_de "echo ok" 2>/dev/null | grep -q "ok"; then
    echo -e "${GREEN}✓ DE server accessible${NC}"
else
    echo -e "${RED}✗ Cannot connect to DE server${NC}"
    echo -e "${YELLOW}  Check that DE server is reachable and credentials are correct${NC}"
    exit 1
fi
echo ""

# ============================================================
# PHASE 1: Setup RU Server
# ============================================================
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}PHASE 1: RU Server - Installing dependencies${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

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
echo -e "${GREEN}✓ Docker installed${NC}"

echo -e "${BLUE}[RU] Installing AmneziaWG...${NC}"
if ! command -v awg &> /dev/null; then
    add-apt-repository ppa:amnezia/ppa -y
    apt update -qq
    apt install -y -qq amneziawg amneziawg-tools
fi
echo -e "${GREEN}✓ AmneziaWG installed${NC}"

echo -e "${BLUE}[RU] Enabling IP forwarding...${NC}"
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-krotvpn.conf
sysctl -p /etc/sysctl.d/99-krotvpn.conf > /dev/null

echo -e "${BLUE}[RU] Generating AmneziaWG keys...${NC}"
mkdir -p /etc/amnezia/amneziawg
cd /etc/amnezia/amneziawg
awg genkey | tee ru_server_private.key | awg pubkey > ru_server_public.key
awg genkey | tee ru_client_private.key | awg pubkey > ru_client_public.key

RU_SERVER_PUBLIC=$(cat ru_server_public.key)
RU_SERVER_PRIVATE=$(cat ru_server_private.key)
RU_CLIENT_PUBLIC=$(cat ru_client_public.key)
RU_CLIENT_PRIVATE=$(cat ru_client_private.key)

echo -e "${GREEN}✓ Keys generated${NC}"
echo -e "  Server Public: ${RU_SERVER_PUBLIC}"
echo ""

# ============================================================
# PHASE 2: Setup DE Server
# ============================================================
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}PHASE 2: DE Server - Installation${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

# Create script for DE server - FIXED: proper firewall config
cat > /tmp/de_setup.sh << 'DESCRIPT'
#!/bin/bash
set -e

RU_CLIENT_PUBLIC="$1"
VPN_PORT="$2"
DE_IP="$3"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

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
echo -e "${GREEN}✓ AmneziaWG installed${NC}"

echo -e "${BLUE}[DE] Enabling IP forwarding...${NC}"
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-krotvpn.conf
sysctl -p /etc/sysctl.d/99-krotvpn.conf > /dev/null

echo -e "${BLUE}[DE] Generating keys...${NC}"
mkdir -p /etc/amnezia/amneziawg
cd /etc/amnezia/amneziawg
awg genkey | tee de_private.key | awg pubkey > de_public.key

DE_PRIVATE=$(cat de_private.key)
DE_PUBLIC=$(cat de_public.key)

echo -e "${GREEN}✓ Keys generated${NC}"
echo -e "  DE Public: ${DE_PUBLIC}"

echo -e "${BLUE}[DE] Creating AmneziaWG config...${NC}"
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
PublicKey = ${RU_CLIENT_PUBLIC}
AllowedIPs = 10.200.0.2/32
EOF

chmod 600 /etc/amnezia/amneziawg/awg0.conf
echo -e "${GREEN}✓ Config created${NC}"

# FIXED: Proper firewall configuration without breaking UFW
echo -e "${BLUE}[DE] Configuring firewall...${NC}"

# Reset UFW but keep it simple
ufw --force reset > /dev/null 2>&1
ufw default allow FORWARD > /dev/null 2>&1
ufw allow 22/tcp > /dev/null 2>&1
ufw allow ${VPN_PORT}/udp > /dev/null 2>&1
ufw --force enable > /dev/null 2>&1

# Add NAT rule directly via iptables (survives reboot via iptables-persistent or rc.local)
iptables -t nat -C POSTROUTING -s 10.200.0.0/24 -o eth0 -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -s 10.200.0.0/24 -o eth0 -j MASQUERADE

# Save iptables rules
mkdir -p /etc/iptables
iptables-save > /etc/iptables/rules.v4

# Create restore script for boot
cat > /etc/rc.local << 'RCLOCAL'
#!/bin/bash
iptables-restore < /etc/iptables/rules.v4
exit 0
RCLOCAL
chmod +x /etc/rc.local 2>/dev/null || true

echo -e "${GREEN}✓ Firewall configured${NC}"

echo -e "${BLUE}[DE] Starting AmneziaWG...${NC}"
awg-quick down awg0 2>/dev/null || true
awg-quick up awg0

# Verify AmneziaWG is running
sleep 1
if ip link show awg0 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ AmneziaWG interface awg0 is UP${NC}"
    awg show
else
    echo -e "${RED}✗ AmneziaWG failed to start!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ DE server ready!${NC}"
DESCRIPT

chmod +x /tmp/de_setup.sh

# Copy and run on DE server
echo -e "${BLUE}[RU] Copying setup script to DE server...${NC}"
sshpass -p "$DE_PASS" scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR /tmp/de_setup.sh "$DE_USER@$DE_IP:/tmp/"

echo -e "${BLUE}[RU] Running setup on DE server...${NC}"
ssh_de "bash /tmp/de_setup.sh '$RU_CLIENT_PUBLIC' '$VPN_PORT' '$DE_IP'"

# Get DE public key
DE_PUBLIC_KEY=$(ssh_de "cat /etc/amnezia/amneziawg/de_public.key")
echo -e "${GREEN}✓ Got DE public key: ${DE_PUBLIC_KEY}${NC}"

# Verify DE AmneziaWG is accessible
echo -e "${BLUE}[RU] Verifying DE AmneziaWG status...${NC}"
DE_AWG_STATUS=$(ssh_de "awg show 2>/dev/null || echo 'FAILED'")
if echo "$DE_AWG_STATUS" | grep -q "peer"; then
    echo -e "${GREEN}✓ DE AmneziaWG is running${NC}"
else
    echo -e "${RED}✗ DE AmneziaWG is NOT running properly${NC}"
    echo "$DE_AWG_STATUS"
fi
echo ""

# ============================================================
# PHASE 3: Complete RU Setup
# ============================================================
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}PHASE 3: RU Server - Completing setup${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""

cd /etc/amnezia/amneziawg

echo -e "${BLUE}[RU] Creating tunnel config to DE...${NC}"
cat > awg-client.conf << EOF
[Interface]
PrivateKey = ${RU_CLIENT_PRIVATE}
Address = 10.200.0.2/24
Table = off
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

echo -e "${BLUE}[RU] Creating VPN server config...${NC}"
cat > awg0.conf << EOF
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

chmod 600 *.conf
echo -e "${GREEN}✓ Configs created${NC}"

# Setup scripts
echo -e "${BLUE}[RU] Creating helper scripts...${NC}"

cat > /usr/local/bin/update_ru_ips.sh << 'UPDATE_SCRIPT'
#!/bin/bash
ipset create ru_ips hash:net 2>/dev/null || ipset flush ru_ips
for net in 10.0.0.0/8 192.168.0.0/16 172.16.0.0/12 127.0.0.0/8; do
    ipset add ru_ips $net 2>/dev/null || true
done
curl -sL --connect-timeout 10 https://raw.githubusercontent.com/ipverse/rir-ip/master/country/ru/ipv4-aggregated.txt 2>/dev/null | \
    grep -v '^#' | grep -E '^[0-9]' | while read line; do
        ipset add ru_ips $line 2>/dev/null || true
    done
echo "RU IPset updated: $(ipset list ru_ips 2>/dev/null | grep 'Number of entries' | awk '{print $4}') entries"
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

/usr/local/bin/update_ru_ips.sh

# Firewall
echo -e "${BLUE}[RU] Configuring firewall...${NC}"
ufw --force reset > /dev/null
ufw allow 22/tcp > /dev/null
ufw allow 80/tcp > /dev/null
ufw allow 443/tcp > /dev/null
ufw allow 8080/tcp > /dev/null
ufw allow 8443/tcp > /dev/null
ufw allow 8000/tcp > /dev/null
ufw allow ${VPN_PORT}/udp > /dev/null
ufw default allow FORWARD > /dev/null
ufw --force enable > /dev/null
echo -e "${GREEN}✓ Firewall configured${NC}"

# Add explicit route to DE server via main gateway (prevent SSH hang)
echo -e "${BLUE}[RU] Adding route to DE server via main gateway...${NC}"
DE_GW=$(ip route | grep default | awk '{print $3}' | head -1)
if [ -n "$DE_GW" ]; then
    ip route add ${DE_IP}/32 via ${DE_GW} 2>/dev/null || true
    echo -e "${GREEN}✓ Route to DE added via ${DE_GW}${NC}"
else
    echo -e "${YELLOW}Warning: Could not detect default gateway${NC}"
fi

# Start AmneziaWG
echo -e "${BLUE}[RU] Starting AmneziaWG...${NC}"
awg-quick down awg0 2>/dev/null || true
awg-quick up awg0
awg-quick down awg-client 2>/dev/null || true
awg-quick up awg-client

# FIXED: Add explicit route to tunnel subnet (Table=off doesn't add it)
echo -e "${BLUE}[RU] Adding route to DE tunnel subnet...${NC}"
ip route add 10.200.0.0/24 dev awg-client 2>/dev/null || true
echo -e "${GREEN}✓ Route to 10.200.0.0/24 added${NC}"

# Show routing table for debugging
echo -e "${BLUE}[RU] Current routes to DE tunnel:${NC}"
ip route show | grep -E "(awg-client|10.200)" || echo "No routes found"

# Verify awg-client is up
echo -e "${BLUE}[RU] Verifying awg-client interface...${NC}"
if ip link show awg-client > /dev/null 2>&1; then
    echo -e "${GREEN}✓ awg-client interface is UP${NC}"
    ip addr show awg-client | grep inet
else
    echo -e "${RED}✗ awg-client interface is DOWN${NC}"
fi

# Show AmneziaWG status
echo -e "${BLUE}[RU] AmneziaWG status:${NC}"
awg show

/usr/local/bin/setup_routing.sh

# Test tunnel - try multiple times
echo -e "${BLUE}[RU] Testing tunnel to DE (10.200.0.1)...${NC}"
TUNNEL_OK=false
for i in 1 2 3 4 5; do
    sleep 2
    if ping -c 2 -W 3 10.200.0.1 > /dev/null 2>&1; then
        TUNNEL_OK=true
        echo -e "${GREEN}✓ Tunnel to DE is working! (attempt $i)${NC}"
        break
    else
        echo -e "${YELLOW}  Attempt $i failed, retrying...${NC}"
    fi
done

if [ "$TUNNEL_OK" = false ]; then
    echo -e "${RED}✗ Tunnel test failed after 5 attempts${NC}"
    echo -e "${YELLOW}  Debugging info:${NC}"
    echo -e "${YELLOW}  - RU awg-client status:${NC}"
    awg show awg-client 2>/dev/null || echo "    Cannot show awg-client"
    echo -e "${YELLOW}  - Routes:${NC}"
    ip route show | grep -E "(awg|10.200)" || echo "    No relevant routes"
    echo -e "${YELLOW}  - DE AmneziaWG status:${NC}"
    ssh_de "awg show" 2>/dev/null || echo "    Cannot connect to DE"
fi

# Update KrotVPN
echo -e "${BLUE}[RU] Updating KrotVPN application...${NC}"
cd /opt/KrotVPN
git pull

# Generate SSL
echo -e "${BLUE}[RU] Generating SSL certificate...${NC}"
mkdir -p /opt/KrotVPN/ssl
cd /opt/KrotVPN/ssl
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout server.key -out server.crt \
    -subj "/C=RU/ST=Moscow/L=Moscow/O=KrotVPN/OU=IT/CN=krotvpn.local" 2>/dev/null
chmod 600 server.key
chmod 644 server.crt
echo -e "${GREEN}✓ SSL certificate generated${NC}"

# Generate .env
echo -e "${BLUE}[RU] Creating configuration...${NC}"
cd /opt/KrotVPN
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
DATA_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

cat > .env << EOF
# === APPLICATION ===
APP_NAME=KrotVPN
APP_VERSION=2.3.0
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
echo -e "${GREEN}✓ Configuration created${NC}"

# Systemd services
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
echo -e "${GREEN}✓ Systemd services created${NC}"

# Docker
echo -e "${BLUE}[RU] Building and starting Docker containers...${NC}"
cd /opt/KrotVPN
docker compose up -d --build

echo ""
sleep 5
echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}        DEPLOYMENT COMPLETE!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Frontend:    ${CYAN}https://${RU_IP}${NC}"
echo -e "  Admin Panel: ${CYAN}https://${RU_IP}:8443${NC}"
echo -e "  Backend API: ${CYAN}https://${RU_IP}:8000${NC}"
echo ""
echo -e "  Create VPN client:"
echo -e "  ${YELLOW}/opt/KrotVPN/deploy/create-client.sh my_client${NC}"
echo ""

# Cleanup
rm -f /tmp/krotvpn_deploy.conf /tmp/de_setup.sh
