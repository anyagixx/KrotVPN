"""
VPN models for server and client configuration.

CHANGE_SUMMARY
- 2026-03-27: Added nullable device linkage so legacy one-client-per-user records can migrate toward explicit device-bound peers.
- 2026-03-27: Moved the stable uniqueness boundary from user_id to device_id for multi-device support.
"""
# <!-- GRACE: module="M-003" entity="VPNServer, VPNNode, VPNRoute, VPNClient" -->

from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.devices.models import UserDevice
    from app.users.models import User


class VPNServer(SQLModel, table=True):
    """Deprecated legacy mirror of an entry-capable node."""
    
    __tablename__ = "vpn_servers"
    
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    location: str = Field(max_length=100)  # e.g., "Germany", "Netherlands"
    endpoint: str = Field(max_length=255)  # IP or hostname
    port: int = Field(default=51821)
    
    # Server keys (private key encrypted)
    public_key: str = Field(max_length=100, unique=True)
    private_key_enc: str | None = Field(default=None, max_length=500)  # Encrypted
    
    # Network configuration
    subnet: str = Field(default="10.10.0.0/24")
    
    # Status
    is_active: bool = Field(default=True)
    is_entry_node: bool = Field(default=False)  # RU server = entry node
    is_exit_node: bool = Field(default=True)  # DE server = exit node
    
    # Capacity
    max_clients: int = Field(default=100)
    current_clients: int = Field(default=0)
    
    # Monitoring
    last_ping_at: datetime | None = Field(default=None)
    is_online: bool = Field(default=True)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    clients: list["VPNClient"] = Relationship(back_populates="server")


class VPNNode(SQLModel, table=True):
    """Physical VPN node used as an entry, exit, or combined hop."""

    __tablename__ = "vpn_nodes"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    role: str = Field(default="entry", max_length=20)
    country_code: str = Field(default="ZZ", max_length=2)
    location: str = Field(max_length=100)
    endpoint: str = Field(max_length=255)
    port: int = Field(default=51821)

    public_key: str = Field(max_length=100, unique=True)
    private_key_enc: str | None = Field(default=None, max_length=500)

    is_active: bool = Field(default=True)
    is_online: bool = Field(default=True)
    is_entry_node: bool = Field(default=False)
    is_exit_node: bool = Field(default=False)

    max_clients: int = Field(default=100)
    current_clients: int = Field(default=0)
    last_ping_at: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class VPNRoute(SQLModel, table=True):
    """Logical path that connects an entry node to an exit node."""

    __tablename__ = "vpn_routes"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, unique=True)
    entry_node_id: int = Field(foreign_key="vpn_nodes.id", index=True)
    # Exit node stays nullable during the migration from the legacy single-hop model.
    exit_node_id: int | None = Field(default=None, foreign_key="vpn_nodes.id", index=True)

    is_active: bool = Field(default=True)
    is_default: bool = Field(default=False)
    priority: int = Field(default=100)
    max_clients: int = Field(default=100)
    current_clients: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class VPNClient(SQLModel, table=True):
    """VPN client configuration for a user."""
    
    __tablename__ = "vpn_clients"
    
    id: int | None = Field(default=None, primary_key=True)
    # User linkage remains for compatibility queries, but uniqueness now belongs
    # to the logical device so one user can own multiple device-bound peers.
    user_id: int = Field(foreign_key="users.id", index=True)
    device_id: int | None = Field(default=None, foreign_key="user_devices.id", index=True, unique=True)
    # Legacy compatibility field. New runtime logic should prefer route/entry/exit
    # topology and treat server_id only as a mirror for rollback paths.
    server_id: int | None = Field(default=None, foreign_key="vpn_servers.id", index=True)
    route_id: int | None = Field(default=None, foreign_key="vpn_routes.id", index=True)
    entry_node_id: int | None = Field(default=None, foreign_key="vpn_nodes.id", index=True)
    exit_node_id: int | None = Field(default=None, foreign_key="vpn_nodes.id", index=True)
    
    # Client keys (private key encrypted)
    public_key: str = Field(max_length=100, unique=True)
    private_key_enc: str = Field(max_length=500)  # Encrypted with Fernet
    
    # Network configuration
    address: str = Field(max_length=20, unique=True)  # e.g., 10.10.0.2
    
    # Status
    is_active: bool = Field(default=True)
    
    # Statistics
    total_upload_bytes: int = Field(default=0)
    total_download_bytes: int = Field(default=0)
    last_handshake_at: datetime | None = Field(default=None)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    user: "User" = Relationship(back_populates="vpn_clients")
    device: "UserDevice" = Relationship(back_populates="vpn_clients")
    server: VPNServer | None = Relationship(back_populates="clients")


class VPNConfig(SQLModel):
    """Generated VPN configuration for client download."""
    config: str
    server_name: str
    server_location: str
    route_name: str | None = None
    entry_server_name: str | None = None
    entry_server_location: str | None = None
    exit_server_name: str | None = None
    exit_server_location: str | None = None
    address: str
    public_key: str
    created_at: datetime


class VPNStats(SQLModel):
    """VPN usage statistics."""
    total_upload_bytes: int
    total_download_bytes: int
    last_handshake_at: datetime | None
    is_connected: bool
    server_name: str
    server_location: str


class ServerStatus(SQLModel):
    """Deprecated legacy server status shape kept for compatibility."""
    id: int
    name: str
    location: str
    is_online: bool
    current_clients: int
    max_clients: int
    load_percent: float
