# 🐀 KrotVPN

**Коммерческий VPN-сервис с обфускацией AmneziaWG и split-tunneling**

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.11-green)
![React](https://img.shields.io/badge/react-18-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## 🌟 Особенности

- **AmneziaWG** - обфусцированный WireGuard протокол для обхода DPI
- **Split-Tunneling** - российские сайты открываются напрямую
- **Двухуровневая архитектура** - RU Entry Node + DE Exit Node
- **Коммерческая модель** - подписки, триалы, реферальная программа
- **Telegram Bot** - управление через Telegram
- **PWA** - установка как приложение на телефон

## 🏗️ Архитектура

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Клиенты   │ ──AWG─▶ │  RU Сервер  │ ──AWG─▶ │  DE Сервер  │ ──▶ │ Интернет
│  (Россия)   │         │ (Entry Node)│         │ (Exit Node) │
└─────────────┘         └─────────────┘         └─────────────┘
                              │
                              ▼
                        ┌─────────────┐
                        │   Docker    │
                        │  - Backend  │
                        │  - Frontend │
                        │  - Admin    │
                        │  - PostgreSQL
                        │  - Redis    │
                        └─────────────┘
```

## ⚡ Быстрый старт

### Требования

| Компонент | RU Сервер | DE Сервер |
|-----------|-----------|-----------|
| OS | Ubuntu 20.04/22.04 | Ubuntu 20.04/22.04 |
| CPU | 2+ ядер | 1+ ядро |
| RAM | 2+ GB | 1+ GB |
| Порты | 22, 80, 443, 51821/udp | 22, 51821/udp |

### Установка

1. **Клонируй репозиторий:**
```bash
git clone https://github.com/anyagixx/KrotVPN.git
cd KrotVPN
```

2. **Настрой SSH доступ:**
```bash
ssh-copy-id root@DE_SERVER_IP
ssh-copy-id root@RU_SERVER_IP
```

3. **Запусти быстрый деплой:**
```bash
./deploy/quick-start.sh
```

Или следуй [пошаговой инструкции](QUICKSTART.md).

## 📱 Клиентские приложения

| Платформа | Скачать |
|-----------|---------|
| Android | [Google Play](https://play.google.com/store/apps/details?id=org.amnezia.awg) |
| iOS | [App Store](https://apps.apple.com/app/amneziawg/id6448364248) |
| Windows | [GitHub Releases](https://github.com/amnezia-vpn/amneziawg-windows-client/releases) |
| macOS | [GitHub Releases](https://github.com/amnezia-vpn/amneziawg-apple/releases) |

## 🔧 Управление

### Создание VPN клиента

```bash
ssh root@RU_SERVER_IP
/opt/KrotVPN/deploy/create-client.sh username
```

### Проверка состояния

```bash
/opt/KrotVPN/deploy/health-check.sh
```

### Логи

```bash
cd /opt/KrotVPN
docker compose logs -f backend
```

## 📁 Структура проекта

```
KrotVPN/
├── backend/                # FastAPI Backend
│   ├── app/
│   │   ├── core/          # Config, Security, Database
│   │   ├── users/         # Auth & Users
│   │   ├── vpn/           # AmneziaWG Integration
│   │   ├── billing/       # YooKassa Payments
│   │   ├── referrals/     # Referral System
│   │   └── main.py        # Entry Point
│   └── Dockerfile
│
├── frontend/              # React User Dashboard
│   ├── src/
│   │   ├── pages/        # Dashboard, Config, Subscription
│   │   ├── stores/       # Zustand State
│   │   └── i18n/         # RU/EN Translations
│   ├── Dockerfile
│   └── nginx.conf
│
├── frontend-admin/        # React Admin Panel
│   ├── src/
│   │   └── pages/        # Users, Servers, Plans, Analytics
│   └── Dockerfile
│
├── telegram-bot/          # Telegram Bot
│   └── bot.py
│
├── deploy/                # Deployment Scripts
│   ├── deploy-de-server.sh
│   ├── deploy-ru-server.sh
│   ├── create-client.sh
│   ├── remove-client.sh
│   ├── health-check.sh
│   └── quick-start.sh
│
├── docker-compose.yml
├── .env.example
└── QUICKSTART.md
```

## 🔐 Безопасность

- JWT токены с коротким сроком жизни
- Fernet шифрование чувствительных данных
- Rate limiting на API endpoints
- CORS whitelist
- UFW firewall на обоих серверах

## 💰 Монетизация

- **Триал**: 3 дня бесплатно
- **Подписки**: 1/3/6/12 месяцев
- **Реферальная программа**: +7 дней за приглашение
- **YooKassa**: приём платежей

## 🌐 API Endpoints

| Endpoint | Описание |
|----------|----------|
| `GET /health` | Health check |
| `POST /api/auth/register` | Регистрация |
| `POST /api/auth/login` | Авторизация |
| `GET /api/vpn/config` | Получить конфиг VPN |
| `GET /api/vpn/qr` | QR код для клиента |
| `GET /api/subscription/status` | Статус подписки |
| `POST /api/billing/create-payment` | Создать платёж |

Полная документация: `http://RU_SERVER_IP:8000/docs`

## 📞 Поддержка

- **GitHub Issues**: https://github.com/anyagixx/KrotVPN/issues
- **Telegram**: @krotvpn_support

## 📄 Лицензия

MIT License

---

**Сделано с ❤️ для свободного интернета**
