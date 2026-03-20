# 🚀 KrotVPN Quick Start Guide

## Твои серверы

| Сервер | IP | Роль |
|--------|-----|------|
| 🇷🇺 RU | `212.113.121.164` | Entry Node (Backend + Frontend + VPN Server) |
| 🇩🇪 DE | `95.216.149.110` | Exit Node (VPN Exit) |

---

## ⚡ Быстрый старт (одной командой)

Если у тебя настроен SSH без пароля:

```bash
# Клонируй проект
git clone https://github.com/anyagixx/KrotVPN.git
cd KrotVPN

# Запусти быстрый деплой
./deploy/quick-start.sh
```

---

## 📋 Пошаговая установка

### Шаг 1: Подготовка SSH

```bash
# Настрой SSH ключи для безпарольного доступа
ssh-copy-id root@95.216.149.110
ssh-copy-id root@212.113.121.164
```

### Шаг 2: Установка на DE сервер (Германия)

```bash
# Скопируй скрипт
scp deploy/deploy-de-server.sh root@95.216.149.110:/tmp/

# Запусти на DE сервере
ssh root@95.216.149.110 "bash /tmp/deploy-de-server.sh"
```

**Запиши DE Public Key!** Он понадобится для RU сервера.

### Шаг 3: Установка на RU сервер (Россия)

```bash
# Скопируй скрипт
scp deploy/deploy-ru-server.sh root@212.113.121.164:/tmp/

# Запусти на RU сервере
ssh root@212.113.121.164 "bash /tmp/deploy-ru-server.sh"
```

Когда скрипт спросит - введи DE Public Key.

**Запиши RU Client Public Key!** Его нужно добавить на DE сервер.

### Шаг 4: Добавь RU peer на DE сервер

```bash
ssh root@95.216.149.110

# Добавь peer в конфиг
nano /etc/amnezia/amneziawg/awg0.conf
```

Добавь в конец файла:
```ini
[Peer]
PublicKey = ВСТАВЬ_RU_CLIENT_PUBLIC_KEY
AllowedIPs = 10.200.0.2/32
```

Перезапусти AmneziaWG:
```bash
awg-quick down awg0
awg-quick up awg0
```

### Шаг 5: Проверь туннель

На RU сервере:
```bash
ssh root@212.113.121.164

# Запусти туннель
awg-quick up awg0
awg-quick up awg-client

# Настрой routing
/usr/local/bin/setup_routing.sh

# Проверь связь с DE
ping -c 3 10.200.0.1
```

### Шаг 6: Запусти Docker

На RU сервере:
```bash
cd /opt/KrotVPN
docker compose up -d --build
```

---

## ✅ Проверка

Открой в браузере:
- **Frontend**: http://212.113.121.164
- **Admin Panel**: http://212.113.121.164:8080
- **Backend Health**: http://212.113.121.164:8000/health

---

## 👤 Создание VPN клиента

```bash
ssh root@212.113.121.164
/opt/KrotVPN/deploy/create-client.sh my_first_client
```

Отсканируй QR код приложением **AmneziaWG** на телефоне.

---

## 🔧 Полезные команды

### Статус сервисов

```bash
# AmneziaWG
awg show

# Docker
docker compose ps
docker compose logs -f backend

# Routing
ip rule list
ipset list ru_ips | head
```

### Перезапуск

```bash
# Перезапустить Docker
docker compose restart

# Перезапустить AmneziaWG
awg-quick down awg0 && awg-quick up awg0
awg-quick down awg-client && awg-quick up awg-client
```

### Обновление RU IP

```bash
/usr/local/bin/update_ru_ips.sh
```

---

## 🗑️ Удаление клиента

```bash
/opt/KrotVPN/deploy/remove-client.sh client_name
```

---

## 📱 Клиентские приложения

- **Android**: [AmneziaWG в Google Play](https://play.google.com/store/apps/details?id=org.amnezia.awg)
- **iOS**: [AmneziaWG в App Store](https://apps.apple.com/app/amneziawg/id6448364248)
- **Windows**: [AmneziaWG для Windows](https://github.com/amnezia-vpn/amneziawg-windows-client/releases)
- **macOS**: [AmneziaWG для macOS](https://github.com/amnezia-vpn/amneziawg-apple/releases)

---

## ⚠️ Устранение неполадок

### Туннель не работает

1. Проверь что оба интерфейса запущены:
```bash
awg show
```

2. Проверь firewall:
```bash
ufw status
```

3. Проверь что порты открыты:
```bash
ss -ulpn | grep 51821
```

### Docker не запускается

1. Проверь логи:
```bash
docker compose logs backend
```

2. Проверь .env:
```bash
cat /opt/KrotVPN/.env
```

### Клиент не подключается

1. Проверь что peer добавлен:
```bash
awg show
```

2. Проверь конфиг клиента:
```bash
cat /etc/amnezia/amneziawg/clients/client_name.conf
```

---

## 📞 Поддержка

- **GitHub Issues**: https://github.com/anyagixx/KrotVPN/issues
- **Telegram**: @krotvpn_support
