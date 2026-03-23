"""
VPN schemas for API requests and responses.
"""
# <!-- GRACE: module="M-003" contract="vpn-schemas" -->

from datetime import datetime

from pydantic import Field

from sqlmodel import SQLModel


class VPNConfigResponse(SQLModel):
    """VPN configuration response."""
    config: str
    server_name: str
    server_location: str
    route_name: str | None = None
    entry_server_name: str | None = None
    entry_server_location: str | None = None
    exit_server_name: str | None = None
    exit_server_location: str | None = None
    address: str
    created_at: datetime


class VPNStatsResponse(SQLModel):
    """VPN statistics response."""
    total_upload_bytes: int = 0
    total_download_bytes: int = 0
    total_upload_formatted: str = "0 B"
    total_download_formatted: str = "0 B"
    last_handshake_at: datetime | None = None
    is_connected: bool = False
    server_name: str
    server_location: str


class ServerStatusResponse(SQLModel):
    """Server status response."""
    id: int
    name: str
    location: str
    is_online: bool
    current_clients: int
    max_clients: int
    load_percent: float


class ServerListResponse(SQLModel):
    """List of servers."""
    servers: list[ServerStatusResponse]


class NodeStatusResponse(SQLModel):
    """VPN node status response."""
    id: int
    name: str
    role: str
    country_code: str
    location: str
    endpoint: str
    port: int
    public_key: str
    is_active: bool
    is_online: bool
    is_entry_node: bool
    is_exit_node: bool
    current_clients: int
    max_clients: int
    load_percent: float


class NodeListResponse(SQLModel):
    """List of VPN nodes."""
    nodes: list[NodeStatusResponse]


class RouteStatusResponse(SQLModel):
    """VPN route status response."""
    id: int
    name: str
    entry_node_id: int
    entry_node_name: str
    entry_node_location: str
    exit_node_id: int | None = None
    exit_node_name: str | None = None
    exit_node_location: str | None = None
    is_active: bool
    is_default: bool
    tunnel_interface: str | None = None
    tunnel_status: str = "unknown"
    priority: int
    current_clients: int
    max_clients: int
    load_percent: float


class RouteListResponse(SQLModel):
    """List of VPN routes."""
    routes: list[RouteStatusResponse]


class NodeCreate(SQLModel):
    """Schema for creating a route-aware VPN node."""
    name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(default="entry", min_length=4, max_length=20)
    country_code: str = Field(default="ZZ", min_length=2, max_length=2)
    location: str = Field(..., min_length=1, max_length=100)
    endpoint: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=51821, ge=1, le=65535)
    public_key: str = Field(..., min_length=1, max_length=100)
    private_key: str | None = None
    is_active: bool = True
    is_online: bool = True
    max_clients: int = Field(default=100, ge=1)


class NodeUpdate(SQLModel):
    """Schema for updating a route-aware VPN node."""
    name: str | None = None
    role: str | None = None
    country_code: str | None = None
    location: str | None = None
    endpoint: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    public_key: str | None = None
    private_key: str | None = None
    is_active: bool | None = None
    is_online: bool | None = None
    max_clients: int | None = Field(default=None, ge=1)


class RouteCreate(SQLModel):
    """Schema for creating a VPN route."""
    name: str = Field(..., min_length=1, max_length=100)
    entry_node_id: int = Field(..., ge=1)
    exit_node_id: int | None = Field(default=None, ge=1)
    is_active: bool = True
    is_default: bool = False
    priority: int = Field(default=100, ge=0)
    max_clients: int | None = Field(default=None, ge=1)


class RouteUpdate(SQLModel):
    """Schema for updating a VPN route."""
    name: str | None = None
    entry_node_id: int | None = Field(default=None, ge=1)
    exit_node_id: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    is_default: bool | None = None
    priority: int | None = Field(default=None, ge=0)
    max_clients: int | None = Field(default=None, ge=1)


class ServerCreate(SQLModel):
    """Schema for creating a server."""
    name: str = Field(..., min_length=1, max_length=100)
    location: str = Field(..., min_length=1, max_length=100)
    endpoint: str = Field(..., min_length=1, max_length=255)
    public_key: str = Field(..., min_length=1, max_length=100)
    private_key: str | None = None
    port: int = Field(default=51821, ge=1, le=65535)
    is_entry_node: bool = True
    is_exit_node: bool = False
    max_clients: int = Field(default=100, ge=1)


class ServerUpdate(SQLModel):
    """Schema for updating a server."""
    name: str | None = None
    location: str | None = None
    endpoint: str | None = None
    is_active: bool | None = None
    max_clients: int | None = None
