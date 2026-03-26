"""
Database module for connection and session management.

GRACE-lite module contract:
- Owns engine/session creation and lightweight compatibility migrations on startup.
- `init_db()` is not a pure bootstrap helper: it can mutate existing schemas/data.
- `get_session()` auto-commits on successful request completion; service code usually flushes, not commits.
- The current project does not rely on a disciplined Alembic migration workflow yet.
"""
# <!-- GRACE: module="M-001" contract="database-connection" -->

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TypeVar

from loguru import logger
from sqlalchemy import bindparam, inspect, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from app.core.config import settings

ModelType = TypeVar("ModelType", bound=SQLModel)

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
    # Use NullPool for SQLite to avoid connection issues
    poolclass=NullPool if "sqlite" in settings.database_url else None,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


def import_all_models() -> None:
    """Import all SQLModel models so relationship targets are registered."""
    import app.billing.models  # noqa: F401
    import app.devices.models  # noqa: F401
    import app.referrals.models  # noqa: F401
    import app.routing.models  # noqa: F401
    import app.users.models  # noqa: F401
    import app.vpn.models  # noqa: F401


async def init_db() -> None:
    """Initialize database tables."""
    import_all_models()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        await migrate_existing_schema(conn)


def _partition_vpn_client_rows(
    rows: list[RowMapping],
) -> tuple[list[RowMapping], list[RowMapping]]:
    """Keep one VPN client row per user and mark the rest as duplicates."""
    keepers: list[RowMapping] = []
    duplicates: list[RowMapping] = []
    seen_user_ids: set[int] = set()

    for row in rows:
        user_id = int(row["user_id"])
        if user_id in seen_user_ids:
            duplicates.append(row)
            continue

        seen_user_ids.add(user_id)
        keepers.append(row)

    return keepers, duplicates


async def migrate_existing_schema(conn) -> None:
    """Apply lightweight compatibility migrations for already deployed databases."""
    # Keep this list additive and defensive. Startup executes it automatically,
    # so any migration bug here affects every application boot.
    await _ensure_subscription_internal_access_columns(conn)
    await _ensure_plan_device_limit_column(conn)
    await _ensure_vpn_client_topology_columns(conn)
    await _ensure_vpn_client_device_columns(conn)
    await _migrate_legacy_vpn_servers_to_nodes(conn)
    await _migrate_legacy_vpn_clients_to_topology(conn)
    await _sync_vpn_topology_client_counts(conn)
    await _deduplicate_vpn_clients(conn)
    await _backfill_primary_user_devices(conn)
    await _relax_vpn_client_user_uniqueness(conn)
    await _ensure_unique_vpn_client_device_id(conn)


async def _deduplicate_vpn_clients(conn) -> None:
    """Collapse duplicate VPN client rows to a single record per user."""
    result = await conn.execute(
        text(
            """
            SELECT id, user_id, server_id, public_key, is_active, created_at, updated_at
            FROM vpn_clients
            ORDER BY
                user_id ASC,
                CASE WHEN is_active THEN 0 ELSE 1 END ASC,
                COALESCE(updated_at, created_at) DESC,
                created_at DESC,
                id DESC
            """
        )
    )
    rows = list(result.mappings())
    if not rows:
        return

    _, duplicates = _partition_vpn_client_rows(rows)
    if not duplicates:
        await _sync_vpn_server_client_counts(conn)
        return

    duplicate_ids = [int(row["id"]) for row in duplicates]
    duplicate_keys = [
        row["public_key"]
        for row in duplicates
        if bool(row["is_active"]) and row["public_key"]
    ]

    if duplicate_keys:
        from app.vpn.amneziawg import wg_manager

        for public_key in duplicate_keys:
            removed = await wg_manager.remove_peer(public_key)
            if not removed:
                logger.warning(
                    f"[DB] Failed to remove duplicate VPN peer during migration: {public_key[:20]}..."
                )

    await conn.execute(
        text("DELETE FROM vpn_clients WHERE id IN :duplicate_ids").bindparams(
            bindparam("duplicate_ids", expanding=True)
        )
        ,
        {"duplicate_ids": duplicate_ids},
    )
    await _sync_vpn_server_client_counts(conn)

    logger.warning(
        f"[DB] Removed {len(duplicate_ids)} duplicate vpn_clients rows during schema migration"
    )


async def _sync_vpn_server_client_counts(conn) -> None:
    """Recalculate vpn_servers.current_clients from the remaining active clients."""
    counts_result = await conn.execute(
        text(
            """
            SELECT server_id, COUNT(*) AS current_clients
            FROM vpn_clients
            WHERE is_active = TRUE
            GROUP BY server_id
            """
        )
    )
    server_counts = {
        int(row["server_id"]): int(row["current_clients"])
        for row in counts_result.mappings()
        if row["server_id"] is not None
    }

    await conn.execute(text("UPDATE vpn_servers SET current_clients = 0"))
    for server_id, current_clients in server_counts.items():
        await conn.execute(
            text(
                """
                UPDATE vpn_servers
                SET current_clients = :current_clients
                WHERE id = :server_id
                """
            ),
            {"server_id": server_id, "current_clients": current_clients},
        )


async def _relax_vpn_client_user_uniqueness(conn) -> None:
    """Remove legacy uniqueness on vpn_clients.user_id so one user can own multiple device-bound peers."""
    has_vpn_clients = await conn.run_sync(_table_exists, "vpn_clients")
    if not has_vpn_clients:
        return

    has_unique_index = await conn.run_sync(_has_unique_vpn_client_user_id)
    if not has_unique_index:
        return

    if conn.dialect.name == "sqlite":
        await _rebuild_vpn_clients_table_for_device_binding(conn)
        logger.info("[DB] Rebuilt vpn_clients for device-bound uniqueness on SQLite")
        return

    descriptors = await conn.run_sync(_get_vpn_client_user_uniqueness_descriptors)
    for index_name in descriptors["indexes"]:
        await conn.execute(text(f'DROP INDEX IF EXISTS "{index_name}"'))
    for constraint_name in descriptors["constraints"]:
        await conn.execute(
            text(f'ALTER TABLE vpn_clients DROP CONSTRAINT IF EXISTS "{constraint_name}"')
        )
    logger.info("[DB] Relaxed vpn_clients.user_id uniqueness for multi-device support")


async def _ensure_unique_vpn_client_device_id(conn) -> None:
    """Ensure vpn_clients.device_id is the stable uniqueness boundary."""
    has_vpn_clients = await conn.run_sync(_table_exists, "vpn_clients")
    if not has_vpn_clients:
        return

    has_unique_index = await conn.run_sync(_has_unique_vpn_client_device_id)
    if has_unique_index:
        return

    await conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ix_vpn_clients_device_id_unique
            ON vpn_clients (device_id)
            """
        )
    )
    logger.info("[DB] Ensured unique index for vpn_clients.device_id")


async def _ensure_vpn_client_topology_columns(conn) -> None:
    """Add nullable topology columns to vpn_clients on already deployed databases."""
    has_vpn_clients = await conn.run_sync(_table_exists, "vpn_clients")
    if not has_vpn_clients:
        return

    for column_name in ("route_id", "entry_node_id", "exit_node_id"):
        has_column = await conn.run_sync(_table_has_column, "vpn_clients", column_name)
        if has_column:
            continue

        await conn.execute(
            text(f"ALTER TABLE vpn_clients ADD COLUMN {column_name} INTEGER")
        )
        await conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS ix_vpn_clients_{column_name} "
                f"ON vpn_clients ({column_name})"
            )
        )
        logger.info(f"[DB] Added vpn_clients.{column_name} compatibility column")


async def _ensure_vpn_client_device_columns(conn) -> None:
    """Add nullable device linkage columns to vpn_clients on already deployed databases."""
    has_vpn_clients = await conn.run_sync(_table_exists, "vpn_clients")
    if not has_vpn_clients:
        return

    if not await conn.run_sync(_table_has_column, "vpn_clients", "device_id"):
        await conn.execute(text("ALTER TABLE vpn_clients ADD COLUMN device_id INTEGER"))
        logger.info("[DB] Added vpn_clients.device_id compatibility column")

    await conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_vpn_clients_device_id
            ON vpn_clients (device_id)
            """
        )
    )


async def _ensure_subscription_internal_access_columns(conn) -> None:
    """Add complimentary-access columns to subscriptions on already deployed databases."""
    has_subscriptions = await conn.run_sync(_table_exists, "subscriptions")
    if not has_subscriptions:
        return

    if not await conn.run_sync(_table_has_column, "subscriptions", "is_complimentary"):
        await conn.execute(
            text("ALTER TABLE subscriptions ADD COLUMN is_complimentary BOOLEAN DEFAULT FALSE")
        )
        logger.info("[DB] Added subscriptions.is_complimentary compatibility column")

    if not await conn.run_sync(_table_has_column, "subscriptions", "access_label"):
        await conn.execute(
            text("ALTER TABLE subscriptions ADD COLUMN access_label VARCHAR(100)")
        )
        logger.info("[DB] Added subscriptions.access_label compatibility column")


async def _ensure_plan_device_limit_column(conn) -> None:
    """Add device_limit to plans on already deployed databases."""
    has_plans = await conn.run_sync(_table_exists, "plans")
    if not has_plans:
        return

    if not await conn.run_sync(_table_has_column, "plans", "device_limit"):
        await conn.execute(
            text("ALTER TABLE plans ADD COLUMN device_limit INTEGER DEFAULT 1")
        )
        logger.info("[DB] Added plans.device_limit compatibility column")


async def _migrate_legacy_vpn_servers_to_nodes(conn) -> None:
    """Mirror deprecated vpn_servers rows into vpn_nodes during the migration window."""
    has_vpn_servers = await conn.run_sync(_table_exists, "vpn_servers")
    has_vpn_nodes = await conn.run_sync(_table_exists, "vpn_nodes")
    if not has_vpn_servers or not has_vpn_nodes:
        return

    result = await conn.execute(
        text(
            """
            SELECT
                id,
                name,
                location,
                endpoint,
                port,
                public_key,
                private_key_enc,
                is_active,
                is_entry_node,
                is_exit_node,
                max_clients,
                current_clients,
                last_ping_at,
                is_online,
                created_at,
                updated_at
            FROM vpn_servers
            ORDER BY id ASC
            """
        )
    )
    rows = list(result.mappings())
    if not rows:
        return

    inserted = 0
    for row in rows:
        existing = await conn.execute(
            text("SELECT id FROM vpn_nodes WHERE public_key = :public_key"),
            {"public_key": row["public_key"]},
        )
        if existing.scalar_one_or_none() is not None:
            continue

        await conn.execute(
            text(
                """
                INSERT INTO vpn_nodes (
                    name,
                    role,
                    country_code,
                    location,
                    endpoint,
                    port,
                    public_key,
                    private_key_enc,
                    is_active,
                    is_online,
                    is_entry_node,
                    is_exit_node,
                    max_clients,
                    current_clients,
                    last_ping_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    :name,
                    :role,
                    :country_code,
                    :location,
                    :endpoint,
                    :port,
                    :public_key,
                    :private_key_enc,
                    :is_active,
                    :is_online,
                    :is_entry_node,
                    :is_exit_node,
                    :max_clients,
                    :current_clients,
                    :last_ping_at,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "name": row["name"],
                "role": _legacy_node_role(
                    bool(row["is_entry_node"]),
                    bool(row["is_exit_node"]),
                ),
                "country_code": _country_code_for_location(str(row["location"])),
                "location": row["location"],
                "endpoint": row["endpoint"],
                "port": row["port"],
                "public_key": row["public_key"],
                "private_key_enc": row["private_key_enc"],
                "is_active": row["is_active"],
                "is_online": row["is_online"],
                "is_entry_node": row["is_entry_node"],
                "is_exit_node": row["is_exit_node"],
                "max_clients": row["max_clients"],
                "current_clients": row["current_clients"],
                "last_ping_at": row["last_ping_at"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )
        inserted += 1

    if inserted:
        logger.info(f"[DB] Mirrored {inserted} legacy vpn_servers rows into vpn_nodes")


async def _migrate_legacy_vpn_clients_to_topology(conn) -> None:
    """Backfill vpn_clients route, entry, and exit columns from legacy server records."""
    has_vpn_clients = await conn.run_sync(_table_exists, "vpn_clients")
    has_vpn_routes = await conn.run_sync(_table_exists, "vpn_routes")
    if not has_vpn_clients or not has_vpn_routes:
        return

    server_map_result = await conn.execute(
        text(
            """
            SELECT vs.id AS server_id, vn.id AS node_id, vs.name AS server_name, vs.max_clients
            FROM vpn_servers vs
            JOIN vpn_nodes vn ON vn.public_key = vs.public_key
            """
        )
    )
    server_map = {
        int(row["server_id"]): {
            "node_id": int(row["node_id"]),
            "server_name": str(row["server_name"]),
            "max_clients": int(row["max_clients"]),
        }
        for row in server_map_result.mappings()
    }
    if not server_map:
        return

    legacy_route_ids: dict[int, int] = {}
    for server_id, server_data in server_map.items():
        route_id = await _ensure_legacy_route(
            conn,
            entry_node_id=server_data["node_id"],
            server_name=server_data["server_name"],
            max_clients=server_data["max_clients"],
        )
        legacy_route_ids[server_id] = route_id

    clients_result = await conn.execute(
        text(
            """
            SELECT id, server_id, route_id, entry_node_id, exit_node_id
            FROM vpn_clients
            ORDER BY id ASC
            """
        )
    )
    updated = 0
    for row in clients_result.mappings():
        if row["server_id"] is None:
            continue
        server_id = int(row["server_id"])
        server_data = server_map.get(server_id)
        if server_data is None:
            continue

        route_id = int(row["route_id"]) if row["route_id"] is not None else legacy_route_ids[server_id]
        entry_node_id = (
            int(row["entry_node_id"])
            if row["entry_node_id"] is not None
            else server_data["node_id"]
        )
        exit_node_id = int(row["exit_node_id"]) if row["exit_node_id"] is not None else None

        if (
            row["route_id"] == route_id
            and row["entry_node_id"] == entry_node_id
            and row["exit_node_id"] == exit_node_id
        ):
            continue

        await conn.execute(
            text(
                """
                UPDATE vpn_clients
                SET route_id = :route_id,
                    entry_node_id = :entry_node_id,
                    exit_node_id = :exit_node_id
                WHERE id = :client_id
                """
            ),
            {
                "client_id": int(row["id"]),
                "route_id": route_id,
                "entry_node_id": entry_node_id,
                "exit_node_id": exit_node_id,
            },
        )
        updated += 1

    if updated:
        logger.info(f"[DB] Backfilled topology fields for {updated} vpn_clients rows")


async def _sync_vpn_topology_client_counts(conn) -> None:
    """Recalculate vpn_nodes and vpn_routes client counters from vpn_clients."""
    has_vpn_clients = await conn.run_sync(_table_exists, "vpn_clients")
    has_vpn_nodes = await conn.run_sync(_table_exists, "vpn_nodes")
    has_vpn_routes = await conn.run_sync(_table_exists, "vpn_routes")
    if not has_vpn_clients:
        return

    if has_vpn_nodes:
        await conn.execute(text("UPDATE vpn_nodes SET current_clients = 0"))

        entry_counts_result = await conn.execute(
            text(
                """
                SELECT entry_node_id, COUNT(*) AS current_clients
                FROM vpn_clients
                WHERE is_active = TRUE AND entry_node_id IS NOT NULL
                GROUP BY entry_node_id
                """
            )
        )
        for row in entry_counts_result.mappings():
            await conn.execute(
                text(
                    """
                    UPDATE vpn_nodes
                    SET current_clients = current_clients + :current_clients
                    WHERE id = :node_id
                    """
                ),
                {
                    "node_id": int(row["entry_node_id"]),
                    "current_clients": int(row["current_clients"]),
                },
            )

        exit_counts_result = await conn.execute(
            text(
                """
                SELECT exit_node_id, COUNT(*) AS current_clients
                FROM vpn_clients
                WHERE is_active = TRUE AND exit_node_id IS NOT NULL
                GROUP BY exit_node_id
                """
            )
        )
        for row in exit_counts_result.mappings():
            await conn.execute(
                text(
                    """
                    UPDATE vpn_nodes
                    SET current_clients = current_clients + :current_clients
                    WHERE id = :node_id
                    """
                ),
                {
                    "node_id": int(row["exit_node_id"]),
                    "current_clients": int(row["current_clients"]),
                },
            )

    if has_vpn_routes:
        await conn.execute(text("UPDATE vpn_routes SET current_clients = 0"))
        route_counts_result = await conn.execute(
            text(
                """
                SELECT route_id, COUNT(*) AS current_clients
                FROM vpn_clients
                WHERE is_active = TRUE AND route_id IS NOT NULL
                GROUP BY route_id
                """
            )
        )
        for row in route_counts_result.mappings():
            await conn.execute(
                text(
                    """
                    UPDATE vpn_routes
                    SET current_clients = :current_clients
                    WHERE id = :route_id
                    """
                ),
                {
                    "route_id": int(row["route_id"]),
                    "current_clients": int(row["current_clients"]),
                },
            )


async def _backfill_primary_user_devices(conn) -> None:
    """Create deterministic primary devices for legacy vpn_clients rows."""
    has_vpn_clients = await conn.run_sync(_table_exists, "vpn_clients")
    has_user_devices = await conn.run_sync(_table_exists, "user_devices")
    has_device_events = await conn.run_sync(_table_exists, "device_security_events")
    if not has_vpn_clients or not has_user_devices:
        return

    result = await conn.execute(
        text(
            """
            SELECT id, user_id, device_id, is_active, created_at, updated_at, last_handshake_at
            FROM vpn_clients
            ORDER BY user_id ASC, id ASC
            """
        )
    )
    rows = list(result.mappings())
    if not rows:
        return

    created_devices = 0
    linked_clients = 0
    recorded_events = 0

    for row in rows:
        client_id = int(row["id"])
        user_id = int(row["user_id"])
        existing_device_id = row["device_id"]
        if existing_device_id is not None:
            device_exists = await conn.execute(
                text("SELECT id FROM user_devices WHERE id = :device_id"),
                {"device_id": int(existing_device_id)},
            )
            if device_exists.scalar_one_or_none() is not None:
                continue

        device_key = _legacy_primary_device_key(user_id)
        existing_device = await conn.execute(
            text(
                """
                SELECT id
                FROM user_devices
                WHERE device_key = :device_key
                """
            ),
            {"device_key": device_key},
        )
        device_id = existing_device.scalar_one_or_none()

        if device_id is None:
            await conn.execute(
                text(
                    """
                    INSERT INTO user_devices (
                        user_id,
                        device_key,
                        name,
                        platform,
                        status,
                        created_at,
                        updated_at,
                        last_seen_at,
                        last_handshake_at,
                        config_version
                    )
                    VALUES (
                        :user_id,
                        :device_key,
                        :name,
                        :platform,
                        :status,
                        :created_at,
                        :updated_at,
                        :last_seen_at,
                        :last_handshake_at,
                        1
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "device_key": device_key,
                    "name": "Primary device",
                    "platform": "legacy-migrated",
                    "status": "active" if bool(row["is_active"]) else "revoked",
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "last_seen_at": row["last_handshake_at"],
                    "last_handshake_at": row["last_handshake_at"],
                },
            )
            inserted_device = await conn.execute(
                text("SELECT id FROM user_devices WHERE device_key = :device_key"),
                {"device_key": device_key},
            )
            device_id = inserted_device.scalar_one()
            created_devices += 1
            logger.info(
                "[VPN][device][VPN_DEVICE_CREATED] "
                f"user_id={user_id} device_id={int(device_id)} device_key={device_key} source=legacy_migration"
            )

            if has_device_events:
                await _record_device_security_event(
                    conn,
                    user_id=user_id,
                    device_id=int(device_id),
                    event_type="migrated_primary_device",
                    severity="info",
                    details_json=f'{{"client_id": {client_id}, "source": "legacy_migration"}}',
                )
                recorded_events += 1

        await conn.execute(
            text(
                """
                UPDATE vpn_clients
                SET device_id = :device_id
                WHERE id = :client_id
                """
            ),
            {"client_id": client_id, "device_id": int(device_id)},
        )
        linked_clients += 1

    if created_devices:
        logger.info(
            "[VPN][device][VPN_DEVICE_AUDIT_RECORDED] "
            f"created_devices={created_devices} linked_clients={linked_clients} events={recorded_events} source=legacy_migration"
        )


async def _ensure_legacy_route(
    conn,
    *,
    entry_node_id: int,
    server_name: str,
    max_clients: int,
) -> int:
    """Create a compatibility route for legacy single-hop server records."""
    route_name = f"Legacy: {server_name}"
    existing = await conn.execute(
        text("SELECT id FROM vpn_routes WHERE name = :name"),
        {"name": route_name},
    )
    route_id = existing.scalar_one_or_none()
    if route_id is not None:
        return int(route_id)

    await conn.execute(
        text(
            """
            INSERT INTO vpn_routes (
                name,
                entry_node_id,
                exit_node_id,
                is_active,
                is_default,
                priority,
                max_clients,
                current_clients,
                created_at,
                updated_at
            )
            VALUES (
                :name,
                :entry_node_id,
                NULL,
                TRUE,
                FALSE,
                1000,
                :max_clients,
                0,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "name": route_name,
            "entry_node_id": entry_node_id,
            "max_clients": max_clients,
        },
    )
    inserted = await conn.execute(
        text("SELECT id FROM vpn_routes WHERE name = :name"),
        {"name": route_name},
    )
    route_id = inserted.scalar_one()
    return int(route_id)


def _has_unique_vpn_client_user_id(sync_conn) -> bool:
    """Check whether vpn_clients.user_id is already uniquely constrained."""
    inspector = inspect(sync_conn)
    if "vpn_clients" not in inspector.get_table_names():
        return False

    for index in inspector.get_indexes("vpn_clients"):
        if index.get("unique") and index.get("column_names") == ["user_id"]:
            return True

    for constraint in inspector.get_unique_constraints("vpn_clients"):
        if constraint.get("column_names") == ["user_id"]:
            return True

    return False


def _has_unique_vpn_client_device_id(sync_conn) -> bool:
    """Check whether vpn_clients.device_id is already uniquely constrained."""
    inspector = inspect(sync_conn)
    if "vpn_clients" not in inspector.get_table_names():
        return False

    for index in inspector.get_indexes("vpn_clients"):
        if index.get("unique") and index.get("column_names") == ["device_id"]:
            return True

    for constraint in inspector.get_unique_constraints("vpn_clients"):
        if constraint.get("column_names") == ["device_id"]:
            return True

    return False


def _get_vpn_client_user_uniqueness_descriptors(sync_conn) -> dict[str, list[str]]:
    """Return unique indexes and constraints that enforce vpn_clients.user_id uniqueness."""
    inspector = inspect(sync_conn)
    indexes: list[str] = []
    constraints: list[str] = []
    if "vpn_clients" not in inspector.get_table_names():
        return {"indexes": indexes, "constraints": constraints}

    for index in inspector.get_indexes("vpn_clients"):
        if index.get("unique") and index.get("column_names") == ["user_id"]:
            name = index.get("name")
            if name:
                indexes.append(name)

    for constraint in inspector.get_unique_constraints("vpn_clients"):
        if constraint.get("column_names") == ["user_id"]:
            name = constraint.get("name")
            if name:
                constraints.append(name)

    return {"indexes": indexes, "constraints": constraints}


async def _rebuild_vpn_clients_table_for_device_binding(conn) -> None:
    """Rebuild vpn_clients on SQLite without user uniqueness and with device uniqueness."""
    await conn.execute(text("DROP TABLE IF EXISTS vpn_clients__new"))
    await conn.execute(
        text(
            """
            CREATE TABLE vpn_clients__new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                device_id INTEGER,
                server_id INTEGER,
                route_id INTEGER,
                entry_node_id INTEGER,
                exit_node_id INTEGER,
                public_key VARCHAR(100) NOT NULL UNIQUE,
                private_key_enc VARCHAR(500) NOT NULL,
                address VARCHAR(20) NOT NULL UNIQUE,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                total_upload_bytes INTEGER NOT NULL DEFAULT 0,
                total_download_bytes INTEGER NOT NULL DEFAULT 0,
                last_handshake_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users (id),
                FOREIGN KEY(device_id) REFERENCES user_devices (id),
                FOREIGN KEY(server_id) REFERENCES vpn_servers (id),
                FOREIGN KEY(route_id) REFERENCES vpn_routes (id),
                FOREIGN KEY(entry_node_id) REFERENCES vpn_nodes (id),
                FOREIGN KEY(exit_node_id) REFERENCES vpn_nodes (id)
            )
            """
        )
    )
    await conn.execute(
        text(
            """
            INSERT INTO vpn_clients__new (
                id,
                user_id,
                device_id,
                server_id,
                route_id,
                entry_node_id,
                exit_node_id,
                public_key,
                private_key_enc,
                address,
                is_active,
                total_upload_bytes,
                total_download_bytes,
                last_handshake_at,
                created_at,
                updated_at
            )
            SELECT
                id,
                user_id,
                device_id,
                server_id,
                route_id,
                entry_node_id,
                exit_node_id,
                public_key,
                private_key_enc,
                address,
                is_active,
                total_upload_bytes,
                total_download_bytes,
                last_handshake_at,
                created_at,
                updated_at
            FROM vpn_clients
            """
        )
    )
    await conn.execute(text("DROP TABLE vpn_clients"))
    await conn.execute(text("ALTER TABLE vpn_clients__new RENAME TO vpn_clients"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vpn_clients_user_id ON vpn_clients (user_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vpn_clients_device_id ON vpn_clients (device_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vpn_clients_server_id ON vpn_clients (server_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vpn_clients_route_id ON vpn_clients (route_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vpn_clients_entry_node_id ON vpn_clients (entry_node_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vpn_clients_exit_node_id ON vpn_clients (exit_node_id)"))
    await conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ix_vpn_clients_device_id_unique
            ON vpn_clients (device_id)
            """
        )
    )


def _table_exists(sync_conn, table_name: str) -> bool:
    """Check whether a table already exists."""
    inspector = inspect(sync_conn)
    return table_name in inspector.get_table_names()


def _table_has_column(sync_conn, table_name: str, column_name: str) -> bool:
    """Check whether a table contains the requested column."""
    inspector = inspect(sync_conn)
    if table_name not in inspector.get_table_names():
        return False

    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _legacy_node_role(is_entry_node: bool, is_exit_node: bool) -> str:
    """Convert legacy booleans to the new stable node role string."""
    if is_entry_node and is_exit_node:
        return "combined"
    if is_exit_node:
        return "exit"
    return "entry"


def _country_code_for_location(location: str) -> str:
    """Best-effort country code inference for legacy location strings."""
    normalized = location.strip().lower()
    mapping = {
        "russia": "RU",
        "russian": "RU",
        "germany": "DE",
        "deutschland": "DE",
        "netherlands": "NL",
        "holland": "NL",
        "finland": "FI",
        "france": "FR",
        "poland": "PL",
    }
    for needle, country_code in mapping.items():
        if needle in normalized:
            return country_code
    return "ZZ"


def _legacy_primary_device_key(user_id: int) -> str:
    """Build a deterministic device key for migrated legacy users."""
    return f"legacy-user-{user_id}-primary"


async def _record_device_security_event(
    conn,
    *,
    user_id: int,
    device_id: int,
    event_type: str,
    severity: str,
    details_json: str,
) -> None:
    """Insert a durable device security event during compatibility migration."""
    await conn.execute(
        text(
            """
            INSERT INTO device_security_events (
                user_id,
                device_id,
                event_type,
                severity,
                details_json,
                created_at
            )
            VALUES (
                :user_id,
                :device_id,
                :event_type,
                :severity,
                :details_json,
                CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "user_id": user_id,
            "device_id": device_id,
            "event_type": event_type,
            "severity": severity,
            "details_json": details_json,
        },
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions (for use outside FastAPI)."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_by_id(session: AsyncSession, model: type[ModelType], id: int) -> ModelType | None:
    """Get a model instance by ID."""
    return await session.get(model, id)
