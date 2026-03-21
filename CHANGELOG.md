# Changelog

All notable changes to this project will be documented in this file.

## [2.1.2] - 2026-03-21

### Changed
- **MAJOR**: Simplified installation - now uses SSH password authentication instead of SSH keys
  - No more manual SSH key setup required
  - Script asks for username/password for each server
  - Password input shows asterisks for security
- Removed complex ASCII art banner - replaced with simple "KROTVPN" text
- Default SSH username is `root`

### Fixed
- Interactive input now works correctly when running via `curl | bash`
- All `read` commands use `/dev/tty` for terminal input

## [2.1.1] - 2026-03-21

### Fixed
- **CRITICAL**: Fixed interactive input when running via `curl | bash`
  - Changed `read` to `read < /dev/tty` to read from terminal instead of pipe
- Fixed ASCII art banner - now correctly shows "KROTVPN" instead of garbled text

## [2.1.0] - 2026-03-21

### Added
- **Interactive Installer** - one-line installation via curl/wget
  ```bash
  curl -fsSL https://raw.githubusercontent.com/anyagixx/KrotVPN/main/install.sh | bash
  ```
- **HTTPS Support** - self-signed SSL certificates for all services
  - Frontend: https://RU_IP (port 443)
  - Admin Panel: https://RU_IP:8443
  - Backend API: https://RU_IP:8000
- **Nginx SSL Proxy** - new Docker container for SSL termination
- **HTTP to HTTPS redirect** - automatic redirect from HTTP to HTTPS
- **Security headers** - X-Frame-Options, X-Content-Type-Options, X-XSS-Protection
- **Certificate generation** - automatic self-signed certificate generation (10 years validity)
- **New ports**: 443 (frontend HTTPS), 8443 (admin HTTPS)

### Changed
- Updated docker-compose.yml to use nginx as SSL proxy
- All services now behind nginx proxy (not exposed directly)
- Updated deploy-all.sh to generate SSL certificates
- Updated firewall rules to include HTTPS ports

### Security
- All traffic now encrypted via HTTPS
- Self-signed certificates generated automatically
- Certificates persisted in /opt/KrotVPN/ssl/

## [2.0.1] - 2026-03-21

### Fixed
- **CRITICAL**: Fixed deployment scripts dependency order (RU must be deployed before DE)
- Rewrote `deploy-all.sh` - fully automated one-command deployment
- Updated `quick-start.sh` - now calls deploy-all.sh correctly
- Updated `deploy-ru-server.sh` - accepts DE_PUBLIC_KEY via environment variable
- Updated `deploy-de-server.sh` - accepts RU_CLIENT_PUBLIC_KEY via environment variable
- All scripts now work non-interactively when keys are provided via env vars

## [2.0.0] - 2026-03-21

### Added
- Full commercial VPN service platform
- User registration with email and Telegram OAuth
- Subscription system (trial, 1/3/6/12 months)
- YooKassa payment integration
- Referral program (+7 days bonus for referrals)
- Telegram bot for user management
- Admin panel (separate React frontend)
- Split-tunneling (Russian traffic bypass via ipset)
- PWA support for mobile installation
- Internationalization (Russian/English)
- Background tasks scheduler
- Security analysis report
- Auto-deployment scripts for RU/DE servers

### Security
- bcrypt password hashing via passlib
- JWT tokens (15min access + 7days refresh)
- Rate limiting with slowapi
- CORS whitelist configuration
- No hardcoded secrets (all via env vars)
- XSS protection (React auto-escaping)
- Shell injection protection (subprocess_exec)

### Infrastructure
- Docker Compose with 6 services
- PostgreSQL 15 + Redis 7
- AmneziaWG protocol with obfuscation params
- Two-server architecture (RU Entry + DE Exit)
- Health checks for all containers
- Systemd services for VPN routing

## [1.0.0] - 2026-03-20

### Added
- Initial release
- Basic VPN management functionality
- AmneziaWG integration
- Deployment scripts
