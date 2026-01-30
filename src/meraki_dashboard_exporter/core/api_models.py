"""Typed models for Meraki API responses.

This module provides Pydantic models for common API responses,
ensuring type safety and better documentation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Organization(BaseModel):
    """Meraki organization model."""

    id: str
    name: str
    url: str | None = None
    api: dict[str, bool] | None = None
    licensing: dict[str, Any] | None = None
    cloud: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class Network(BaseModel):
    """Meraki network model."""

    id: str
    organizationId: str
    name: str
    productTypes: list[str] = Field(default_factory=list)
    timeZone: str | None = None
    tags: list[str] = Field(default_factory=list)
    enrollmentString: str | None = None
    url: str | None = None
    notes: str | None = None
    isBoundToConfigTemplate: bool = False

    model_config = ConfigDict(extra="allow")


class Device(BaseModel):
    """Meraki device model."""

    serial: str
    name: str | None = None
    model: str
    networkId: str | None = None
    mac: str | None = None
    lanIp: str | None = None
    wan1Ip: str | None = None
    wan2Ip: str | None = None
    tags: list[str] = Field(default_factory=list)
    lat: float | None = None
    lng: float | None = None
    address: str | None = None
    notes: str | None = None
    url: str | None = None
    productType: str | None = None
    configurationUpdatedAt: datetime | None = None
    firmware: str | None = None
    floorPlanId: str | None = None

    model_config = ConfigDict(extra="allow")


class DeviceStatus(BaseModel):
    """Device status information."""

    serial: str
    status: Literal["online", "offline", "alerting", "dormant"]
    lastReportedAt: datetime | None = None
    publicIp: str | None = None
    lanIp: str | None = None
    wan1Ip: str | None = None
    wan2Ip: str | None = None
    gateway: str | None = None
    ipType: str | None = None
    primaryDns: str | None = None
    secondaryDns: str | None = None
    usingCellularFailover: bool = False
    wan1IpType: str | None = None
    wan2IpType: str | None = None

    model_config = ConfigDict(extra="allow")


class PortStatus(BaseModel):
    """Switch port status model."""

    portId: str
    enabled: bool
    status: Literal["Connected", "Disconnected", "Disabled"] | str
    isUplink: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    speed: str | None = None
    duplex: str | None = None
    usageInKb: dict[str, int] | None = None
    cdp: dict[str, Any] | None = None
    lldp: dict[str, Any] | None = None
    clientCount: int = 0
    powerUsageInWh: float = 0.0
    trafficInKbps: dict[str, float] | None = None
    securePort: dict[str, Any] | None = None

    @field_validator("powerUsageInWh", mode="before")
    @classmethod
    def validate_power_usage(cls, v: Any) -> float:
        """Ensure power usage is a float."""
        if v is None:
            return 0.0
        return float(v)

    model_config = ConfigDict(extra="allow")


class WirelessClient(BaseModel):
    """Wireless client model."""

    id: str
    mac: str
    description: str | None = None
    ip: str | None = None
    ip6: str | None = None
    ip6Local: str | None = None
    user: str | None = None
    firstSeen: datetime
    lastSeen: datetime
    manufacturer: str | None = None
    os: str | None = None
    deviceTypePrediction: str | None = None
    recentDeviceSerial: str | None = None
    recentDeviceName: str | None = None
    recentDeviceMac: str | None = None
    recentDeviceConnection: str | None = None
    ssid: str | None = None
    vlan: int | None = None
    switchport: str | None = None
    status: Literal["Online", "Offline"] | str = "Offline"
    notes: str | None = None
    usage: dict[str, int] | None = None
    namedVlan: str | None = None
    adaptivePolicyGroup: str | None = None
    wirelessCapabilities: str | None = None

    model_config = ConfigDict(extra="allow")


class SensorReading(BaseModel):
    """Sensor reading model."""

    ts: datetime
    metric: str
    value: float

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, v: Any) -> float:
        """Ensure value is a float."""
        if v is None:
            raise ValueError("Sensor value cannot be None")
        return float(v)


class SensorData(BaseModel):
    """Sensor data response model."""

    serial: str
    network: dict[str, str] | None = None
    readings: list[SensorReading] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class APIUsage(BaseModel):
    """API usage statistics model."""

    method: str
    host: str
    path: str
    queryString: str | None = None
    userAgent: str
    ts: datetime
    responseCode: int
    sourceIp: str | None = None

    model_config = ConfigDict(extra="allow")


class License(BaseModel):
    """License information model."""

    id: str | None = None
    licenseType: str
    licenseKey: str | None = None
    orderNumber: str | None = None
    deviceSerial: str | None = None
    networkId: str | None = None
    state: Literal["active", "expired", "expiring", "unused", "unusedActive"] | str
    seatCount: int | None = None
    totalDurationInDays: int | None = None
    durationInDays: int | None = None
    permanentlyQueuedLicenses: list[dict[str, Any]] | None = None
    expirationDate: datetime | None = None
    claimedAt: datetime | None = None
    invalidAt: datetime | None = None
    invalidReason: str | None = None

    model_config = ConfigDict(extra="allow")


class ClientOverview(BaseModel):
    """Client overview statistics model."""

    counts: dict[str, int]
    usages: dict[str, dict[str, int]]

    @field_validator("counts", mode="before")
    @classmethod
    def validate_counts(cls, v: Any) -> dict[str, int]:
        """Ensure counts is a dict with integer values."""
        if not isinstance(v, dict):
            return {}
        return {k: int(val) if val is not None else 0 for k, val in v.items()}

    @field_validator("usages", mode="before")
    @classmethod
    def validate_usages(cls, v: Any) -> dict[str, dict[str, int]]:
        """Ensure usages is properly structured."""
        if not isinstance(v, dict):
            return {}
        result = {}
        for key, usage in v.items():
            if isinstance(usage, dict):
                result[key] = {k: int(val) if val is not None else 0 for k, val in usage.items()}
            else:
                result[key] = {}
        return result


class Alert(BaseModel):
    """Assurance alert model."""

    id: str
    categoryType: str
    alertType: str
    severity: Literal["critical", "warning", "informational"] | str
    alertData: dict[str, Any] | None = None
    device: dict[str, Any] | None = None
    network: dict[str, Any] | None = None
    occurredAt: datetime
    dismissedAt: datetime | None = None

    model_config = ConfigDict(extra="allow")


class MemoryUsage(BaseModel):
    """Device memory usage model."""

    ts: datetime
    percentage: float | None = None
    used: int | None = None
    total: int | None = None
    free: int | None = None

    @field_validator("percentage", "used", "total", "free", mode="before")
    @classmethod
    def validate_numeric(cls, v: Any) -> float | int | None:
        """Ensure numeric values are properly typed."""
        if v is None:
            return None
        return float(v) if "." in str(v) else int(v)


class NetworkClient(BaseModel):
    """Network client model for client-level metrics."""

    id: str
    mac: str
    description: str | None = None
    ip: str | None = None
    ip6: str | None = None
    ip6Local: str | None = None
    user: str | None = None
    firstSeen: datetime
    lastSeen: datetime
    manufacturer: str | None = None
    os: str | None = None
    deviceTypePrediction: str | None = None
    recentDeviceSerial: str | None = None
    recentDeviceName: str | None = None
    recentDeviceMac: str | None = None
    recentDeviceConnection: Literal["Wired", "Wireless"] | str | None = None
    ssid: str | None = None
    vlan: str | None = None  # Can be string or None in API
    switchport: str | None = None
    usage: dict[str, int] | None = None
    status: Literal["Online", "Offline"] | str = "Offline"
    notes: str | None = None
    groupPolicy8021x: str | None = None
    adaptivePolicyGroup: str | None = None
    smInstalled: bool = False
    namedVlan: str | None = None
    pskGroup: str | None = None
    wirelessCapabilities: str | None = None
    is11beCapable: bool | None = None
    mcgSerial: str | None = None
    mcgNodeName: str | None = None
    mcgNodeMac: str | None = None
    mcgNetworkId: str | None = None

    @field_validator("vlan", mode="before")
    @classmethod
    def validate_vlan(cls, v: Any) -> str | None:
        """Convert vlan to string if needed."""
        if v is None:
            return None
        return str(v)

    model_config = ConfigDict(extra="allow")


# Uplink status models
class UplinkSignalStat(BaseModel):
    """Cellular signal statistics for an uplink."""

    rsrp: str | None = None  # Reference Signal Received Power
    rsrq: str | None = None  # Reference Signal Received Quality

    model_config = ConfigDict(extra="allow")


class UplinkRoaming(BaseModel):
    """Roaming status for a cellular uplink."""

    status: Literal["home", "roaming", "unknown"] | str | None = None

    model_config = ConfigDict(extra="allow")


class Uplink(BaseModel):
    """Individual uplink status for a device."""

    interface: Literal["cellular", "wan1", "wan2", "wan3"] | str
    status: Literal["active", "connecting", "failed", "not connected", "ready"] | str
    ip: str | None = None
    gateway: str | None = None
    publicIp: str | None = None
    primaryDns: str | None = None
    secondaryDns: str | None = None
    ipAssignedBy: str | None = None
    provider: str | None = None
    signalStat: UplinkSignalStat | None = None
    mcc: str | None = None  # Mobile country code
    mnc: str | None = None  # Mobile network code
    roaming: UplinkRoaming | None = None
    connectionType: str | None = None  # Radio access technology
    apn: str | None = None  # Access point name
    mtu: int | None = None  # Maximum transmission unit
    iccid: str | None = None  # SIM card identifier
    imsi: str | None = None  # International mobile subscriber identity
    msisdn: str | None = None  # Phone number

    model_config = ConfigDict(extra="allow")


class HighAvailability(BaseModel):
    """High availability status for a device."""

    enabled: bool = False
    role: str | None = None  # "primary", "spare", etc.

    model_config = ConfigDict(extra="allow")


class UplinkStatus(BaseModel):
    """Device uplink status from organization uplinks statuses endpoint."""

    networkId: str
    serial: str
    model: str | None = None
    lastReportedAt: datetime | None = None
    highAvailability: HighAvailability | None = None
    uplinks: list[Uplink] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# VPN Status models
class VpnUplink(BaseModel):
    """VPN uplink information."""

    interface: str
    publicIp: str | None = None

    model_config = ConfigDict(extra="allow")


class VpnPeer(BaseModel):
    """VPN peer connection information."""

    networkId: str
    networkName: str | None = None
    reachability: str | None = None  # "reachable", "unreachable"

    model_config = ConfigDict(extra="allow")


class VpnStatus(BaseModel):
    """VPN status for a network from organization VPN statuses endpoint."""

    networkId: str
    networkName: str | None = None
    deviceSerial: str | None = None
    deviceStatus: str | None = None
    vpnMode: str | None = None  # "hub", "spoke", "none"
    exportedSubnets: list[dict[str, Any]] = Field(default_factory=list)
    uplinks: list[VpnUplink] = Field(default_factory=list)
    merakiVpnPeers: list[VpnPeer] = Field(default_factory=list)
    thirdPartyVpnPeers: list[VpnPeer] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# VPN Stats models
class VpnUsageSummary(BaseModel):
    """VPN usage summary with bytes sent/received."""

    receivedInKilobytes: int = 0
    sentInKilobytes: int = 0

    model_config = ConfigDict(extra="allow")


class VpnStatSummary(BaseModel):
    """VPN stat summary with min/avg/max values."""

    senderUplink: str | None = None
    receiverUplink: str | None = None
    avgLatencyMs: float | None = None
    minLatencyMs: float | None = None
    maxLatencyMs: float | None = None
    avgLossPercentage: float | None = None
    minLossPercentage: float | None = None
    maxLossPercentage: float | None = None
    avgJitter: float | None = None
    minJitter: float | None = None
    maxJitter: float | None = None
    avgMos: float | None = None
    minMos: float | None = None
    maxMos: float | None = None

    model_config = ConfigDict(extra="allow")


class VpnPeerStats(BaseModel):
    """VPN peer statistics."""

    networkId: str
    networkName: str | None = None
    usageSummary: VpnUsageSummary | None = None
    latencySummaries: list[VpnStatSummary] = Field(default_factory=list)
    lossPercentageSummaries: list[VpnStatSummary] = Field(default_factory=list)
    jitterSummaries: list[VpnStatSummary] = Field(default_factory=list)
    mosSummaries: list[VpnStatSummary] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class VpnStats(BaseModel):
    """VPN statistics for a network."""

    networkId: str
    networkName: str | None = None
    merakiVpnPeers: list[VpnPeerStats] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# Device Performance model
class DevicePerformance(BaseModel):
    """Device performance score."""

    perfScore: float | None = None

    model_config = ConfigDict(extra="allow")


# Uplink Usage models
class UplinkUsageByInterface(BaseModel):
    """Uplink usage for a single interface."""

    serial: str
    interface: str
    sent: int = 0
    received: int = 0

    model_config = ConfigDict(extra="allow")


class NetworkUplinkUsage(BaseModel):
    """Network uplink usage from organization uplinks usage endpoint."""

    networkId: str
    name: str | None = None
    byUplink: list[UplinkUsageByInterface] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


# Loss and Latency History models
class LossAndLatencyEntry(BaseModel):
    """Single entry in loss and latency history."""

    startTime: datetime
    endTime: datetime
    lossPercent: float | None = None
    latencyMs: float | None = None
    goodput: int | None = None
    jitter: float | None = None

    model_config = ConfigDict(extra="allow")


# Response wrapper models
class PaginatedResponse(BaseModel):
    """Paginated API response wrapper."""

    items: list[dict[str, Any]]
    meta: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")
