# Stellio Data Exploration

This project contains scripts for exploring and processing temperature and humidity sensor data using the Stellio NGSI-LD Context Broker.

## Overview

The project provides three main scripts for interacting with Stellio Context Broker:

1. **explore_stellio_data.py** - General data exploration and inspection
2. **temp_humidity_sensor_updater.py** - Process GeoJSON files and create/update TempHumiditySensor entities
3. **fetch_temp_humidity_sensors.py** - Fetch existing sensor data in various formats

## Getting Started

### Prerequisites

- Python 3.12 or 3.13
- Stellio Context Broker access credentials (client ID and secret)

### Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   # Create virtual environment with uv
   uv venv
   
   # Activate virtual environment
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   
   # Install dependencies from pyproject.toml
   uv pip install -U -r pyproject.toml --extra dev

   # Install pre-commit hooks if you are planning to modify the code
   pre-commit install
   ```

## Usage Examples

### Explore Stellio Data
```bash
python exploration/explore_stellio_data.py --client-id <id> --client-secret <secret>
```

### Update Temperature and Humidity Sensors
```bash
python exploration/temp_humidity_sensor_updater.py --geojson https://bri3.fvh.io/opendata/r4c/r4c_all_latest.geojson https://bri3.fvh.io/opendata/makelankatu/makelankatu_latest.geojson --client-id <id> --client-secret <secret> --verify-upsert
```

### Fetch Sensor Data
```bash
python exploration/fetch_temp_humidity_sensors.py --client-id <id> --client-secret <secret> --output-format csv
```

## Project Structure

- `exploration/` - Main scripts for data processing and exploration
- `data/` - Data storage directory
  - `raw/` - Raw data files and access tokens
  - `samples/` - Sample data files for testing
- `output/` - Generated output files

## Features

- **NGSI-LD Compliance**: All entities follow NGSI-LD standards
- **Multiple Data Sources**: Support for local files and remote URLs
- **Flexible Output Formats**: CSV, JSON, and brief summary formats
- **Error Handling**: Comprehensive error handling with retry logic
- **Dry-run Mode**: Test functionality without making actual API calls
- **Authentication**: OAuth2 token management for Stellio Context Broker

## Notes

- All scripts require valid Stellio Context Broker credentials
- The project uses OAuth2 authentication with automatic token refresh
- Sensor entities are created as type `TempHumiditySensor` with NGSI-LD compliant structure
- GeoJSON processing supports both temperature and humidity measurements with timestamps
