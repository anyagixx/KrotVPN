# 🐀 KrotVPN

**Коммерческий VPN-сервис с обфускацией AmneziaWG и split-tunneling**

![Version](https://img.shields.io/badge/version-2.4.25-blue)
![Python](https://img.shields.io/badge/python-3.11-green)
![React](https://img.shields.io/badge/react-18-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## 🌟 Особенности

- **AmneziaWG** - обфусцированный WireGuard протокол для обхода DPI
- **Split-Tunneling** - российские сайты открываются напрямую
- **HTTPS** - самоподписанные SSL сертификаты для безопасности
- **Двухуровневая архитектура** - RU Entry Node + DE Exit Node
- **Коммерческая модель** - подписки, триалы, реферальная программа
- **Telegram Bot** - управление через Telegram
- **PWA** - установка как приложение на телефон
- **Интерактивная установка** - одна команда для полного деплоя

## 🏗️ Архитектура

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Клиенты   │ ──AWG─▶ │  RU Сервер  │ ──AWG─▶ │  DE Сервер  │ ──▶ Интернет
│  (Россия)   │         │ (Entry Node)│         │ (Exit Node) │
└─────────────┘         └─────────────┘         └─────────────┘
                              │
                              ▼
                        ┌─────────────┐
                        │   Docker    │
                        │  - Nginx    │
                        │  - Backend  │
                        │  - Frontend │
                        │  - Admin    │
                        │  - PostgreSQL
                        │  - Redis    │
                        └─────────────┘
```

## ⚡ Быстрый старт

### Одна команда установки

```bash
curl -fsSL https://raw.githubusercontent.com/anyagixx/KrotVPN/main/install.sh | bash
```

Или с wget:

```bash
wget -qO- https://raw.githubusercontent.com/anyagixx/KrotVPN/main/install.sh | bash
```

Установщик проведёт вас через все шаги интерактивно.

### Требования

| Компонент | RU Сервер | DE Сервер |
|-----------|-----------|-----------|
| OS | Ubuntu 20.04/22.04 | Ubuntu 20.04/22.04 |
| CPU | 2+ ядер | 1+ ядро |
| RAM | 2+ GB | 1+ GB |
| Порты | 22, 80, 443, 8443, 8000, 51821/udp | 22, 51821/udp |

### После установки

| Сервис | URL |
|--------|-----|
| **Frontend** | `https://YOUR_RU_IP` |
| **Admin Panel** | `https://YOUR_RU_IP:8443` |
| **Backend API** | `https://YOUR_RU_IP:8000` |

> ⚠️ Браузер предупредит о самоподписанном сертификате. Нажмите "Дополнительно" → "Перейти".

### 🔐 Доступ к Admin Panel

После установки используйте учётные данные, которые вы задали в `ADMIN_EMAIL` и `ADMIN_PASSWORD` во время деплоя.

> ⚠️ Не оставляйте дефолтные или предсказуемые значения. Для production используйте уникальный длинный пароль.

### 🖥️ CLI инструменты

Управление администраторами через командную строку:

```bash
# Создать нового админа
docker exec -it krotvpn-backend python -m app.cli create-admin -e admin2@example.com -p secret123

# Сбросить пароль
docker exec -it krotvpn-backend python -m app.cli reset-password -e your-admin@example.com -p newsecret

# Список всех админов
docker exec -it krotvpn-backend python -m app.cli list-admins

# Проверить конфигурацию
docker exec -it krotvpn-backend python -m app.cli check-config
```

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
ssh root@YOUR_RU_IP
/opt/KrotVPN/deploy/create-client.sh username
```

### Проверка состояния

```bash
ssh root@YOUR_RU_IP "docker compose -f /opt/KrotVPN/docker-compose.yml ps"
```

### Логи

```bash
ssh root@YOUR_RU_IP "docker compose -f /opt/KrotVPN/docker-compose.yml logs -f backend"
```

### Перезапуск

```bash
ssh root@YOUR_RU_IP "cd /opt/KrotVPN && docker compose restart"
```

## 📁 Структура проекта

```
KrotVPN/
├── install.sh              # Интерактивный установщик
├── backend/                # FastAPI Backend
│   └── app/
│       ├── core/          # Config, Security, Database
│       ├── users/         # Auth & Users
│       ├── vpn/           # AmneziaWG Integration
│       ├── billing/       # YooKassa Payments
│       └── referrals/     # Referral System
│
├── frontend/              # React User Dashboard
├── frontend-admin/        # React Admin Panel
├── telegram-bot/          # Telegram Bot
├── nginx/                 # SSL Proxy
│   ├── Dockerfile
│   ├── nginx.conf
│   └── generate-certs.sh
│
├── deploy/                # Deployment Scripts
│   ├── deploy-all.sh     # Автоматический деплой
│   ├── quick-start.sh    # Wrapper для deploy-all.sh
│   ├── create-client.sh
│   └── remove-client.sh
│
└── docker-compose.yml     # 6 сервисов + nginx
```

## 🔐 Безопасность

- **HTTPS** - самоподписанные SSL сертификаты
- **JWT токены** - короткий срок жизни (15 мин)
- **Fernet шифрование** - чувствительные данные
- **Rate limiting** - защита от брутфорса
- **CORS whitelist** - контроль доступа
- **UFW firewall** - на обоих серверах

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

Полная документация: `https://YOUR_RU_IP:8000/docs`

## 📞 Поддержка

- **GitHub**: https://github.com/anyagixx/KrotVPN
- **Issues**: https://github.com/anyagixx/KrotVPN/issues

## 📄 Лицензия

MIT License

---

**Сделано с ❤️ для свободного интернета**
