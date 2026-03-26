#!/usr/bin/env python3
"""
KrotVPN CLI tools for administration.

Usage:
    python -m app.cli create-admin --email admin@example.com --password secret
    python -m app.cli create-admin --email admin@example.com --password secret --superadmin
    python -m app.cli reset-password --email admin@example.com --password newsecret
    python -m app.cli list-admins
    python -m app.cli check-config
    python -m app.cli create-internal-client --identity family-phone --output /tmp/family-phone.conf

CHANGE_SUMMARY
- 2026-03-26: Added backend CLI command for internal non-billable client issuance through the normal VPN provisioning path.
"""
# <!-- GRACE: module="M-007" contract="cli-tools" -->

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger
from sqlalchemy import select

from app.billing.service import BillingService
from app.core.config import settings
from app.core.database import async_session_maker, init_db
from app.core.init_admin import create_admin_user, reset_admin_password
from app.users.models import User, UserRole
from app.users.service import UserService
from app.vpn.service import VPNService


def print_success(msg: str) -> None:
    print(f"\033[92m✓ {msg}\033[0m")


def print_error(msg: str) -> None:
    print(f"\033[91m✗ {msg}\033[0m")


def print_info(msg: str) -> None:
    print(f"\033[94mℹ {msg}\033[0m")


def print_warning(msg: str) -> None:
    print(f"\033[93m⚠ {msg}\033[0m")


async def cmd_create_admin(
    email: str,
    password: str,
    name: str = "Administrator",
    superadmin: bool = False,
) -> int:
    """Create a new admin user."""
    try:
        await init_db()
        async with async_session_maker() as session:
            user = await create_admin_user(
                session=session,
                email=email,
                password=password,
                name=name,
                superadmin=superadmin,
            )
            await session.commit()
            
        role_str = "superadmin" if superadmin else "admin"
        print_success(f"Created {role_str} user: {user.email} (ID: {user.id})")
        return 0
        
    except ValueError as e:
        print_error(str(e))
        return 1
    except Exception as e:
        print_error(f"Failed to create admin: {e}")
        return 1


async def cmd_reset_password(email: str, password: str) -> int:
    """Reset password for an admin user."""
    try:
        await init_db()
        async with async_session_maker() as session:
            user = await reset_admin_password(
                session=session,
                email=email,
                password=password,
            )
            await session.commit()
            
        print_success(f"Password reset for: {user.email}")
        return 0
        
    except ValueError as e:
        print_error(str(e))
        return 1
    except Exception as e:
        print_error(f"Failed to reset password: {e}")
        return 1


async def cmd_list_admins() -> int:
    """List all admin users."""
    try:
        await init_db()
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(
                    User.role.in_([UserRole.ADMIN, UserRole.SUPERADMIN])
                ).order_by(User.created_at)
            )
            admins = result.scalars().all()
            
        if not admins:
            print_info("No admin users found")
            return 0
            
        print(f"\n{'ID':<6} {'Email':<35} {'Role':<12} {'Active':<8} {'Created'}")
        print("-" * 80)
        
        for admin in admins:
            print(
                f"{admin.id:<6} {admin.email:<35} {admin.role.value:<12} "
                f"{'✓' if admin.is_active else '✗':<8} {admin.created_at.strftime('%Y-%m-%d %H:%M')}"
            )
        
        print(f"\nTotal: {len(admins)} admin user(s)")
        return 0
        
    except Exception as e:
        print_error(f"Failed to list admins: {e}")
        return 1


async def cmd_check_config() -> int:
    """Check admin configuration."""
    print("\n" + "=" * 50)
    print("KrotVPN Admin Configuration Check")
    print("=" * 50 + "\n")
    
    issues = []
    
    # Check ADMIN_EMAIL
    if settings.admin_email:
        print_success(f"ADMIN_EMAIL: {settings.admin_email}")
    else:
        print_warning("ADMIN_EMAIL: Not configured")
        issues.append("ADMIN_EMAIL is not set")
    
    # Check ADMIN_PASSWORD
    if settings.admin_password:
        # Check for default passwords
        password_lower = settings.admin_password.lower()
        default_patterns = ["changeme", "admin", "password", "123456"]
        is_default = any(p in password_lower for p in default_patterns)
        
        if is_default:
            print_warning("ADMIN_PASSWORD: Using default/weak password!")
            issues.append("ADMIN_PASSWORD appears to be a default value")
        else:
            print_success("ADMIN_PASSWORD: Configured")
    else:
        print_warning("ADMIN_PASSWORD: Not configured")
        issues.append("ADMIN_PASSWORD is not set")
    
    # Check database connection
    try:
        await init_db()
        async with async_session_maker() as session:
            result = await session.execute(select(User).limit(1))
            result.scalar_one_or_none()
        print_success("Database: Connected")
    except Exception as e:
        print_error(f"Database: Connection failed - {e}")
        issues.append(f"Database connection failed: {e}")
    
    # Check if admin exists
    try:
        async with async_session_maker() as session:
            result = await session.execute(
                select(User).where(
                    User.role.in_([UserRole.ADMIN, UserRole.SUPERADMIN])
                )
            )
            admins = result.scalars().all()
            
        if admins:
            print_success(f"Admin users: {len(admins)} found")
        else:
            print_warning("Admin users: None found")
            if settings.admin_email and settings.admin_password:
                print_info("Admin will be created automatically on next startup")
    except Exception:
        pass  # Already reported above
    
    print("\n" + "=" * 50)
    
    if issues:
        print_warning(f"Found {len(issues)} issue(s):")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    else:
        print_success("All checks passed!")
        return 0


async def issue_internal_client(
    identity: str,
    *,
    output: str | None = None,
    display_name: str | None = None,
    access_label: str = "internal-unlimited",
    reprovision: bool = False,
):
    """Resolve internal access and export a VPN config through backend services."""
    logger.info(
        "[VPN][manual][VPN_MANUAL_CLIENT_REQUESTED] "
        f"internal_identity={identity} access_label={access_label} reprovision={reprovision}"
    )

    async with async_session_maker() as session:
        user_service = UserService(session)
        billing_service = BillingService(session)
        vpn_service = VPNService(session)

        user = await user_service.resolve_internal_user(
            identity,
            display_name=display_name,
        )
        subscription = await billing_service.ensure_complimentary_access(
            user.id,
            access_label=access_label,
        )
        client = await vpn_service.provision_internal_client(
            user.id,
            reprovision=reprovision,
        )
        config = await vpn_service.get_client_config(client)
        await session.commit()

    logger.info(
        "[VPN][manual][VPN_MANUAL_CLIENT_PROVISIONED] "
        f"internal_identity={identity} user_id={user.id} client_id={client.id} "
        f"subscription_id={subscription.id} reprovision={reprovision}"
    )
    return user, subscription, client, config


async def cmd_create_internal_client(
    identity: str,
    *,
    output: str | None = None,
    display_name: str | None = None,
    access_label: str = "internal-unlimited",
    reprovision: bool = False,
) -> int:
    """Create or reuse an internal user and export a working VPN config."""
    try:
        await init_db()
        user, subscription, client, config = await issue_internal_client(
            identity,
            output=output,
            display_name=display_name,
            access_label=access_label,
            reprovision=reprovision,
        )

        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(config.config, encoding="utf-8")
            logger.info(
                "[VPN][manual][VPN_MANUAL_CLIENT_OUTPUT_WRITTEN] "
                f"internal_identity={identity} user_id={user.id} client_id={client.id} "
                f"subscription_id={subscription.id} output_path={output_path} reprovision={reprovision}"
            )
            print_success(f"Internal client config saved: {output_path}")
            print_info(
                f"user_id={user.id} subscription_id={subscription.id} "
                f"client_id={client.id} address={config.address}"
            )
        else:
            sys.stdout.write(config.config)
            if not config.config.endswith("\n"):
                sys.stdout.write("\n")
            logger.info(
                "[VPN][manual][VPN_MANUAL_CLIENT_OUTPUT_WRITTEN] "
                f"internal_identity={identity} user_id={user.id} client_id={client.id} "
                f"subscription_id={subscription.id} output_path=stdout reprovision={reprovision}"
            )

        return 0
    except ValueError as e:
        print_error(str(e))
        return 1
    except Exception as e:
        print_error(f"Failed to create internal client: {e}")
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="krotvpn-cli",
        description="KrotVPN administration CLI tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.cli create-admin --email admin@example.com --password secret
  python -m app.cli create-admin --email super@example.com --password secret --superadmin
  python -m app.cli reset-password --email admin@example.com --password newsecret
  python -m app.cli list-admins
  python -m app.cli check-config
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # create-admin command
    create_parser = subparsers.add_parser(
        "create-admin",
        help="Create a new admin user",
    )
    create_parser.add_argument(
        "--email", "-e",
        required=True,
        help="Admin email address",
    )
    create_parser.add_argument(
        "--password", "-p",
        required=True,
        help="Admin password",
    )
    create_parser.add_argument(
        "--name", "-n",
        default="Administrator",
        help="Admin display name (default: Administrator)",
    )
    create_parser.add_argument(
        "--superadmin", "-s",
        action="store_true",
        help="Create as superadmin instead of admin",
    )
    
    # reset-password command
    reset_parser = subparsers.add_parser(
        "reset-password",
        help="Reset password for an admin user",
    )
    reset_parser.add_argument(
        "--email", "-e",
        required=True,
        help="Admin email address",
    )
    reset_parser.add_argument(
        "--password", "-p",
        required=True,
        help="New password",
    )
    
    # list-admins command
    subparsers.add_parser(
        "list-admins",
        help="List all admin users",
    )
    
    # check-config command
    subparsers.add_parser(
        "check-config",
        help="Check admin configuration",
    )

    internal_client_parser = subparsers.add_parser(
        "create-internal-client",
        help="Create or reuse an internal complimentary VPN client",
    )
    internal_client_parser.add_argument(
        "--identity", "-i",
        required=True,
        help="Stable identity for the internal client, e.g. family-phone",
    )
    internal_client_parser.add_argument(
        "--display-name", "-n",
        default=None,
        help="Optional display name for the internal user",
    )
    internal_client_parser.add_argument(
        "--access-label", "-l",
        default="internal-unlimited",
        help="Explicit complimentary access label",
    )
    internal_client_parser.add_argument(
        "--output", "-o",
        default=None,
        help="Optional path where the rendered config will be written",
    )
    internal_client_parser.add_argument(
        "--reprovision", "-r",
        action="store_true",
        help="Force key and peer reprovision instead of reusing an existing active client",
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Run the appropriate command
    if args.command == "create-admin":
        return asyncio.run(cmd_create_admin(
            email=args.email,
            password=args.password,
            name=args.name,
            superadmin=args.superadmin,
        ))
    elif args.command == "reset-password":
        return asyncio.run(cmd_reset_password(
            email=args.email,
            password=args.password,
        ))
    elif args.command == "list-admins":
        return asyncio.run(cmd_list_admins())
    elif args.command == "check-config":
        return asyncio.run(cmd_check_config())
    elif args.command == "create-internal-client":
        return asyncio.run(cmd_create_internal_client(
            identity=args.identity,
            output=args.output,
            display_name=args.display_name,
            access_label=args.access_label,
            reprovision=args.reprovision,
        ))

    return 0


if __name__ == "__main__":
    sys.exit(main())
