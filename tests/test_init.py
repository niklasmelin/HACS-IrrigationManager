"""Tests for setup, actions, scheduling, lifecycle, and budget enforcement."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_CONFIG_ENTRY_ID
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solar_irrigation import _async_evaluate_automatic_irrigation
from custom_components.solar_irrigation.const import (
    CONF_IGNORE_RAIN,
    DOMAIN,
    PLATFORMS,
    SVC_RUN_NOW,
    ControllerStatus,
)
from custom_components.solar_irrigation.models import SolarIrrigationData


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that setup stores typed runtime objects on the config entry."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.solar_irrigation.SolarIrrigationCoordinator."
        "async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.coordinator is not None
    assert mock_config_entry.runtime_data.controller is not None
    assert mock_config_entry.runtime_data.cancel_schedule is not None
    assert mock_config_entry.runtime_data.remove_update_listener is not None


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test unloading releases platforms, callbacks, and controller safely."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.solar_irrigation.SolarIrrigationCoordinator."
        "async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_forwards_exact_platforms(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup forwards only the declared platform tuple."""
    mock_config_entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.solar_irrigation.SolarIrrigationCoordinator."
            "async_config_entry_first_refresh",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ) as forward_mock,
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    forward_mock.assert_awaited_once_with(mock_config_entry, PLATFORMS)


async def test_setup_failure_shuts_down_controller(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test partial setup cannot leave monitoring or an actuator event behind."""
    mock_config_entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.solar_irrigation.SolarIrrigationCoordinator."
            "async_config_entry_first_refresh",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(side_effect=RuntimeError("platform failure")),
        ),
        patch(
            "custom_components.solar_irrigation.SolarIrrigationController."
            "async_shutdown",
            new=AsyncMock(),
        ) as shutdown,
    ):
        assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)

    shutdown.assert_awaited_once()


async def test_monitoring_setup_failure_shuts_down_controller(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a listener setup failure still invokes controller cleanup."""
    mock_config_entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.solar_irrigation.SolarIrrigationCoordinator."
            "async_config_entry_first_refresh",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "custom_components.solar_irrigation.SolarIrrigationController."
            "async_start_monitoring",
            new=AsyncMock(side_effect=RuntimeError("listener failure")),
        ),
        patch(
            "custom_components.solar_irrigation.SolarIrrigationController."
            "async_shutdown",
            new=AsyncMock(),
        ) as shutdown,
    ):
        assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)

    shutdown.assert_awaited_once()


async def test_source_refresh_setup_failure_still_shuts_down_controller(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test actuator recovery occurs before a failing first source refresh."""
    mock_config_entry.add_to_hass(hass)
    order: list[str] = []

    async def load_controller(_self: object) -> None:
        """Record controller recovery before the first source refresh."""
        order.append("controller_load")

    async def fail_refresh(_self: object) -> None:
        """Fail after controller recovery has already secured the actuator."""
        order.append("coordinator_refresh")
        raise RuntimeError("source failure")

    with (
        patch(
            "custom_components.solar_irrigation.SolarIrrigationController.async_load",
            new=load_controller,
        ),
        patch(
            "custom_components.solar_irrigation.SolarIrrigationController."
            "async_start_monitoring",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.solar_irrigation.SolarIrrigationCoordinator."
            "async_config_entry_first_refresh",
            new=fail_refresh,
        ),
        patch(
            "custom_components.solar_irrigation.SolarIrrigationController."
            "async_shutdown",
            new=AsyncMock(),
        ) as shutdown,
    ):
        assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)

    assert order == ["controller_load", "coordinator_refresh"]
    shutdown.assert_awaited_once()


async def test_migrate_legacy_schedule_to_watering_window(
    hass: HomeAssistant,
    config_entry_data: dict[str, object],
) -> None:
    """Test migration of the legacy daily time into the window start."""
    from custom_components.solar_irrigation import async_migrate_entry
    from custom_components.solar_irrigation.const import (
        CONF_SCHEDULE_TIME,
        CONF_WATERING_WINDOW_END,
        CONF_WATERING_WINDOW_START,
        DEFAULT_WATERING_WINDOW_END,
    )

    legacy_data = dict(config_entry_data)
    legacy_data.pop(CONF_WATERING_WINDOW_START)
    legacy_data.pop(CONF_WATERING_WINDOW_END)
    legacy_data[CONF_SCHEDULE_TIME] = "06:30:00"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Legacy Irrigation",
        data=legacy_data,
        version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 4
    assert entry.options[CONF_WATERING_WINDOW_START] == "06:30:00"
    assert entry.options[CONF_WATERING_WINDOW_END] == DEFAULT_WATERING_WINDOW_END
    assert CONF_SCHEDULE_TIME not in entry.data


async def test_migrate_clamps_legacy_peak_demand_and_adds_pulse_defaults(
    hass: HomeAssistant,
    config_entry_data: dict[str, object],
) -> None:
    """Test version-2 entries are safe for the new number and pulse controls."""
    from custom_components.solar_irrigation import async_migrate_entry
    from custom_components.solar_irrigation.const import (
        CONF_MAX_PULSE_DURATION,
        CONF_MAX_RUNTIME,
        CONF_SOAK_DURATION,
        DEFAULT_MAX_PULSE_DURATION,
        DEFAULT_SOAK_DURATION,
        MIN_MAX_RUNTIME,
    )

    legacy_data = dict(config_entry_data)
    legacy_data[CONF_MAX_RUNTIME] = 2
    legacy_data.pop(CONF_MAX_PULSE_DURATION)
    legacy_data.pop(CONF_SOAK_DURATION)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Version 2 Irrigation",
        data=legacy_data,
        version=2,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 4
    assert entry.options[CONF_MAX_RUNTIME] == MIN_MAX_RUNTIME
    assert entry.options[CONF_MAX_PULSE_DURATION] == DEFAULT_MAX_PULSE_DURATION
    assert entry.options[CONF_SOAK_DURATION] == DEFAULT_SOAK_DURATION
    assert entry.unique_id == legacy_data["irrigation_entity"]


async def test_migration_rejects_duplicate_irrigation_entity(
    hass: HomeAssistant,
    config_entry_data: dict[str, object],
) -> None:
    """Test migration cannot normalize two entries onto the same actuator."""
    from custom_components.solar_irrigation import async_migrate_entry

    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Existing",
        unique_id="switch.irrigation_valve",
        data=config_entry_data,
        version=3,
    )
    legacy = MockConfigEntry(
        domain=DOMAIN,
        title="Legacy duplicate",
        unique_id="switch.old_irrigation_valve",
        data=config_entry_data,
        version=2,
    )
    existing.add_to_hass(hass)
    legacy.add_to_hass(hass)

    assert await async_migrate_entry(hass, legacy) is False
    assert legacy.version == 2
    assert legacy.unique_id == "switch.old_irrigation_valve"


def _evaluation_entry(
    mock_config_entry: MockConfigEntry,
    *,
    runtime_seconds: int,
    delivered_seconds: int,
    running: bool = False,
    refresh_success: bool = True,
) -> tuple[MockConfigEntry, MagicMock, MagicMock]:
    """Attach mocked runtime objects for periodic-evaluation unit tests."""
    controller = MagicMock()
    controller.is_running = running
    controller.async_prepare_for_evaluation = AsyncMock()
    controller.async_set_status = AsyncMock()
    controller.async_run = AsyncMock(return_value=True)
    controller.delivered_today_seconds.return_value = delivered_seconds
    coordinator = MagicMock()
    coordinator.data = SolarIrrigationData(
        actual_solar_kwh=30,
        remaining_solar_kwh=35,
        expected_solar_kwh=65,
        solar_factor=1,
        rain_mm=None,
        rain_factor=1,
        runtime_minutes=runtime_seconds / 60,
        runtime_seconds=runtime_seconds,
        skip_reason=None,
        calculated_at=datetime.now(UTC),
        solar_sample_count=8,
    )
    coordinator.last_update_success = refresh_success
    coordinator.last_exception = RuntimeError("source failed")
    coordinator.async_request_refresh = AsyncMock()
    mock_config_entry.runtime_data = SimpleNamespace(
        controller=controller,
        coordinator=coordinator,
    )
    return mock_config_entry, controller, coordinator


async def test_periodic_evaluation_starts_only_amount_due(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test target-to-date minus all delivered water determines the next event."""
    entry, controller, _ = _evaluation_entry(
        mock_config_entry,
        runtime_seconds=600,
        delivered_seconds=120,
    )
    with (
        patch(
            "custom_components.solar_irrigation.is_within_watering_window",
            return_value=True,
        ),
        patch("custom_components.solar_irrigation.delivery_progress", return_value=0.5),
    ):
        await _async_evaluate_automatic_irrigation(
            hass,
            entry,
            datetime(2026, 7, 23, 12, 0, tzinfo=UTC),
        )

    controller.async_run.assert_awaited_once_with(
        3,
        automatic=True,
        ignore_rain=False,
    )


async def test_periodic_evaluation_never_overlaps_active_cycle(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test a run or soak cycle blocks every later timer evaluation."""
    entry, controller, coordinator = _evaluation_entry(
        mock_config_entry,
        runtime_seconds=600,
        delivered_seconds=0,
        running=True,
    )
    with patch(
        "custom_components.solar_irrigation.is_within_watering_window",
        return_value=True,
    ):
        await _async_evaluate_automatic_irrigation(
            hass,
            entry,
            datetime(2026, 7, 23, 12, 0, tzinfo=UTC),
        )

    coordinator.async_request_refresh.assert_not_awaited()
    controller.async_run.assert_not_awaited()


async def test_manual_delivery_suppresses_not_yet_due_automatic_water(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test manual pump time counts against the same target and daily budget."""
    entry, controller, _ = _evaluation_entry(
        mock_config_entry,
        runtime_seconds=600,
        delivered_seconds=400,
    )
    with (
        patch(
            "custom_components.solar_irrigation.is_within_watering_window",
            return_value=True,
        ),
        patch("custom_components.solar_irrigation.delivery_progress", return_value=0.5),
    ):
        await _async_evaluate_automatic_irrigation(
            hass,
            entry,
            datetime(2026, 7, 23, 12, 0, tzinfo=UTC),
        )

    controller.async_run.assert_not_awaited()
    controller.async_set_status.assert_awaited_with(
        ControllerStatus.WAITING_FOR_PULSE,
        decision_reason="waiting_for_water_demand",
        clear_error=True,
    )


async def test_periodic_evaluation_respects_remaining_daily_cap(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the event requested at a tick cannot exceed remaining daily budget."""
    entry, controller, _ = _evaluation_entry(
        mock_config_entry,
        runtime_seconds=600,
        delivered_seconds=500,
    )
    with (
        patch(
            "custom_components.solar_irrigation.is_within_watering_window",
            return_value=True,
        ),
        patch("custom_components.solar_irrigation.delivery_progress", return_value=1.0),
    ):
        await _async_evaluate_automatic_irrigation(
            hass,
            entry,
            datetime(2026, 7, 23, 21, 45, tzinfo=UTC),
        )

    controller.async_run.assert_awaited_once_with(
        100 / 60,
        automatic=True,
        ignore_rain=False,
    )


async def test_source_failure_sets_visible_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test failed automatic source refresh records a human-readable error."""
    entry, controller, _ = _evaluation_entry(
        mock_config_entry,
        runtime_seconds=600,
        delivered_seconds=0,
        refresh_success=False,
    )
    with patch(
        "custom_components.solar_irrigation.is_within_watering_window",
        return_value=True,
    ):
        await _async_evaluate_automatic_irrigation(
            hass,
            entry,
            datetime(2026, 7, 23, 12, 0, tzinfo=UTC),
        )

    controller.async_set_status.assert_awaited_with(
        ControllerStatus.ERROR,
        decision_reason="source_data_unavailable",
        error_message="Source data unavailable: source failed",
    )
    controller.async_run.assert_not_awaited()


async def test_run_now_uses_human_friendly_config_entry_target(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the action accepts the config-entry selector field."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.solar_irrigation.SolarIrrigationCoordinator."
        "async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    controller = mock_config_entry.runtime_data.controller
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.async_request_refresh = AsyncMock()
    coordinator.last_update_success = True
    controller.async_run = AsyncMock(return_value=True)

    await hass.services.async_call(
        DOMAIN,
        SVC_RUN_NOW,
        {
            ATTR_CONFIG_ENTRY_ID: mock_config_entry.entry_id,
            "duration": 2,
            CONF_IGNORE_RAIN: True,
        },
        blocking=True,
    )

    controller.async_run.assert_awaited_once_with(
        2,
        automatic=False,
        ignore_rain=True,
    )


async def test_run_now_ignore_rain_survives_failed_full_refresh(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test an unavailable rain source does not block the dry manual path."""
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.solar_irrigation.SolarIrrigationCoordinator."
        "async_config_entry_first_refresh",
        new=AsyncMock(return_value=None),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    controller = mock_config_entry.runtime_data.controller
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.async_request_refresh = AsyncMock()
    coordinator.last_update_success = False
    controller.async_run = AsyncMock(return_value=True)

    await hass.services.async_call(
        DOMAIN,
        SVC_RUN_NOW,
        {
            ATTR_CONFIG_ENTRY_ID: mock_config_entry.entry_id,
            CONF_IGNORE_RAIN: True,
        },
        blocking=True,
    )

    controller.async_run.assert_awaited_once_with(
        None,
        automatic=False,
        ignore_rain=True,
    )
