#!/bin/bash
#
# KrotVPN全自动部署脚本
# Запусти на своём компьютере - всё само развернётся
#
# Usage: ./auto-deploy.sh
#

set -e

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Конфигурация серверов
RU_IP="212.113.121.164"
DE_IP="95.216.149.110"
VPN_PORT="51821"

echo -e "${BLUE}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     KrotVPN - Автоматический деплой          ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "RU сервер: ${GREEN}${RU_IP}${NC}"
echo -e "DE сервер: ${GREEN}${DE_IP}${NC}"
echo ""

# Проверка SSH
echo -e "${YELLOW}[1/6] Проверка SSH доступа...${NC}"

if ! ssh -o ConnectTimeout=5 -o BatchMode=yes root@${DE_IP} "echo ok" 2>/dev/null; then
    echo -e "${RED}✗ Нет доступа к DE серверу${NC}"
    echo -e "${YELLOW}Выполни: ssh-copy-id root@${DE_IP}${NC}"
    exit 1
fi
echo -e "${GREEN}✓ DE сервер доступен${NC}"

if ! ssh -o ConnectTimeout=5 -o BatchMode=yes root@${RU_IP} "echo ok" 2>/dev/null; then
    echo -e "${RED}✗ Нет доступа к RU серверу${NC}"
    echo -e "${YELLOW}Выполни: ssh-copy-id root@${RU_IP}${NC}"
    exit 1
fi
echo -e "${GREEN}✓ RU сервер доступен${NC}"

# ============================================
# DEPLOY DE SERVER
# ============================================
echo ""
echo -e "${YELLOW}[2/6] Установка DE сервера (Германия)...${NC}"

ssh root@${DE_IP} 'bash -s' << 'DESCRIPT'
set -e

echo "===> Обновление системы..."
apt update && apt upgrade -y

echo "===> Установка зависимостей..."
apt install -y software-properties-common python3-launchpadlib gnupg2 \
    linux-headers-$(uname -r) curl wget git ipset iptables ufw qrencode

echo "===> Установка AmneziaWG..."
if ! command -v awg &> /dev/null; then
    add-apt-repository ppa:amnezia/ppa -y
    apt update
    apt install -y amneziawg amneziawg-tools
fi

echo "===> Включение IP форвардинга..."
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-krotvpn.conf
sysctl -p /etc/sysctl.d/99-krotvpn.conf

echo "===> Генерация ключей..."
mkdir -p /etc/amnezia/amneziawg
cd /etc/amnezia/amneziawg
awg genkey | tee de_private.key | awg pubkey > de_public.key

echo "===> Создание конфигурации (без пира пока)..."
cat > /etc/amnezia/amneziawg/awg0.conf << EOF
[Interface]
PrivateKey = $(cat de_private.key)
Address = 10.200.0.1/24
ListenPort = 51821
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

echo "===> Настройка firewall..."
ufw --force reset
ufw allow 22/tcp
ufw allow 51821/udp
sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw

# NAT rules
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

ufw --force enable

echo "===> DE сервер готов!"
DESCRIPT

# Получаем DE public key
DE_PUBLIC_KEY=$(ssh root@${DE_IP} "cat /etc/amnezia/amneziawg/de_public.key")
echo -e "${GREEN}DE Public Key: ${DE_PUBLIC_KEY}${NC}"

# ============================================
# DEPLOY RU SERVER
# ============================================
echo ""
echo -e "${YELLOW}[3/6] Установка RU сервера (Россия)...${NC}"

ssh root@${RU_IP} DE_PUBLIC_KEY="${DE_PUBLIC_KEY}" DE_IP="${DE_IP}" 'bash -s' << 'RUSCRIPT'
set -e
DE_PUBLIC_KEY=$DE_PUBLIC_KEY
DE_IP=$DE_IP

echo "===> Обновление системы..."
apt update && apt upgrade -y

echo "===> Установка Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
apt install -y docker-compose-plugin

echo "===> Установка зависимостей..."
apt install -y software-properties-common python3-launchpadlib gnupg2 \
    linux-headers-$(uname -r) curl wget git ipset iptables ufw qrencode \
    python3-pip python3-cryptography

echo "===> Установка AmneziaWG..."
if ! command -v awg &> /dev/null; then
    add-apt-repository ppa:amnezia/ppa -y
    apt update
    apt install -y amneziawg amneziawg-tools
fi

echo "===> Включение IP форвардинга..."
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-krotvpn.conf
sysctl -p /etc/sysctl.d/99-krotvpn.conf

echo "===> Генерация ключей..."
mkdir -p /etc/amnezia/amneziawg
cd /etc/amnezia/amneziawg
awg genkey | tee ru_server_private.key | awg pubkey > ru_server_public.key
awg genkey | tee ru_client_private.key | awg pubkey > ru_client_public.key

RU_SERVER_PRIVATE_KEY=$(cat ru_server_private.key)
RU_SERVER_PUBLIC_KEY=$(cat ru_server_public.key)
RU_CLIENT_PRIVATE_KEY=$(cat ru_client_private.key)
RU_CLIENT_PUBLIC_KEY=$(cat ru_client_public.key)

echo "===> Создание конфигурации клиента (туннель к DE)..."
cat > /etc/amnezia/amneziawg/awg-client.conf << EOF
[Interface]
PrivateKey = ${RU_CLIENT_PRIVATE_KEY}
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
Endpoint = ${DE_IP}:51821
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF

echo "===> Создание конфигурации сервера (для клиентов)..."
cat > /etc/amnezia/amneziawg/awg0.conf << EOF
[Interface]
PrivateKey = ${RU_SERVER_PRIVATE_KEY}
Address = 10.10.0.1/24
ListenPort = 51821
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

echo "===> Создание скриптов routing..."
cat > /usr/local/bin/update_ru_ips.sh << 'SCRIPT'
#!/bin/bash
ipset create ru_ips hash:net 2>/dev/null || ipset flush ru_ips
ipset add ru_ips 10.0.0.0/8 2>/dev/null || true
ipset add ru_ips 192.168.0.0/16 2>/dev/null || true
ipset add ru_ips 172.16.0.0/12 2>/dev/null || true
ipset add ru_ips 127.0.0.0/8 2>/dev/null || true
curl -sL --connect-timeout 10 https://raw.githubusercontent.com/ipverse/rir-ip/master/country/ru/ipv4-aggregated.txt 2>/dev/null | \
    grep -v '^#' | grep -E '^[0-9]' | while read line; do
        ipset add ru_ips $line 2>/dev/null || true
    done
echo "RU IPset updated"
SCRIPT
chmod +x /usr/local/bin/update_ru_ips.sh

cat > /usr/local/bin/setup_routing.sh << 'SCRIPT'
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

iptables -A FORWARD -i $CLIENT_IF -j ACCEPT 2>/dev/null || true
iptables -A FORWARD -o $CLIENT_IF -j ACCEPT 2>/dev/null || true

echo "Routing configured"
SCRIPT
chmod +x /usr/local/bin/setup_routing.sh

/usr/local/bin/update_ru_ips.sh

echo "===> Настройка firewall..."
ufw --force reset
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8080/tcp
ufw allow 51821/udp
sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw
ufw --force enable

echo "===> Клонирование проекта..."
cd /opt
if [ -d "KrotVPN" ]; then
    cd KrotVPN && git pull
else
    git clone https://github.com/anyagixx/KrotVPN.git
    cd KrotVPN
fi

echo "===> Генерация секретов..."
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
DATA_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

cat > .env << EOF
APP_NAME=KrotVPN
APP_VERSION=2.4.20
DEBUG=false
ENVIRONMENT=production
HOST=0.0.0.0
PORT=8000

SECRET_KEY=${SECRET_KEY}
DATA_ENCRYPTION_KEY=${DATA_KEY}
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

DB_USER=krotvpn
DB_PASSWORD=${DB_PASSWORD}
DB_NAME=krotvpn
DATABASE_URL=postgresql+asyncpg://krotvpn:${DB_PASSWORD}@db:5432/krotvpn

REDIS_URL=redis://redis:6379/0

CORS_ORIGINS=["http://212.113.121.164","http://localhost"]

ADMIN_EMAIL=admin@krotvpn.com
ADMIN_PASSWORD=ChangeMeImmediately123!

VPN_SUBNET=10.10.0.0/24
VPN_PORT=51821
VPN_DNS=8.8.8.8, 1.1.1.1
VPN_MTU=1360
VPN_SERVER_PUBLIC_KEY=${RU_SERVER_PUBLIC_KEY}
VPN_SERVER_ENDPOINT=212.113.121.164

AWG_JC=120
AWG_JMIN=50
AWG_JMAX=1000
AWG_S1=111
AWG_S2=222
AWG_H1=1
AWG_H2=2
AWG_H3=3
AWG_H4=4

TRIAL_DAYS=3
REFERRAL_BONUS_DAYS=7
REFERRAL_MIN_PAYMENT=100.0

DOMAIN=212.113.121.164
EOF

chmod 600 .env

echo "===> RU сервер готов!"
echo "RU_CLIENT_PUBLIC_KEY=${RU_CLIENT_PUBLIC_KEY}"
RUSCRIPT

# Получаем RU client public key
RU_CLIENT_PUBLIC_KEY=$(ssh root@${RU_IP} "cat /etc/amnezia/amneziawg/ru_client_public.key")
echo -e "${GREEN}RU Client Public Key: ${RU_CLIENT_PUBLIC_KEY}${NC}"

# ============================================
# ADD RU PEER TO DE SERVER
# ============================================
echo ""
echo -e "${YELLOW}[4/6] Добавление RU пира на DE сервер...${NC}"

ssh root@${DE_IP} RU_CLIENT_PUBLIC_KEY="${RU_CLIENT_PUBLIC_KEY}" 'bash -s' << 'ADDPEER'
RU_CLIENT_PUBLIC_KEY=$RU_CLIENT_PUBLIC_KEY

# Добавляем пир в конфиг
cat >> /etc/amnezia/amneziawg/awg0.conf << EOF

[Peer]
PublicKey = ${RU_CLIENT_PUBLIC_KEY}
AllowedIPs = 10.200.0.2/32
EOF

# Запускаем AmneziaWG
awg-quick up awg0 2>/dev/null || true

echo "RU peer added to DE server"
ADDPEER

echo -e "${GREEN}✓ RU peer добавлен на DE сервер${NC}"

# ============================================
# START SERVICES ON RU SERVER
# ============================================
echo ""
echo -e "${YELLOW}[5/6] Запуск сервисов на RU сервере...${NC}"

ssh root@${RU_IP} 'bash -s' << 'STARTSERVICES'
# Запускаем AmneziaWG
echo "===> Запуск AmneziaWG..."
awg-quick up awg0 2>/dev/null || true
awg-quick up awg-client 2>/dev/null || true

# Настраиваем routing
echo "===> Настройка routing..."
/usr/local/bin/setup_routing.sh

# Создаём systemd сервисы
cat > /etc/systemd/system/krotvpn-routing.service << 'SERVICE'
[Unit]
Description=KrotVPN Routing
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/setup_routing.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable krotvpn-routing

# Запускаем Docker
echo "===> Запуск Docker контейнеров..."
cd /opt/KrotVPN
docker compose up -d --build

echo "===> Ожидание запуска backend..."
sleep 15

# Проверяем
echo "===> Проверка туннеля к DE..."
ping -c 3 10.200.0.1 || echo "Туннель не работает!"

echo "===> Проверка backend..."
curl -sf http://localhost:8000/health && echo " - OK" || echo " - FAILED"

STARTSERVICES

# ============================================
# FINAL CHECK
# ============================================
echo ""
echo -e "${YELLOW}[6/6] Финальная проверка...${NC}"

# Проверяем DE
echo -e "${BLUE}DE сервер:${NC}"
ssh root@${DE_IP} "awg show"

# Проверяем RU
echo ""
echo -e "${BLUE}RU сервер:${NC}"
ssh root@${RU_IP} "awg show"

echo ""
echo -e "${BLUE}Docker:${NC}"
ssh root@${RU_IP} "docker ps"

# ============================================
# DONE
# ============================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ДЕПЛОЙ ЗАВЕРШЁН!                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Доступ к сервису:${NC}"
echo -e "  Frontend:    ${GREEN}http://${RU_IP}${NC}"
echo -e "  Admin Panel: ${GREEN}http://${RU_IP}:8080${NC}"
echo -e "  Backend API: ${GREEN}http://${RU_IP}:8000${NC}"
echo -e "  Health:      ${GREEN}http://${RU_IP}:8000/health${NC}"
echo ""
echo -e "${BLUE}Создание VPN клиента:${NC}"
echo -e "  ssh root@${RU_IP} '/opt/KrotVPN/deploy/create-client.sh user1'"
echo ""
