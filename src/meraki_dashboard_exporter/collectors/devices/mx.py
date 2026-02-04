"""MX security appliance collector."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...core.api_models import (
    DevicePerformance,
    HighAvailability,
    LossAndLatencyEntry,
    NetworkUplinkUsage,
    Uplink,
    UplinkStatus,
    VpnPeerStats,
    VpnStats,
    VpnStatus,
)
from ...core.constants import MXMetricName
from ...core.error_handling import ErrorCategory, validate_response_format, with_error_handling
from ...core.label_helpers import create_device_labels
from ...core.logging import get_logger
from ...core.logging_decorators import log_api_call
from ...core.logging_helpers import LogContext
from ...core.metrics import LabelName
from ...core.otel_tracing import trace_method
from .base import BaseDeviceCollector

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Standard device labels used across all MX metrics
_DEVICE_LABELS: list[str] = [
    LabelName.ORG_ID.value,
    LabelName.ORG_NAME.value,
    LabelName.NETWORK_ID.value,
    LabelName.NETWORK_NAME.value,
    LabelName.SERIAL.value,
    LabelName.NAME.value,
    LabelName.MODEL.value,
    LabelName.DEVICE_TYPE.value,
]

# Network-level labels (no device-specific info)
_NETWORK_LABELS: list[str] = [
    LabelName.ORG_ID.value,
    LabelName.ORG_NAME.value,
    LabelName.NETWORK_ID.value,
    LabelName.NETWORK_NAME.value,
]


class MXCollector(BaseDeviceCollector):
    """Collector for MX security appliance metrics."""

    def __init__(self, parent: Any) -> None:
        """Initialize the MX collector.

        Parameters
        ----------
        parent : Any
            Parent collector providing shared metrics and helpers.

        """
        super().__init__(parent)
        self._uplink_status_cache: dict[str, UplinkStatus] = {}
        self._network_lookup: dict[str, dict[str, str]] = {}

    def _initialize_metrics(self) -> None:
        """Initialize MX-specific metrics."""
        self._initialize_uplink_metrics()
        self._initialize_vpn_metrics()
        self._initialize_performance_metrics()
        self._initialize_loss_latency_metrics()

    def _initialize_uplink_metrics(self) -> None:
        """Initialize uplink-related metrics."""
        # Uplink status metric (1 = active, 0 = not active)
        self._mx_uplink_status = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_STATUS,
            "MX uplink status (1 = active, 0 = not active)",
            labelnames=[*_DEVICE_LABELS, LabelName.INTERFACE.value, LabelName.STATUS.value],
        )

        # Uplink info metric (info metric with additional details)
        self._mx_uplink_info = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_INFO,
            "MX uplink information",
            labelnames=[
                *_DEVICE_LABELS,
                LabelName.INTERFACE.value,
                LabelName.PUBLIC_IP.value,
                LabelName.PROVIDER.value,
                LabelName.CONNECTION_TYPE.value,
            ],
        )

        # Cellular signal metrics
        self._mx_uplink_signal_rsrp = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_SIGNAL_RSRP,
            "MX cellular uplink RSRP (Reference Signal Received Power) in dBm",
            labelnames=[*_DEVICE_LABELS, LabelName.INTERFACE.value],
        )

        self._mx_uplink_signal_rsrq = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_SIGNAL_RSRQ,
            "MX cellular uplink RSRQ (Reference Signal Received Quality) in dB",
            labelnames=[*_DEVICE_LABELS, LabelName.INTERFACE.value],
        )

        # High availability metrics
        self._mx_ha_enabled = self.parent._create_gauge(
            MXMetricName.MX_HA_ENABLED,
            "MX high availability enabled (1 = enabled, 0 = disabled)",
            labelnames=_DEVICE_LABELS,
        )

        self._mx_ha_info = self.parent._create_gauge(
            MXMetricName.MX_HA_INFO,
            "MX high availability information",
            labelnames=[*_DEVICE_LABELS, LabelName.HA_ROLE.value],
        )

        # Uplink usage metrics
        self._mx_uplink_sent_bytes = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_SENT_BYTES,
            "MX uplink bytes sent",
            labelnames=[*_NETWORK_LABELS, LabelName.SERIAL.value, LabelName.INTERFACE.value],
        )

        self._mx_uplink_received_bytes = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_RECEIVED_BYTES,
            "MX uplink bytes received",
            labelnames=[*_NETWORK_LABELS, LabelName.SERIAL.value, LabelName.INTERFACE.value],
        )

    def _initialize_vpn_metrics(self) -> None:
        """Initialize VPN-related metrics."""
        # VPN peer status
        self._mx_vpn_peer_status = self.parent._create_gauge(
            MXMetricName.MX_VPN_PEER_STATUS,
            "MX VPN peer reachability (1 = reachable, 0 = unreachable)",
            labelnames=[
                *_NETWORK_LABELS,
                LabelName.PEER_NETWORK_ID.value,
                LabelName.PEER_NETWORK_NAME.value,
                LabelName.REACHABILITY.value,
            ],
        )

        # VPN mode info
        self._mx_vpn_mode_info = self.parent._create_gauge(
            MXMetricName.MX_VPN_MODE_INFO,
            "MX VPN mode information",
            labelnames=[*_NETWORK_LABELS, LabelName.VPN_MODE.value],
        )

        # VPN exported subnets count
        self._mx_vpn_exported_subnets_total = self.parent._create_gauge(
            MXMetricName.MX_VPN_EXPORTED_SUBNETS_TOTAL,
            "Number of subnets exported via VPN",
            labelnames=_NETWORK_LABELS,
        )

        # VPN performance metrics
        vpn_perf_labels: list[str] = [
            *_NETWORK_LABELS,
            LabelName.PEER_NETWORK_ID.value,
            LabelName.PEER_NETWORK_NAME.value,
            LabelName.STAT.value,
            LabelName.SENDER_UPLINK.value,
            LabelName.RECEIVER_UPLINK.value,
        ]

        self._mx_vpn_latency_ms = self.parent._create_gauge(
            MXMetricName.MX_VPN_LATENCY_MS,
            "MX VPN tunnel latency in milliseconds",
            labelnames=vpn_perf_labels,
        )

        self._mx_vpn_loss_percent = self.parent._create_gauge(
            MXMetricName.MX_VPN_LOSS_PERCENT,
            "MX VPN tunnel packet loss percentage",
            labelnames=vpn_perf_labels,
        )

        self._mx_vpn_jitter_ms = self.parent._create_gauge(
            MXMetricName.MX_VPN_JITTER_MS,
            "MX VPN tunnel jitter in milliseconds",
            labelnames=vpn_perf_labels,
        )

        self._mx_vpn_mos = self.parent._create_gauge(
            MXMetricName.MX_VPN_MOS,
            "MX VPN tunnel Mean Opinion Score (voice quality metric)",
            labelnames=vpn_perf_labels,
        )

        # VPN usage metrics
        vpn_usage_labels: list[str] = [
            *_NETWORK_LABELS,
            LabelName.PEER_NETWORK_ID.value,
            LabelName.PEER_NETWORK_NAME.value,
        ]

        self._mx_vpn_usage_sent_bytes = self.parent._create_gauge(
            MXMetricName.MX_VPN_USAGE_SENT_BYTES,
            "MX VPN bytes sent to peer",
            labelnames=vpn_usage_labels,
        )

        self._mx_vpn_usage_received_bytes = self.parent._create_gauge(
            MXMetricName.MX_VPN_USAGE_RECEIVED_BYTES,
            "MX VPN bytes received from peer",
            labelnames=vpn_usage_labels,
        )

    def _initialize_performance_metrics(self) -> None:
        """Initialize device performance metrics."""
        self._mx_performance_score = self.parent._create_gauge(
            MXMetricName.MX_PERFORMANCE_SCORE,
            "MX device performance/utilization score (0-100)",
            labelnames=_DEVICE_LABELS,
        )

    def _initialize_loss_latency_metrics(self) -> None:
        """Initialize loss and latency metrics."""
        loss_latency_labels: list[str] = [
            *_DEVICE_LABELS,
            LabelName.INTERFACE.value,
            LabelName.DESTINATION_IP.value,
        ]

        self._mx_uplink_loss_percent = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_LOSS_PERCENT,
            "MX uplink packet loss percentage",
            labelnames=loss_latency_labels,
        )

        self._mx_uplink_latency_ms = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_LATENCY_MS,
            "MX uplink latency in milliseconds",
            labelnames=loss_latency_labels,
        )

        self._mx_uplink_jitter_ms = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_JITTER_MS,
            "MX uplink jitter in milliseconds",
            labelnames=loss_latency_labels,
        )

        self._mx_uplink_goodput_kbps = self.parent._create_gauge(
            MXMetricName.MX_UPLINK_GOODPUT_KBPS,
            "MX uplink goodput in kilobits per second",
            labelnames=loss_latency_labels,
        )

    async def collect(self, device: dict[str, Any]) -> None:
        """Collect MX-specific metrics.

        Parameters
        ----------
        device : dict[str, Any]
            Device data with status_info added.

        """
        # Collect common metrics
        self.collect_common_metrics(device)

        # Per-device metrics from uplink status cache
        serial = device.get("serial", "")
        if serial in self._uplink_status_cache:
            uplink_status = self._uplink_status_cache[serial]
            await self._process_uplink_status(device, uplink_status)

    # =========================================================================
    # Uplink Status Collection
    # =========================================================================

    @trace_method("collect.mx_uplink_statuses")
    @log_api_call("getOrganizationUplinksStatuses")
    @with_error_handling(
        operation="Collect MX uplink statuses",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_uplink_statuses(
        self,
        org_id: str,
        org_name: str,
        device_lookup: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Collect uplink status metrics for all MX devices in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        device_lookup : dict[str, dict[str, Any]] | None
            Device lookup table for enriching device info.

        """
        self._track_api_call("getOrganizationUplinksStatuses")

        # Get network IDs for batching if we have device lookup
        network_ids: list[str] = []
        if device_lookup:
            network_ids = list({d.get("networkId", "") for d in device_lookup.values() if d.get("networkId")})

        # Batch by network IDs to avoid 502 errors on large deployments
        batch_size = self.settings.api.org_endpoint_batch_size
        uplink_statuses: list[dict[str, Any]] = []

        if batch_size > 0 and len(network_ids) > batch_size:
            # Split network IDs into batches
            network_batches = [
                network_ids[i : i + batch_size] for i in range(0, len(network_ids), batch_size)
            ]
            logger.debug(
                "Batching org-level uplink status calls",
                org_id=org_id,
                total_networks=len(network_ids),
                batch_size=batch_size,
                batch_count=len(network_batches),
            )

            for batch_idx, network_batch in enumerate(network_batches):
                with LogContext(org_id=org_id, batch=f"{batch_idx + 1}/{len(network_batches)}"):
                    response = await asyncio.to_thread(
                        self.api.organizations.getOrganizationUplinksStatuses,
                        org_id,
                        networkIds=network_batch,
                        perPage=1000,
                        total_pages="all",
                    )
                    batch_statuses = validate_response_format(
                        response,
                        expected_type=list,
                        operation="getOrganizationUplinksStatuses",
                    )
                    uplink_statuses.extend(batch_statuses)
        else:
            # Single request for all devices
            with LogContext(org_id=org_id):
                response = await asyncio.to_thread(
                    self.api.organizations.getOrganizationUplinksStatuses,
                    org_id,
                    perPage=1000,
                    total_pages="all",
                )

            uplink_statuses = validate_response_format(
                response,
                expected_type=list,
                operation="getOrganizationUplinksStatuses",
            )

        logger.debug(
            "Fetched organization uplink statuses",
            org_id=org_id,
            device_count=len(uplink_statuses),
        )

        # Clear the uplink status cache for this collection cycle
        self._uplink_status_cache.clear()

        for status_data in uplink_statuses:
            try:
                # Parse and validate the uplink status
                uplink_status = UplinkStatus.model_validate(status_data)

                # Get device info from lookup
                serial = uplink_status.serial
                device_info = (device_lookup or {}).get(serial, {})

                # Only process MX, MG, and Z series devices
                model = uplink_status.model or device_info.get("model", "")
                device_type = model[:2] if len(model) >= 2 else ""

                # Skip non-MX/MG/Z devices (the API returns MX, MG, and Z series)
                if device_type not in {"MX", "MG", "Z1", "Z3", "Z4"}:
                    # For Z series, check full model prefix
                    if not model.startswith("Z"):
                        continue

                # Build device data for label creation
                device_data = {
                    "serial": serial,
                    "name": device_info.get("name", serial),
                    "model": model,
                    "networkId": uplink_status.networkId,
                    "networkName": device_info.get("network_name", uplink_status.networkId),
                    "orgId": org_id,
                    "orgName": org_name,
                }

                # Cache for per-device collection
                self._uplink_status_cache[serial] = uplink_status

                # Process uplinks
                for uplink in uplink_status.uplinks:
                    self._process_uplink(device_data, uplink, org_id, org_name)

                # Process high availability
                if uplink_status.highAvailability:
                    self._process_high_availability(
                        device_data, uplink_status.highAvailability, org_id, org_name
                    )

            except Exception:
                logger.exception(
                    "Failed to process uplink status for device",
                    serial=status_data.get("serial", "unknown"),
                )

        logger.info(
            "Collected MX uplink statuses",
            org_id=org_id,
            org_name=org_name,
            devices_processed=len(uplink_statuses),
        )

    def _process_uplink(
        self,
        device_data: dict[str, Any],
        uplink: Uplink,
        org_id: str,
        org_name: str,
    ) -> None:
        """Process a single uplink and set metrics."""
        base_labels = create_device_labels(device_data, org_id=org_id, org_name=org_name)

        # Uplink status metric
        status_labels = {
            **base_labels,
            LabelName.INTERFACE.value: uplink.interface,
            LabelName.STATUS.value: uplink.status,
        }
        is_active = 1 if uplink.status == "active" else 0
        self._mx_uplink_status.labels(**status_labels).set(is_active)

        # Uplink info metric
        info_labels = {
            **base_labels,
            LabelName.INTERFACE.value: uplink.interface,
            LabelName.PUBLIC_IP.value: uplink.publicIp or "",
            LabelName.PROVIDER.value: uplink.provider or "",
            LabelName.CONNECTION_TYPE.value: uplink.connectionType or "",
        }
        self._mx_uplink_info.labels(**info_labels).set(1)

        # Cellular signal metrics
        if uplink.interface == "cellular" and uplink.signalStat:
            signal_labels = {
                **base_labels,
                LabelName.INTERFACE.value: uplink.interface,
            }

            if uplink.signalStat.rsrp:
                try:
                    self._mx_uplink_signal_rsrp.labels(**signal_labels).set(
                        float(uplink.signalStat.rsrp)
                    )
                except ValueError:
                    pass

            if uplink.signalStat.rsrq:
                try:
                    self._mx_uplink_signal_rsrq.labels(**signal_labels).set(
                        float(uplink.signalStat.rsrq)
                    )
                except ValueError:
                    pass

    def _process_high_availability(
        self,
        device_data: dict[str, Any],
        ha: HighAvailability,
        org_id: str,
        org_name: str,
    ) -> None:
        """Process high availability status and set metrics."""
        base_labels = create_device_labels(device_data, org_id=org_id, org_name=org_name)

        ha_enabled = 1 if ha.enabled else 0
        self._mx_ha_enabled.labels(**base_labels).set(ha_enabled)

        if ha.enabled and ha.role:
            ha_info_labels = {**base_labels, LabelName.HA_ROLE.value: ha.role}
            self._mx_ha_info.labels(**ha_info_labels).set(1)

    async def _process_uplink_status(
        self, device: dict[str, Any], uplink_status: UplinkStatus
    ) -> None:
        """Process cached uplink status for a specific device."""
        # Currently all processing is done in collect_uplink_statuses
        pass

    # =========================================================================
    # VPN Status Collection
    # =========================================================================

    @trace_method("collect.mx_vpn_statuses")
    @log_api_call("getOrganizationApplianceVpnStatuses")
    @with_error_handling(
        operation="Collect MX VPN statuses",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_vpn_statuses(
        self,
        org_id: str,
        org_name: str,
    ) -> None:
        """Collect VPN status metrics for all networks in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        self._track_api_call("getOrganizationApplianceVpnStatuses")

        with LogContext(org_id=org_id):
            response = await asyncio.to_thread(
                self.api.appliance.getOrganizationApplianceVpnStatuses,
                org_id,
                perPage=300,
                total_pages="all",
            )

        vpn_statuses = validate_response_format(
            response,
            expected_type=list,
            operation="getOrganizationApplianceVpnStatuses",
        )

        logger.debug(
            "Fetched organization VPN statuses",
            org_id=org_id,
            network_count=len(vpn_statuses),
        )

        # Build network lookup for later use
        self._network_lookup.clear()

        for status_data in vpn_statuses:
            try:
                vpn_status = VpnStatus.model_validate(status_data)
                network_id = vpn_status.networkId
                network_name = vpn_status.networkName or network_id

                # Store network info for lookup
                self._network_lookup[network_id] = {
                    "network_id": network_id,
                    "network_name": network_name,
                }

                # Base network labels
                network_labels = {
                    LabelName.ORG_ID.value: org_id,
                    LabelName.ORG_NAME.value: org_name,
                    LabelName.NETWORK_ID.value: network_id,
                    LabelName.NETWORK_NAME.value: network_name,
                }

                # VPN mode info
                if vpn_status.vpnMode:
                    mode_labels = {
                        **network_labels,
                        LabelName.VPN_MODE.value: vpn_status.vpnMode,
                    }
                    self._mx_vpn_mode_info.labels(**mode_labels).set(1)

                # Exported subnets count
                subnet_count = len(vpn_status.exportedSubnets)
                self._mx_vpn_exported_subnets_total.labels(**network_labels).set(subnet_count)

                # Process Meraki VPN peers
                for peer in vpn_status.merakiVpnPeers:
                    reachability = peer.reachability or "unknown"
                    is_reachable = 1 if reachability == "reachable" else 0

                    peer_labels = {
                        **network_labels,
                        LabelName.PEER_NETWORK_ID.value: peer.networkId,
                        LabelName.PEER_NETWORK_NAME.value: peer.networkName or peer.networkId,
                        LabelName.REACHABILITY.value: reachability,
                    }
                    self._mx_vpn_peer_status.labels(**peer_labels).set(is_reachable)

                # Process third-party VPN peers
                for peer in vpn_status.thirdPartyVpnPeers:
                    reachability = peer.reachability or "unknown"
                    is_reachable = 1 if reachability == "reachable" else 0

                    peer_labels = {
                        **network_labels,
                        LabelName.PEER_NETWORK_ID.value: peer.networkId,
                        LabelName.PEER_NETWORK_NAME.value: peer.networkName or peer.networkId,
                        LabelName.REACHABILITY.value: reachability,
                    }
                    self._mx_vpn_peer_status.labels(**peer_labels).set(is_reachable)

            except Exception:
                logger.exception(
                    "Failed to process VPN status for network",
                    network_id=status_data.get("networkId", "unknown"),
                )

        logger.info(
            "Collected MX VPN statuses",
            org_id=org_id,
            org_name=org_name,
            networks_processed=len(vpn_statuses),
        )

    # =========================================================================
    # VPN Stats Collection
    # =========================================================================

    @trace_method("collect.mx_vpn_stats")
    @log_api_call("getOrganizationApplianceVpnStats")
    @with_error_handling(
        operation="Collect MX VPN stats",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_vpn_stats(
        self,
        org_id: str,
        org_name: str,
    ) -> None:
        """Collect VPN performance statistics for all networks in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        self._track_api_call("getOrganizationApplianceVpnStats")

        with LogContext(org_id=org_id):
            response = await asyncio.to_thread(
                self.api.appliance.getOrganizationApplianceVpnStats,
                org_id,
                perPage=300,
                total_pages="all",
                timespan=86400,  # Last 24 hours
            )

        vpn_stats_list = validate_response_format(
            response,
            expected_type=list,
            operation="getOrganizationApplianceVpnStats",
        )

        logger.debug(
            "Fetched organization VPN stats",
            org_id=org_id,
            network_count=len(vpn_stats_list),
        )

        for stats_data in vpn_stats_list:
            try:
                vpn_stats = VpnStats.model_validate(stats_data)
                network_id = vpn_stats.networkId
                network_name = vpn_stats.networkName or network_id

                # Base network labels
                network_labels = {
                    LabelName.ORG_ID.value: org_id,
                    LabelName.ORG_NAME.value: org_name,
                    LabelName.NETWORK_ID.value: network_id,
                    LabelName.NETWORK_NAME.value: network_name,
                }

                # Process each VPN peer
                for peer_stats in vpn_stats.merakiVpnPeers:
                    self._process_vpn_peer_stats(network_labels, peer_stats)

            except Exception:
                logger.exception(
                    "Failed to process VPN stats for network",
                    network_id=stats_data.get("networkId", "unknown"),
                )

        logger.info(
            "Collected MX VPN stats",
            org_id=org_id,
            org_name=org_name,
            networks_processed=len(vpn_stats_list),
        )

    def _process_vpn_peer_stats(
        self,
        network_labels: dict[str, str],
        peer_stats: VpnPeerStats,
    ) -> None:
        """Process VPN peer statistics and set metrics."""
        peer_base_labels = {
            **network_labels,
            LabelName.PEER_NETWORK_ID.value: peer_stats.networkId,
            LabelName.PEER_NETWORK_NAME.value: peer_stats.networkName or peer_stats.networkId,
        }

        # Usage metrics
        if peer_stats.usageSummary:
            self._mx_vpn_usage_sent_bytes.labels(**peer_base_labels).set(
                peer_stats.usageSummary.sentInKilobytes * 1024
            )
            self._mx_vpn_usage_received_bytes.labels(**peer_base_labels).set(
                peer_stats.usageSummary.receivedInKilobytes * 1024
            )

        # Process latency summaries
        for summary in peer_stats.latencySummaries:
            self._set_vpn_stat_metrics(
                peer_base_labels,
                summary,
                self._mx_vpn_latency_ms,
                "avgLatencyMs",
                "minLatencyMs",
                "maxLatencyMs",
            )

        # Process loss summaries
        for summary in peer_stats.lossPercentageSummaries:
            self._set_vpn_stat_metrics(
                peer_base_labels,
                summary,
                self._mx_vpn_loss_percent,
                "avgLossPercentage",
                "minLossPercentage",
                "maxLossPercentage",
            )

        # Process jitter summaries
        for summary in peer_stats.jitterSummaries:
            self._set_vpn_stat_metrics(
                peer_base_labels,
                summary,
                self._mx_vpn_jitter_ms,
                "avgJitter",
                "minJitter",
                "maxJitter",
            )

        # Process MOS summaries
        for summary in peer_stats.mosSummaries:
            self._set_vpn_stat_metrics(
                peer_base_labels,
                summary,
                self._mx_vpn_mos,
                "avgMos",
                "minMos",
                "maxMos",
            )

    def _set_vpn_stat_metrics(
        self,
        base_labels: dict[str, str],
        summary: Any,
        metric: Any,
        avg_field: str,
        min_field: str,
        max_field: str,
    ) -> None:
        """Set VPN stat metrics for min/avg/max values."""
        sender = summary.senderUplink or ""
        receiver = summary.receiverUplink or ""

        for stat_type, field_name in [("avg", avg_field), ("min", min_field), ("max", max_field)]:
            value = getattr(summary, field_name, None)
            if value is not None:
                labels = {
                    **base_labels,
                    LabelName.STAT.value: stat_type,
                    LabelName.SENDER_UPLINK.value: sender,
                    LabelName.RECEIVER_UPLINK.value: receiver,
                }
                metric.labels(**labels).set(value)

    # =========================================================================
    # Device Performance Collection
    # =========================================================================

    @trace_method("collect.mx_performance")
    @log_api_call("getDeviceAppliancePerformance")
    @with_error_handling(
        operation="Collect MX device performance",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_device_performance(
        self,
        org_id: str,
        org_name: str,
        devices: list[dict[str, Any]],
    ) -> None:
        """Collect performance scores for all MX devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        devices : list[dict[str, Any]]
            List of MX devices.

        """
        mx_devices = [
            d
            for d in devices
            if d.get("model", "").startswith("MX") or d.get("model", "").startswith("Z")
        ]

        logger.debug(
            "Collecting performance for MX devices",
            org_id=org_id,
            device_count=len(mx_devices),
        )

        for device in mx_devices:
            serial = device.get("serial", "")
            if not serial:
                continue

            try:
                self._track_api_call("getDeviceAppliancePerformance")

                with LogContext(serial=serial):
                    response = await asyncio.to_thread(
                        self.api.appliance.getDeviceAppliancePerformance,
                        serial,
                    )

                if response:
                    perf = DevicePerformance.model_validate(response)
                    if perf.perfScore is not None:
                        labels = create_device_labels(device, org_id=org_id, org_name=org_name)
                        self._mx_performance_score.labels(**labels).set(perf.perfScore)

                        logger.debug(
                            "Set MX performance score",
                            serial=serial,
                            perf_score=perf.perfScore,
                        )

            except Exception:
                logger.debug(
                    "Failed to get performance for device (may be secondary/spare)",
                    serial=serial,
                )

        logger.info(
            "Collected MX device performance",
            org_id=org_id,
            org_name=org_name,
            devices_processed=len(mx_devices),
        )

    # =========================================================================
    # Uplink Usage Collection
    # =========================================================================

    @trace_method("collect.mx_uplink_usage")
    @log_api_call("getOrganizationApplianceUplinksUsageByNetwork")
    @with_error_handling(
        operation="Collect MX uplink usage",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_uplink_usage(
        self,
        org_id: str,
        org_name: str,
    ) -> None:
        """Collect uplink usage metrics for all networks in an organization.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.

        """
        self._track_api_call("getOrganizationApplianceUplinksUsageByNetwork")

        with LogContext(org_id=org_id):
            response = await asyncio.to_thread(
                self.api.appliance.getOrganizationApplianceUplinksUsageByNetwork,
                org_id,
                timespan=86400,  # Last 24 hours
            )

        usage_list = validate_response_format(
            response,
            expected_type=list,
            operation="getOrganizationApplianceUplinksUsageByNetwork",
        )

        logger.debug(
            "Fetched organization uplink usage",
            org_id=org_id,
            network_count=len(usage_list),
        )

        for usage_data in usage_list:
            try:
                network_usage = NetworkUplinkUsage.model_validate(usage_data)
                network_id = network_usage.networkId
                network_name = network_usage.name or network_id

                for uplink_usage in network_usage.byUplink:
                    labels = {
                        LabelName.ORG_ID.value: org_id,
                        LabelName.ORG_NAME.value: org_name,
                        LabelName.NETWORK_ID.value: network_id,
                        LabelName.NETWORK_NAME.value: network_name,
                        LabelName.SERIAL.value: uplink_usage.serial,
                        LabelName.INTERFACE.value: uplink_usage.interface,
                    }

                    self._mx_uplink_sent_bytes.labels(**labels).set(uplink_usage.sent)
                    self._mx_uplink_received_bytes.labels(**labels).set(uplink_usage.received)

            except Exception:
                logger.exception(
                    "Failed to process uplink usage for network",
                    network_id=usage_data.get("networkId", "unknown"),
                )

        logger.info(
            "Collected MX uplink usage",
            org_id=org_id,
            org_name=org_name,
            networks_processed=len(usage_list),
        )

    # =========================================================================
    # Loss and Latency History Collection
    # =========================================================================

    @trace_method("collect.mx_loss_latency")
    @with_error_handling(
        operation="Collect MX loss and latency",
        continue_on_error=True,
        error_category=ErrorCategory.API_CLIENT_ERROR,
    )
    async def collect_loss_and_latency(
        self,
        org_id: str,
        org_name: str,
        devices: list[dict[str, Any]],
        destination_ip: str = "8.8.8.8",
    ) -> None:
        """Collect loss and latency metrics for MX devices.

        Parameters
        ----------
        org_id : str
            Organization ID.
        org_name : str
            Organization name.
        devices : list[dict[str, Any]]
            List of MX devices.
        destination_ip : str
            Destination IP for latency measurements (default: 8.8.8.8).

        """
        mx_devices = [
            d
            for d in devices
            if d.get("model", "").startswith("MX")
            or d.get("model", "").startswith("MG")
            or d.get("model", "").startswith("Z")
        ]

        logger.info(
            "Starting loss/latency collection for MX devices",
            org_id=org_id,
            device_count=len(mx_devices),
            destination_ip=destination_ip,
        )

        successful_metrics = 0
        failed_devices = 0

        for idx, device in enumerate(mx_devices):
            serial = device.get("serial", "")
            if not serial:
                continue

            device_success = False
            # Try each uplink interface
            for uplink in ["wan1", "wan2", "cellular"]:
                try:
                    await self._collect_device_loss_latency(
                        device, org_id, org_name, uplink, destination_ip
                    )
                    device_success = True
                    successful_metrics += 1
                except Exception as e:
                    # Log at debug level - device may not have all uplinks
                    logger.debug(
                        "Failed to collect loss/latency for uplink",
                        serial=serial,
                        uplink=uplink,
                        error=str(e),
                    )

            if not device_success:
                failed_devices += 1

            # Log progress every 50 devices
            if (idx + 1) % 50 == 0:
                logger.debug(
                    "Loss/latency collection progress",
                    processed=idx + 1,
                    total=len(mx_devices),
                    successful_metrics=successful_metrics,
                )

        logger.info(
            "Completed MX loss and latency collection",
            org_id=org_id,
            org_name=org_name,
            devices_processed=len(mx_devices),
            successful_metrics=successful_metrics,
            failed_devices=failed_devices,
        )

    @log_api_call("getDeviceLossAndLatencyHistory")
    async def _collect_device_loss_latency(
        self,
        device: dict[str, Any],
        org_id: str,
        org_name: str,
        uplink: str,
        destination_ip: str,
    ) -> None:
        """Collect loss and latency for a single device/uplink."""
        serial = device.get("serial", "")
        self._track_api_call("getDeviceLossAndLatencyHistory")

        with LogContext(serial=serial, uplink=uplink):
            response = await asyncio.to_thread(
                self.api.devices.getDeviceLossAndLatencyHistory,
                serial,
                ip=destination_ip,
                uplink=uplink,
                timespan=300,  # Last 5 minutes
                resolution=60,
            )

        if not response:
            logger.debug(
                "No response from loss/latency API",
                serial=serial,
                uplink=uplink,
            )
            return

        entries = validate_response_format(
            response,
            expected_type=list,
            operation="getDeviceLossAndLatencyHistory",
        )

        if not entries:
            logger.debug(
                "Empty entries from loss/latency API",
                serial=serial,
                uplink=uplink,
            )
            return

        # Use most recent entry
        latest_data = entries[-1]
        entry = LossAndLatencyEntry.model_validate(latest_data)

        labels = {
            **create_device_labels(device, org_id=org_id, org_name=org_name),
            LabelName.INTERFACE.value: uplink,
            LabelName.DESTINATION_IP.value: destination_ip,
        }

        if entry.lossPercent is not None:
            self._mx_uplink_loss_percent.labels(**labels).set(entry.lossPercent)

        if entry.latencyMs is not None:
            self._mx_uplink_latency_ms.labels(**labels).set(entry.latencyMs)

        if entry.jitter is not None:
            self._mx_uplink_jitter_ms.labels(**labels).set(entry.jitter)

        if entry.goodput is not None:
            self._mx_uplink_goodput_kbps.labels(**labels).set(entry.goodput)

        logger.debug(
            "Set loss/latency metrics",
            serial=serial,
            uplink=uplink,
            loss=entry.lossPercent,
            latency=entry.latencyMs,
        )
