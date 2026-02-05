"""Tests for MX (Security Appliance) collector."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from meraki_dashboard_exporter.collectors.devices.mx import MXCollector
from meraki_dashboard_exporter.core.api_models import HighAvailability, UplinkStatus

if TYPE_CHECKING:
    pass


def create_mock_rate_limiter() -> MagicMock:
    """Create a mock rate limiter that returns 0 wait time."""
    rate_limiter = MagicMock()
    rate_limiter.acquire = AsyncMock(return_value=0)
    return rate_limiter


class TestMXCollector:
    """Test MX collector functionality."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.appliance = MagicMock()
        api.devices = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent DeviceCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.settings.api = MagicMock()
        parent.settings.api.concurrency_limit = 5
        parent._create_gauge = MagicMock(return_value=MagicMock())
        parent.rate_limiter = create_mock_rate_limiter()
        return parent

    @pytest.fixture
    def mx_collector(
        self,
        mock_parent: MagicMock,
    ) -> MXCollector:
        """Create MX collector instance."""
        collector = MXCollector(mock_parent)
        # Initialize metrics for testing
        collector._mx_performance_score = MagicMock()
        collector._mx_uplink_loss_percent = MagicMock()
        collector._mx_uplink_latency_ms = MagicMock()
        collector._mx_uplink_jitter_ms = MagicMock()
        collector._mx_uplink_goodput_kbps = MagicMock()
        return collector

    async def test_collect_calls_common_metrics(
        self,
        mx_collector: MXCollector,
    ) -> None:
        """Test that MX collector calls common metrics collection."""
        # Create a mock device
        device = {
            "serial": "Q123",
            "name": "Test MX",
            "model": "MX100",
            "network_id": "net1",
            "organization_id": "123",
            "status_info": {
                "status": "online",
            },
        }

        # Mock the collect_common_metrics method to verify it's called
        mx_collector.collect_common_metrics = MagicMock()

        # Call collect
        await mx_collector.collect(device)

        # Verify only common metrics were collected
        mx_collector.collect_common_metrics.assert_called_once_with(device)

    def test_mx_collector_initialization(
        self,
        mx_collector: MXCollector,
        mock_parent: MagicMock,
    ) -> None:
        """Test MX collector initialization."""
        # Verify collector is properly initialized with parent
        assert mx_collector.parent == mock_parent
        assert mx_collector.api == mock_parent.api
        assert mx_collector.settings == mock_parent.settings


class TestMXCollectorDeviceFiltering:
    """Test MX collector device filtering logic."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.appliance = MagicMock()
        api.devices = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent DeviceCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.settings.api = MagicMock()
        parent.settings.api.concurrency_limit = 5
        parent._create_gauge = MagicMock(return_value=MagicMock())
        parent.rate_limiter = create_mock_rate_limiter()
        return parent

    @pytest.fixture
    def mx_collector(self, mock_parent: MagicMock) -> MXCollector:
        """Create MX collector instance."""
        collector = MXCollector(mock_parent)
        collector._mx_performance_score = MagicMock()
        collector._mx_uplink_loss_percent = MagicMock()
        collector._mx_uplink_latency_ms = MagicMock()
        collector._mx_uplink_jitter_ms = MagicMock()
        collector._mx_uplink_goodput_kbps = MagicMock()
        return collector

    @pytest.fixture
    def mixed_devices(self) -> list[dict[str, Any]]:
        """Create a list of mixed device types."""
        return [
            {"serial": "Q2MX-1111-1111", "model": "MX100", "name": "Physical MX 100"},
            {"serial": "Q2MX-2222-2222", "model": "MX250", "name": "Physical MX 250"},
            {"serial": "Q2MX-3333-3333", "model": "MX450", "name": "Physical MX 450"},
            {"serial": "Q2VM-4444-4444", "model": "VMX100", "name": "Virtual MX 100"},
            {"serial": "Q2VM-5555-5555", "model": "VMX-S", "name": "Virtual MX Small"},
            {"serial": "Q2ZS-6666-6666", "model": "Z3", "name": "Z-series 3"},
            {"serial": "Q2ZS-7777-7777", "model": "Z4", "name": "Z-series 4"},
            {"serial": "Q2MG-8888-8888", "model": "MG21", "name": "Cellular Gateway"},
        ]

    async def test_collect_device_performance_filters_vmx(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mixed_devices: list[dict[str, Any]],
    ) -> None:
        """Test that collect_device_performance excludes VMX devices."""
        # Track which serials get API calls
        called_serials: list[str] = []

        def track_perf_call(serial: str) -> dict[str, int]:
            called_serials.append(serial)
            return {"perfScore": 85}

        mock_api.appliance.getDeviceAppliancePerformance.side_effect = track_perf_call

        async def mock_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            await mx_collector.collect_device_performance(
                org_id="org123",
                org_name="Test Org",
                devices=mixed_devices,
            )

        # Verify only physical MX devices had API calls (not VMX, Z-series, or MG)
        assert "Q2MX-1111-1111" in called_serials  # MX100 - included
        assert "Q2MX-2222-2222" in called_serials  # MX250 - included
        assert "Q2MX-3333-3333" in called_serials  # MX450 - included
        assert "Q2VM-4444-4444" not in called_serials  # VMX100 - excluded
        assert "Q2VM-5555-5555" not in called_serials  # VMX-S - excluded
        assert "Q2ZS-6666-6666" not in called_serials  # Z3 - excluded
        assert "Q2ZS-7777-7777" not in called_serials  # Z4 - excluded
        assert "Q2MG-8888-8888" not in called_serials  # MG21 - excluded

    async def test_collect_device_performance_only_physical_mx(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that only devices starting with MX (not VMX) are processed."""
        devices = [
            {"serial": "Q2MX-AAAA-AAAA", "model": "MX84", "name": "MX 84"},
            {"serial": "Q2MX-BBBB-BBBB", "model": "MX64", "name": "MX 64"},
            {"serial": "Q2VM-CCCC-CCCC", "model": "VMX-M", "name": "VMX Medium"},
        ]

        call_count = 0

        def count_calls(*args: Any, **kwargs: Any) -> dict[str, int]:
            nonlocal call_count
            call_count += 1
            return {"perfScore": 75}

        mock_api.appliance.getDeviceAppliancePerformance.side_effect = count_calls

        async def mock_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            await mx_collector.collect_device_performance(
                org_id="org123",
                org_name="Test Org",
                devices=devices,
            )

        # Only 2 calls for MX84 and MX64, not 3 (VMX excluded)
        assert call_count == 2

    async def test_collect_loss_and_latency_includes_mx_mg_z(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
        mixed_devices: list[dict[str, Any]],
    ) -> None:
        """Test that collect_loss_and_latency includes MX, MG, and Z-series devices."""
        # Track which serials get API calls
        called_serials: list[str] = []

        # Mock API to track calls
        def track_call(serial: str, **kwargs: Any) -> list[dict[str, Any]]:
            called_serials.append(serial)
            return [{"lossPercent": 0.5, "latencyMs": 25.0}]

        mock_api.devices.getDeviceLossAndLatencyHistory.side_effect = track_call

        async def mock_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            await mx_collector.collect_loss_and_latency(
                org_id="org123",
                org_name="Test Org",
                devices=mixed_devices,
                destination_ip="8.8.8.8",
            )

        # Verify MX, MG, and Z-series devices were included
        # (loss/latency API is different from performance API)
        assert "Q2MX-1111-1111" in called_serials  # MX100 - included
        assert "Q2MX-2222-2222" in called_serials  # MX250 - included
        assert "Q2MX-3333-3333" in called_serials  # MX450 - included
        assert "Q2ZS-6666-6666" in called_serials  # Z3 - included
        assert "Q2ZS-7777-7777" in called_serials  # Z4 - included
        assert "Q2MG-8888-8888" in called_serials  # MG21 - included
        # VMX models start with "VMX", not "MX", so they're excluded
        assert "Q2VM-4444-4444" not in called_serials  # VMX100 - excluded (model=VMX100, not MX)
        assert "Q2VM-5555-5555" not in called_serials  # VMX-S - excluded (model=VMX-S, not MX)

    async def test_collect_device_performance_skips_ha_spare_devices(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that collect_device_performance skips warm spare HA devices."""
        devices = [
            {"serial": "Q2MX-PRIM-AAAA", "model": "MX67", "name": "Primary MX"},
            {"serial": "Q2MX-SPAR-BBBB", "model": "MX67", "name": "Spare MX"},
            {"serial": "Q2MX-SOLO-CCCC", "model": "MX67", "name": "Standalone MX"},
        ]

        # Set up uplink status cache with HA info
        mx_collector._uplink_status_cache = {
            "Q2MX-PRIM-AAAA": UplinkStatus(
                networkId="net1",
                serial="Q2MX-PRIM-AAAA",
                model="MX67",
                highAvailability=HighAvailability(enabled=True, role="primary"),
                uplinks=[],
            ),
            "Q2MX-SPAR-BBBB": UplinkStatus(
                networkId="net1",
                serial="Q2MX-SPAR-BBBB",
                model="MX67",
                highAvailability=HighAvailability(enabled=True, role="spare"),
                uplinks=[],
            ),
            "Q2MX-SOLO-CCCC": UplinkStatus(
                networkId="net2",
                serial="Q2MX-SOLO-CCCC",
                model="MX67",
                highAvailability=HighAvailability(enabled=False),
                uplinks=[],
            ),
        }

        # Track which serials get API calls
        called_serials: list[str] = []

        def track_perf_call(serial: str) -> dict[str, int]:
            called_serials.append(serial)
            return {"perfScore": 85}

        mock_api.appliance.getDeviceAppliancePerformance.side_effect = track_perf_call

        async def mock_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            await mx_collector.collect_device_performance(
                org_id="org123",
                org_name="Test Org",
                devices=devices,
            )

        # Verify primary and standalone devices had API calls, but not spare
        assert "Q2MX-PRIM-AAAA" in called_serials  # Primary - included
        assert "Q2MX-SPAR-BBBB" not in called_serials  # Spare - excluded
        assert "Q2MX-SOLO-CCCC" in called_serials  # Standalone (HA disabled) - included
        assert len(called_serials) == 2


class TestMXCollectorErrorHandling:
    """Test MX collector error handling and tracking."""

    @pytest.fixture
    def mock_api(self) -> MagicMock:
        """Create a mock API client."""
        api = MagicMock()
        api.appliance = MagicMock()
        api.devices = MagicMock()
        return api

    @pytest.fixture
    def mock_parent(self, mock_api: MagicMock) -> MagicMock:
        """Create a mock parent DeviceCollector."""
        parent = MagicMock()
        parent.api = mock_api
        parent.settings = MagicMock()
        parent.settings.api = MagicMock()
        parent.settings.api.concurrency_limit = 5
        parent._create_gauge = MagicMock(return_value=MagicMock())
        parent.rate_limiter = create_mock_rate_limiter()
        return parent

    @pytest.fixture
    def mx_collector(self, mock_parent: MagicMock) -> MXCollector:
        """Create MX collector instance."""
        collector = MXCollector(mock_parent)
        collector._mx_performance_score = MagicMock()
        return collector

    async def test_collect_device_performance_tracks_errors(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that performance collection tracks error types."""
        devices = [
            {"serial": "Q2MX-1111-1111", "model": "MX100", "name": "MX 100"},
            {"serial": "Q2MX-2222-2222", "model": "MX250", "name": "MX 250"},
            {"serial": "Q2MX-3333-3333", "model": "MX450", "name": "MX 450"},
        ]

        call_count = 0

        def alternating_response(*args: Any, **kwargs: Any) -> dict[str, int]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"perfScore": 85}
            elif call_count == 2:
                raise Exception("400 Bad Request - Device not supported")
            else:
                return {"perfScore": 90}

        mock_api.appliance.getDeviceAppliancePerformance.side_effect = alternating_response

        async def mock_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            # Should complete without raising
            await mx_collector.collect_device_performance(
                org_id="org123",
                org_name="Test Org",
                devices=devices,
            )

        # Verify all devices were attempted
        assert call_count == 3

    async def test_collect_loss_latency_handles_missing_uplinks(
        self,
        mx_collector: MXCollector,
        mock_api: MagicMock,
    ) -> None:
        """Test that loss/latency collection handles devices with missing uplinks."""
        mx_collector._mx_uplink_loss_percent = MagicMock()
        mx_collector._mx_uplink_latency_ms = MagicMock()
        mx_collector._mx_uplink_jitter_ms = MagicMock()
        mx_collector._mx_uplink_goodput_kbps = MagicMock()

        devices = [
            {"serial": "Q2MX-1111-1111", "model": "MX100", "name": "MX 100"},
        ]

        call_count = 0

        def uplink_response(serial: str, **kwargs: Any) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            uplink = kwargs.get("uplink", "")
            if uplink == "wan1":
                return [{"lossPercent": 0.5, "latencyMs": 25.0}]
            else:
                # Simulate other uplinks not being available
                raise Exception("400 Bad Request - Uplink not available")

        mock_api.devices.getDeviceLossAndLatencyHistory.side_effect = uplink_response

        async def mock_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        with patch(
            "meraki_dashboard_exporter.collectors.devices.mx.asyncio.to_thread",
            side_effect=mock_to_thread,
        ):
            # Should complete without raising
            await mx_collector.collect_loss_and_latency(
                org_id="org123",
                org_name="Test Org",
                devices=devices,
                destination_ip="8.8.8.8",
            )

        # Should have tried all three uplinks (wan1, wan2, cellular)
        assert call_count == 3
