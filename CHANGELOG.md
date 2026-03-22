# Changelog

All notable changes to this project will be documented in this file.

## [2.4.14] - 2026-03-22

### Improved
- Improved product UX across the user frontend for no-subscription, no-config, empty referral history, and API error states
- Added clearer fallback messaging and action paths on dashboard, config, subscription, and referrals screens
- Tightened frontend API typing for subscription and referral flows to support more reliable UI states

## [2.4.13] - 2026-03-22

### Improved
- Unified the visual language of the user frontend and admin panel into one premium product style
- Aligned admin layout, dashboard wording, server load states, and login experience with the redesigned main frontend
- Polished cross-product consistency for surfaces, spacing, controls, and interaction states

## [2.4.12] - 2026-03-22

### Improved
- Fully redesigned the user frontend with a premium visual direction, cleaner hierarchy, and unified layout system
- Reworked login, registration, dashboard, VPN config, subscription, referrals, and settings screens
- Added stronger loading, action, and content states across the user cabinet while keeping API behavior intact

## [2.4.11] - 2026-03-22

### Improved
- Reworked the admin panel frontend with a stronger visual layout, clearer navigation, and more readable dashboard hierarchy
- Redesigned admin login, users, servers, plans, analytics, and settings screens for real operational use
- Replaced misleading placeholder admin forms with honest UI states that match current backend capabilities

## [2.4.10] - 2026-03-22

### Fixed
- Fixed PostgreSQL datetime errors caused by mixing timezone-aware and timezone-naive values
- Standardized database-facing timestamps to naive UTC for services working with SQLModel/PostgreSQL

## [2.4.9] - 2026-03-22

### Fixed
- Fixed runtime ORM mapper errors by importing all SQLModel model modules before database initialization
- Ensured relationship targets like `VPNClient` and referral models are registered before first query

## [2.4.8] - 2026-03-22

### Fixed
- Fixed backend startup failure caused by bcrypt backend limitations during admin password hashing
- Switched password hashing to `pbkdf2_sha256` to avoid bcrypt runtime failures in Docker

## [2.4.7] - 2026-03-22

### Fixed
- Fixed backend startup failure during admin bootstrap when password hashing hit bcrypt's 72-byte limit
- Switched password hashing to `bcrypt_sha256` for safer handling of long passwords

## [2.4.6] - 2026-03-22

### Fixed
- Fixed backend startup failure caused by unsupported union-style relationship type hints in `User` ORM model
- Adjusted referral relationships to explicit one-to-one SQLModel configuration

## [2.4.5] - 2026-03-22

### Fixed
- Fixed backend startup failure when file logging directory is not writable inside Docker
- Backend now falls back gracefully instead of crashing on log file permission errors

## [2.4.4] - 2026-03-22

### Fixed
- Fixed backend startup failure caused by importing billing response models from the wrong module
- Restored billing router import resolution for `PlanResponse`, `PaymentResponse`, and `SubscriptionResponse`

## [2.4.3] - 2026-03-22

### Fixed
- Fixed backend startup failure caused by reserved SQLAlchemy attribute name `metadata` in `Payment`
- Renamed payment metadata storage field to avoid ORM initialization crash

## [2.4.2] - 2026-03-22

### Fixed
- Fixed backend startup failure caused by a circular import through `app.users.__init__`
- Restored API availability for admin login and all frontend requests proxied to backend

## [2.4.1] - 2026-03-22

### Fixed
- Fixed backend startup crash caused by missing `SQLModel` import in user schemas
- Fixed admin panel login flow to work with token-based `/api/auth/login`
- Fixed VPN stats endpoint fallback response for users without a VPN client
- Fixed billing model mismatches around `plan_id` for trial subscriptions and payments
- Fixed user frontend auth state after login and registration
- Fixed referral and admin frontend pages to match actual backend API responses
- Fixed default admin credentials drift between `.env.example` and deploy scripts

### Changed
- New user registration now initializes trial subscriptions and referral records consistently
- Successful first payment now triggers referral bonus processing

### Verification
- Python backend and bot modules compile successfully with `py_compile`
- User frontend production build passes successfully

## [2.4.0] - 2026-03-22

### Added
- **Automatic Admin User Initialization**
  - Admin user is now automatically created from `ADMIN_EMAIL` and `ADMIN_PASSWORD` environment variables
  - Works on first startup - no manual database operations needed
  - Security warning if default password is detected

- **CLI Administration Tools** (`python -m app.cli`)
  - `create-admin` - Create new admin user from command line
  - `reset-password` - Reset admin password
  - `list-admins` - List all admin users
  - `check-config` - Validate admin configuration

### Fixed
- **CRITICAL**: Fixed admin login not working after installation
  - Previously, `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` were ignored
  - Admin user is now properly created on first application startup

### Security
- Added warning when default/weak admin password is detected
- Password patterns like "changeme", "admin", "password" trigger security warning

### Usage
After installation, login to Admin Panel (`https://YOUR_IP:8443`) with:
- **Email**: `admin@krotvpn.com` (or your custom `ADMIN_EMAIL`)
- **Password**: `ChangeMeImmediately123!` (or your custom `ADMIN_PASSWORD`)

⚠️ **Important**: Change the default password immediately after first login!

### CLI Examples
```bash
# Create additional admin
docker exec -it krotvpn-backend python -m app.cli create-admin -e admin2@example.com -p secret123

# Reset admin password
docker exec -it krotvpn-backend python -m app.cli reset-password -e admin@krotvpn.com -p newsecret

# List all admins
docker exec -it krotvpn-backend python -m app.cli list-admins

# Check configuration
docker exec -it krotvpn-backend python -m app.cli check-config
```


## [2.3.1] - 2026-03-22

### Fixed
- Fixed TypeScript build errors in frontend
  - Login.tsx: removed unused setUser and userData variables
  - Register.tsx: removed unused User import
  - Settings.tsx: fixed useMutation type annotations


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
