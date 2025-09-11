#!/usr/bin/env python3
"""
Temperature and Humidity Sensor Data Fetcher for Stellio NGSI-LD Context Broker

This script fetches all TempHumiditySensor entities and their temporal measurement data
from Stellio Context Broker and displays the results in a readable format.

Features:
- Fetch all TempHumiditySensor entities from Stellio
- Display basic metadata (ID, location, address, name, etc.)
- Fetch configurable number of latest temporal measurements per sensor
- Multiple output formats: brief, CSV, and original NGSI-LD JSON
- Configurable logging verbosity (warnings+ by default, full debug with --verbose)
- Support for dry-run mode to test authentication without fetching data

Usage Examples:
    # Fetch all sensors with default brief format
    python fetch_temp_humidity_sensors.py --client-id YOUR_ID --client-secret YOUR_SECRET

    # Fetch all sensors with CSV output format
    python fetch_temp_humidity_sensors.py --client-id YOUR_ID --client-secret YOUR_SECRET --output-format csv

    # Fetch all sensors with original NGSI-LD JSON format
    python fetch_temp_humidity_sensors.py --client-id YOUR_ID --client-secret YOUR_SECRET --output-format ngsi

    # Fetch all sensors with 10 latest measurements per sensor
    python fetch_temp_humidity_sensors.py --client-id YOUR_ID --client-secret YOUR_SECRET --limit 10

    # Test authentication without fetching data
    python fetch_temp_humidity_sensors.py --client-id YOUR_ID --client-secret YOUR_SECRET --dry-run

    # Fetch specific sensor by ID
    python fetch_temp_humidity_sensors.py --client-id YOUR_ID --client-secret YOUR_SECRET --sensor-id urn:ngsi-ld:TempHumiditySensor:12345
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import Stellio client components
from stellio_client import StellioClient, StellioTokenManager


# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Fetch TempHumiditySensor entities and their temporal data from Stellio NGSI-LD Context Broker"
    )

    parser.add_argument("--client-id", type=str, help="OAuth2 Client ID for Stellio authentication")

    parser.add_argument("--client-secret", type=str, help="OAuth2 Client Secret for Stellio authentication")

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of latest temporal measurements to fetch per sensor (default: 5)",
    )

    parser.add_argument(
        "--sensor-id",
        type=str,
        help="Specific sensor ID to fetch. If not provided, all TempHumiditySensor entities will be fetched.",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Test authentication and list entities without fetching temporal data"
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    parser.add_argument(
        "--output-format",
        type=str,
        choices=["brief", "csv", "ngsi"],
        default="brief",
        help="Output format: brief (default), csv, or ngsi",
    )

    parser.add_argument(
        "--stellio-base-url",
        type=str,
        default="https://sedimark-helsinki.stellio.io",
        help="Stellio NGSI-LD Context Broker base URL",
    )

    parser.add_argument(
        "--stellio-tenant",
        type=str,
        default="urn:ngsi-ld:tenant:sedimark-helsinki",
        help="NGSI-LD tenant identifier for Stellio",
    )

    parser.add_argument(
        "--token-file",
        type=str,
        default="data/raw/access_token.json",
        help="Path to store/load Stellio access token",
    )

    parser.add_argument(
        "--no-temporal",
        action="store_true",
        help="Skip fetching temporal data, only show entity metadata",
    )

    args = parser.parse_args()
    return args


def setup_stellio_client(args) -> StellioClient:
    """
    Setup and initialize Stellio client with authentication

    Args:
        args: Parsed command line arguments

    Returns:
        Configured StellioClient instance

    Raises:
        Exception: If authentication fails
    """
    logger.info("🔑 Setting up Stellio authentication...")

    # Check for required credentials
    if not args.client_id or not args.client_secret:
        raise ValueError("Client ID and Client Secret are required for Stellio authentication")

    # Setup token manager
    token_file = Path(args.token_file)
    token_manager = StellioTokenManager(token_file)

    # Get or refresh token
    access_token = token_manager.get_or_refresh_token(args.client_id, args.client_secret)
    if not access_token:
        raise Exception("Failed to obtain Stellio access token")

    # Create Stellio client
    stellio_client = StellioClient(
        base_url=args.stellio_base_url,
        access_token=access_token,
        tenant=args.stellio_tenant,
        client_id=args.client_id,
        client_secret=args.client_secret,
        token_manager=token_manager,
    )

    logger.info("✅ Stellio client configured successfully")
    return stellio_client


def fetch_temp_humidity_sensors(
    stellio_client: StellioClient, sensor_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch TempHumiditySensor entities from Stellio

    Args:
        stellio_client: Configured Stellio client
        sensor_id: Optional specific sensor ID to fetch

    Returns:
        List of TempHumiditySensor entities
    """
    logger.info("🌡️ Fetching TempHumiditySensor entities...")

    try:
        if sensor_id:
            # Fetch specific sensor
            logger.info(f"📍 Fetching specific sensor: {sensor_id}")
            entity = stellio_client.get_entity(sensor_id)
            if entity:
                return [entity]
            else:
                logger.warning(f"⚠️ Sensor not found: {sensor_id}")
                return []
        else:
            # Fetch all TempHumiditySensor entities
            entities = stellio_client.get_entities_by_type("TempHumiditySensor")
            if entities:
                logger.info(f"✅ Found {len(entities)} TempHumiditySensor entities")
                return entities
            else:
                logger.warning("⚠️ No TempHumiditySensor entities found")
                return []

    except Exception as e:
        logger.error(f"❌ Error fetching sensors: {e}")
        return []


def fetch_temporal_data(stellio_client: StellioClient, entity_id: str, limit: int = 5) -> Optional[Dict[str, Any]]:
    """
    Fetch temporal measurement data for a sensor

    Args:
        stellio_client: Configured Stellio client
        entity_id: Entity ID to fetch temporal data for
        limit: Number of latest measurements to include (not directly supported by API, but used for display)

    Returns:
        Temporal data dictionary or None if failed
    """
    try:
        logger.debug(f"📊 Fetching temporal data for: {entity_id}")
        temporal_data = stellio_client.get_temporal_data(entity_id)
        return temporal_data
    except Exception as e:
        logger.error(f"❌ Error fetching temporal data for {entity_id}: {e}")
        return None


def display_sensor_info(entity: Dict[str, Any]):
    """
    Display basic sensor information in readable format

    Args:
        entity: NGSI-LD entity dictionary
    """
    entity_id = entity.get("id", "N/A")
    logger.info(f"\n📍 Sensor: {entity_id}")

    # Display location
    if "location" in entity:
        location = entity["location"]
        if isinstance(location, dict) and "value" in location:
            coordinates = location["value"].get("coordinates", "N/A")
            logger.info(f"  🗺️ Location: {coordinates}")

    # Display address
    if "address" in entity:
        address = entity["address"]
        if isinstance(address, dict) and "value" in address:
            street_address = address["value"].get("streetAddress", "N/A")
            locality = address["value"].get("addressLocality", "")
            logger.info(f"  🏠 Address: {street_address}, {locality}")

    # Display name
    if "name" in entity:
        name = entity["name"]
        if isinstance(name, dict) and "value" in name:
            logger.info(f"  📝 Name: {name['value']}")

    # Display sensor number
    if "sensorNumber" in entity:
        sensor_number = entity["sensorNumber"]
        if isinstance(sensor_number, dict) and "value" in sensor_number:
            logger.info(f"  🔢 Sensor Number: {sensor_number['value']}")

    # Display district
    if "district" in entity:
        district = entity["district"]
        if isinstance(district, dict) and "value" in district:
            logger.info(f"  🏘️ District: {district['value']}")

    # Display installation date
    if "dateInstalled" in entity:
        date_installed = entity["dateInstalled"]
        if isinstance(date_installed, dict) and "value" in date_installed:
            logger.info(f"  📅 Date Installed: {date_installed['value']}")


def display_temporal_measurements(entity_id: str, temporal_data: Dict[str, Any], limit: int = 5):
    """
    Display temporal measurements in readable format

    Args:
        entity_id: Entity ID
        temporal_data: Temporal data from Stellio
        limit: Maximum number of measurements to display
    """
    logger.info(f"  📈 Latest {limit} measurements:")

    # Handle different temporal data formats
    if isinstance(temporal_data, list) and len(temporal_data) > 0:
        entity_data = temporal_data[0]
    elif isinstance(temporal_data, dict):
        entity_data = temporal_data
    else:
        logger.info("    ⚠️ No temporal data available")
        return

    # Display temperature measurements
    if "temperature" in entity_data:
        temp_attr = entity_data["temperature"]
        temp_values = []

        if isinstance(temp_attr, dict) and "values" in temp_attr:
            temp_values = temp_attr["values"]
        elif isinstance(temp_attr, list):
            temp_values = temp_attr

        if temp_values:
            logger.info(f"    🌡️ Temperature ({len(temp_values)} total measurements):")
            for i, measurement in enumerate(temp_values[-limit:]):  # Show latest measurements
                if isinstance(measurement, dict):
                    value = measurement.get("value", "N/A")
                    observed_at = measurement.get("observedAt", "N/A")
                    logger.info(f"      {i + 1}. {value}°C at {observed_at}")
        else:
            logger.info("    🌡️ Temperature: No measurements found")

    # Display humidity measurements
    if "humidity" in entity_data:
        humidity_attr = entity_data["humidity"]
        humidity_values = []

        if isinstance(humidity_attr, dict) and "values" in humidity_attr:
            humidity_values = humidity_attr["values"]
        elif isinstance(humidity_attr, list):
            humidity_values = humidity_attr

        if humidity_values:
            logger.info(f"    💧 Humidity ({len(humidity_values)} total measurements):")
            for i, measurement in enumerate(humidity_values[-limit:]):  # Show latest measurements
                if isinstance(measurement, dict):
                    value = measurement.get("value", "N/A")
                    observed_at = measurement.get("observedAt", "N/A")
                    logger.info(f"      {i + 1}. {value}% at {observed_at}")
        else:
            logger.info("    💧 Humidity: No measurements found")


def extract_sensor_data(entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract basic sensor information from NGSI-LD entity

    Args:
        entity: NGSI-LD entity dictionary

    Returns:
        Dictionary with extracted sensor data
    """
    entity_id = entity.get("id", "N/A")

    # Extract location
    location = "N/A"
    if "location" in entity and isinstance(entity["location"], dict) and "value" in entity["location"]:
        coordinates = entity["location"]["value"].get("coordinates", "N/A")
        if isinstance(coordinates, list) and len(coordinates) >= 2:
            location = f"[{coordinates[0]}, {coordinates[1]}]"

    # Extract name
    name = "N/A"
    if "name" in entity and isinstance(entity["name"], dict) and "value" in entity["name"]:
        name = entity["name"]["value"]

    # Extract address
    address = "N/A"
    if "address" in entity and isinstance(entity["address"], dict) and "value" in entity["address"]:
        street_address = entity["address"]["value"].get("streetAddress", "")
        locality = entity["address"]["value"].get("addressLocality", "")
        if street_address or locality:
            address = f"{street_address}, {locality}".strip(", ")

    return {"id": entity_id, "location": location, "name": name, "address": address}


def extract_latest_measurements(temporal_data: Dict[str, Any], limit: int = 1) -> List[Dict[str, Any]]:
    """
    Extract latest temperature and humidity measurements from temporal data

    Args:
        temporal_data: Temporal data from Stellio
        limit: Number of latest measurements to extract

    Returns:
        List of measurement dictionaries
    """
    measurements = []

    # Handle different temporal data formats
    if isinstance(temporal_data, list) and len(temporal_data) > 0:
        entity_data = temporal_data[0]
    elif isinstance(temporal_data, dict):
        entity_data = temporal_data
    else:
        return measurements

    # Get temperature values
    temp_values = []
    if "temperature" in entity_data:
        temp_attr = entity_data["temperature"]
        if isinstance(temp_attr, dict) and "values" in temp_attr:
            temp_values = temp_attr["values"]
        elif isinstance(temp_attr, list):
            temp_values = temp_attr

    # Get humidity values
    humidity_values = []
    if "humidity" in entity_data:
        humidity_attr = entity_data["humidity"]
        if isinstance(humidity_attr, dict) and "values" in humidity_attr:
            humidity_values = humidity_attr["values"]
        elif isinstance(humidity_attr, list):
            humidity_values = humidity_attr

    # Combine measurements by timestamp
    measurement_dict = {}

    # Add temperature measurements
    for temp in temp_values[-limit:]:
        if isinstance(temp, dict):
            timestamp = temp.get("observedAt", "N/A")
            if timestamp not in measurement_dict:
                measurement_dict[timestamp] = {}
            measurement_dict[timestamp]["temperature"] = temp.get("value", "N/A")
            measurement_dict[timestamp]["time"] = timestamp

    # Add humidity measurements
    for humidity in humidity_values[-limit:]:
        if isinstance(humidity, dict):
            timestamp = humidity.get("observedAt", "N/A")
            if timestamp not in measurement_dict:
                measurement_dict[timestamp] = {}
            measurement_dict[timestamp]["humidity"] = humidity.get("value", "N/A")
            measurement_dict[timestamp]["time"] = timestamp

    # Convert to list and sort by timestamp (latest first)
    measurements = list(measurement_dict.values())
    measurements.sort(key=lambda x: x.get("time", ""), reverse=True)

    return measurements[:limit]


def print_brief_format(entity: Dict[str, Any], temporal_data: Dict[str, Any] = None):
    """
    Print sensor data in brief format

    Args:
        entity: NGSI-LD entity dictionary
        temporal_data: Optional temporal data
    """
    sensor_data = extract_sensor_data(entity)
    print(f"{sensor_data['id']}, {sensor_data['location']}, {sensor_data['name']}")

    if temporal_data:
        measurements = extract_latest_measurements(temporal_data, limit=1)
        if measurements:
            measurement = measurements[0]
            temp = measurement.get("temperature", "N/A")
            humidity = measurement.get("humidity", "N/A")
            timestamp = measurement.get("time", "N/A")
            print(f"time:{timestamp}, temperature:{temp}°C, humidity:{humidity}%")
        else:
            print("No measurements available")
    else:
        print("No temporal data available")


def print_csv_format(entities_with_data: List[tuple], print_header: bool = True):
    """
    Print sensor data in CSV format

    Args:
        entities_with_data: List of (entity, temporal_data) tuples
        print_header: Whether to print CSV header
    """
    if print_header:
        print("id,time,temperature,humidity,name")

    for entity, temporal_data in entities_with_data:
        sensor_data = extract_sensor_data(entity)

        if temporal_data:
            measurements = extract_latest_measurements(temporal_data, limit=1)
            if measurements:
                measurement = measurements[0]
                temp = measurement.get("temperature", "N/A")
                humidity = measurement.get("humidity", "N/A")
                timestamp = measurement.get("time", "N/A")
                print(f'"{sensor_data["id"]}","{timestamp}","{temp}","{humidity}","{sensor_data["name"]}"')
            else:
                print(f'"{sensor_data["id"]}","N/A","N/A","N/A","{sensor_data["name"]}"')
        else:
            print(f'"{sensor_data["id"]}","N/A","N/A","N/A","{sensor_data["name"]}"')


def print_ngsi_format(entity: Dict[str, Any]):
    """
    Print sensor data in NGSI format (original JSON with 2-space indentation)

    Args:
        entity: NGSI-LD entity dictionary
    """
    print(json.dumps(entity, indent=2, ensure_ascii=False))


def main():
    """Main function"""
    args = parse_args()

    # Configure logging based on verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        # Only show warnings and errors when not in verbose mode
        logging.getLogger().setLevel(logging.WARNING)

    logger.info("🌡️ Temperature & Humidity Sensor Data Fetcher")
    logger.info("=" * 55)

    try:
        # Setup Stellio client
        stellio_client = setup_stellio_client(args)

        # Fetch sensor entities
        sensors = fetch_temp_humidity_sensors(stellio_client, args.sensor_id)

        if not sensors:
            logger.warning("⚠️ No sensors found")
            return

        logger.info(f"\n📊 Processing {len(sensors)} sensor(s)...")

        # Collect all sensor data for batch processing (needed for CSV format)
        sensors_with_data = []

        # Process each sensor
        for i, sensor in enumerate(sensors, 1):
            entity_id = sensor.get("id", f"sensor_{i}")
            logger.info(f"\n🔄 Processing sensor {i}/{len(sensors)}")

            temporal_data = None

            # Fetch temporal data unless disabled
            if not args.no_temporal and not args.dry_run:
                temporal_data = fetch_temporal_data(stellio_client, entity_id, args.limit)
                if not temporal_data:
                    logger.warning(f"⚠️ No temporal data available for {entity_id}")
            elif args.dry_run:
                logger.info("  🔍 [DRY RUN] Temporal data fetch skipped")
            elif args.no_temporal:
                logger.info("  ⏭️ Temporal data fetch disabled")

            # Store data for output formatting
            sensors_with_data.append((sensor, temporal_data))

            # For non-CSV formats, output immediately
            if args.output_format == "brief":
                print_brief_format(sensor, temporal_data)
            elif args.output_format == "ngsi":
                print_ngsi_format(sensor)

        # For CSV format, output all at once with header
        if args.output_format == "csv":
            print_csv_format(sensors_with_data, print_header=True)

        # Summary
        logger.info(f"\n✅ Successfully processed {len(sensors)} sensor(s)")

        if args.dry_run:
            logger.info("\n🔍 Dry run completed - temporal data was not fetched")
            logger.info("💡 Remove --dry-run flag to fetch temporal measurements")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
