# Changelog

All notable changes to this project will be documented in this file.

## [2.3.0] - 2026-03-22

### Fixed
- **CRITICAL**: Fixed VPN tunnel not working between RU and DE servers
  - Fixed DE firewall: no longer overwrites /etc/ufw/before.rules (was breaking UFW)
  - Added explicit route to 10.200.0.0/24 via awg-client (Table=off does not add it)
  - Added verification that DE AmneziaWG is actually running
  - Added retry logic for tunnel test (5 attempts with 2s delay)
  - Added extensive debugging output if tunnel fails

### Changed
- DE firewall now uses iptables directly instead of modifying UFW before.rules
- Added rc.local to restore iptables rules on boot on DE server
- More verbose output during deployment for easier debugging


## [2.2.1] - 2026-03-22

### Fixed
- **CRITICAL**: Fixed frontend-admin build failure - missing lib/api.ts
  - Added exception `!**/src/lib/` to .gitignore
  - Force-added frontend/src/lib/api.ts and frontend-admin/src/lib/api.ts
  - These were incorrectly ignored by the `lib/` pattern (meant for Python lib/)


## [2.2.0] - 2026-03-22

### Fixed
- **CRITICAL**: Fixed Docker build failure - nginx.conf files now included in repository
  - Added exception `!**/nginx.conf` to .gitignore
  - Force-added nginx/nginx.conf, frontend/nginx.conf, frontend-admin/nginx.conf

### Note
- Tunnel test may fail initially - this is expected if DE server needs manual verification
- Docker containers will start regardless of tunnel status


## [2.1.9] - 2026-03-22

### Fixed
- **CRITICAL**: Fixed route conflict error "RTNETLINK answers: File exists"
  - Added `Table = off` to awg-client.conf to prevent automatic route creation
  - Removed DNS directive from awg-client.conf (not needed for server-to-server tunnel)
  - All routing is now handled by setup_routing.sh script


## [2.1.8] - 2026-03-22

### Fixed
- **CRITICAL**: Fixed SSH connection hang during VPN tunnel setup
  - Added explicit route to DE server via main gateway before starting VPN
  - Changed AllowedIPs from 0.0.0.0/0 to 10.10.0.0/24 in awg-client.conf
  - This prevents awg-quick from setting up aggressive routing rules
  - SSH connections now stay alive during VPN initialization

### Changed
- Split-tunneling routing is now handled entirely by setup_routing.sh
- VPN client interface no longer captures all traffic by default


## [2.1.7] - 2026-03-21

### Fixed
- **CRITICAL**: Fixed sshpass not being installed before DE connection test
- sshpass is now installed IMMEDIATELY after decoding passwords
- Connection test to DE server now works correctly

### Changed
- Reordered initialization: install sshpass before testing DE connection
- Better error messages

## [2.1.6] - 2026-03-21

### Fixed
- **CRITICAL**: Fixed password handling with special characters
  - Passwords are now base64 encoded before transmission
  - Works with ANY characters ($, !, &, ', ", etc.)

## [2.1.5] - 2026-03-21

### Fixed
- **CRITICAL**: Fixed IPv6 detection - now forces IPv4
- **CRITICAL**: Fixed password passing - now uses config file

## [2.1.4] - 2026-03-21

### Fixed
- **CRITICAL**: Fixed deployment - created deploy-on-server.sh

## [2.1.0] - 2026-03-21

### Added
- Interactive Installer - one-line installation via curl/wget
- HTTPS Support - self-signed SSL certificates

## [2.0.0] - 2026-03-21

### Added
- Full commercial VPN service platform
- Subscription system
- YooKassa payment integration
- Telegram bot
- Admin panel
- Split-tunneling

## [1.0.0] - 2026-03-20

### Added
- Initial release
