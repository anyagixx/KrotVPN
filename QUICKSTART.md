# 🚀 KrotVPN Quick Start Guide

## One-Line Installation

```bash
curl -fsSL https://raw.githubusercontent.com/anyagixx/KrotVPN/main/install.sh | bash
```

Or with wget:

```bash
wget -qO- https://raw.githubusercontent.com/anyagixx/KrotVPN/main/install.sh | bash
```

The installer will guide you through the setup process interactively.

---

## Requirements

- **Two servers** (Ubuntu 20.04/22.04):
  - RU Server (Russia) - Entry node
  - DE Server (Germany/EU) - Exit node
- **Root access** to both servers
- **Linux machine** to run the installer (or WSL2 on Windows)

---

## What the Installer Does

1. ✅ Checks your environment
2. ✅ Asks for server IP addresses
3. ✅ Helps set up SSH keys
4. ✅ Downloads KrotVPN
5. ✅ Deploys to both servers automatically
6. ✅ Generates SSL certificates for HTTPS
7. ✅ Starts all services

---

## After Installation

### Access Your VPN Service

| Service | URL |
|---------|-----|
| **Frontend** | `https://YOUR_RU_IP` |
| **Admin Panel** | `https://YOUR_RU_IP:8443` |
| **Backend API** | `https://YOUR_RU_IP:8000` |

> ⚠️ **Note:** Your browser will warn about the self-signed certificate. Click "Advanced" → "Proceed" to continue.

### Admin Panel Login

Use these credentials to access the admin panel at `https://YOUR_RU_IP:8443`:

| Field | Value |
|-------|-------|
| **Email** | `admin@krotvpn.com` |
| **Password** | `ChangeMeImmediately123!` |

> ⚠️ **Important**: Change the default password immediately after first login!

### Create VPN Client

```bash
ssh root@YOUR_RU_IP "/opt/KrotVPN/deploy/create-client.sh my_client"
```

Scan the QR code with **AmneziaWG** app on your phone.

### Configure (Optional)

Edit `/opt/KrotVPN/.env` on RU server:

```bash
ssh root@YOUR_RU_IP "nano /opt/KrotVPN/.env"
```

| Variable | Description |
|----------|-------------|
| `YOOKASSA_SHOP_ID` | YooKassa shop ID for payments |
| `YOOKASSA_SECRET_KEY` | YooKassa secret key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `ADMIN_PASSWORD` | **Change this!** |

After editing, restart:

```bash
ssh root@YOUR_RU_IP "cd /opt/KrotVPN && docker compose restart"
```

---

## Client Apps

- **Android**: [AmneziaWG](https://play.google.com/store/apps/details?id=org.amnezia.awg)
- **iOS**: [AmneziaWG](https://apps.apple.com/app/amneziawg/id6448364248)
- **Windows**: [AmneziaWG](https://github.com/amnezia-vpn/amneziawg-windows-client/releases)
- **macOS**: [AmneziaWG](https://github.com/amnezia-vpn/amneziawg-apple/releases)

---

## Troubleshooting

### Check service status

```bash
ssh root@YOUR_RU_IP "docker compose -f /opt/KrotVPN/docker-compose.yml ps"
```

### View logs

```bash
ssh root@YOUR_RU_IP "docker compose -f /opt/KrotVPN/docker-compose.yml logs -f backend"
```

### Check VPN tunnel

```bash
ssh root@YOUR_RU_IP "awg show"
ssh root@YOUR_RU_IP "ping -c 3 10.200.0.1"
```

### Restart services

```bash
ssh root@YOUR_RU_IP "cd /opt/KrotVPN && docker compose restart"
```

---

## Support

- **GitHub**: https://github.com/anyagixx/KrotVPN
- **Issues**: https://github.com/anyagixx/KrotVPN/issues
