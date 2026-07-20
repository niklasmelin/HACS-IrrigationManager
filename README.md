# Solar Irrigation Integration

A Home Assistant custom integration that automatically determines the required irrigation duration based on solar energy production.

## Functionality

This integration calculates irrigation runtime based on solar energy available during the day:
- Uses actual and forecast solar energy production as the indicator
- Calculates a scale factor relative to maximum expected solar production
- Determines irrigation duration and automatically controls irrigation
- Exposes intermediate values as sensors for monitoring

## Required Inputs

### Configuration Parameters

1. **Solar Energy Today Sensor** - Actual produced PV energy today (e.g., `sensor.solar_energy_today`)
   - Unit: kWh
   - Mandatory

2. **Remaining Solar Production Sensor** - Forecast remaining PV production today (e.g., `sensor.remaining_solar_today`)
   - Unit: kWh  
   - Mandatory

3. **Irrigation Switch Entity** - Controls irrigation pump (e.g., `switch.irrigation_pump`)
   - Mandatory

4. **Maximum Daily Solar Production** - Represents an exceptionally sunny day (default: 65 kWh)
   - Unit: kWh
   - Mandatory

5. **Maximum Irrigation Runtime** - Watering required during a perfect sunny day (default: 60 minutes)
   - Unit: minutes
   - Mandatory

6. **Update Interval** - How often to recalculate irrigation duration (default: 1 hour)
   - Unit: seconds
   - Optional

## Sensors Exposed

- `expected_solar_today` - Total expected solar energy for the day (kWh)
- `solar_scale_factor` - Scale factor (0.0-1.0) 
- `irrigation_runtime` - Calculated irrigation runtime (minutes)
- `irrigation_runtime_seconds` - Calculated irrigation runtime (seconds)
- `irrigation_status` - Current status (Idle, Scheduled, Running, Completed)

## Services

- `solar_irrigation.run_now` - Run irrigation immediately with latest calculated runtime
- `solar_irrigation.stop` - Stop irrigation immediately

## Installation

Place this integration in your Home Assistant `custom_components` directory.

## Usage

1. Configure the integration with the required sensors and entities
2. The integration will automatically calculate and schedule irrigation
3. Monitor the sensors for real-time data
4. Use services to manually run or stop irrigation