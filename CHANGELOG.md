# Changelog

All notable changes to this project will be documented in this file.

## [2.1.6] - 2026-03-21

### Fixed
- **CRITICAL**: Fixed password handling with special characters
  - Passwords are now base64 encoded before transmission
  - Decoded on server side - works with ANY characters ($, !, &, ', ", etc.)
- Improved password input (shows asterisks while typing)
- Better error handling and validation

### Changed
- install.sh: Base64 encodes passwords before creating config
- deploy-on-server.sh: Decodes base64 passwords from config
- Added password masking during input (shows *****)

### Architecture
```
install.sh (laptop)
    │
    ├─► Encode passwords: base64
    │
    └─► Creates /tmp/krotvpn_deploy.conf
        DE_PASS_B64='base64_encoded_password'
        RU_PASS_B64='base64_encoded_password'
            │
            └─► deploy-on-server.sh decodes
                DE_PASS=$(echo "$DE_PASS_B64" | base64 -d)
```

## [2.1.5] - 2026-03-21

### Fixed
- **CRITICAL**: Fixed IPv6 detection - now forces IPv4 with multiple fallbacks
- Added connection testing before deployment starts

## [2.1.4] - 2026-03-21

### Fixed
- **CRITICAL**: Fixed deployment - created deploy-on-server.sh

## [2.1.3] - 2026-03-21

### Changed
- **MAJOR**: Complete rewrite - now deploys directly to servers via SSH

## [2.1.2] - 202.1-21

### Changed
- **MAJOR**: Simplified installation - now uses SSH password authentication

## [2.1.0] - 2026-03-21

### Added
- **Interactive Installer** - one-line installation via curl/wget
- **HTTPS Support** - self-signed SSL certificates for all services

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

## [1.0.0] - 2026-03-20

### Added
- Initial release
