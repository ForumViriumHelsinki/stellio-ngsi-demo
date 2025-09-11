#!/usr/bin/env python3
"""
Temperature and Humidity Sensor Data Updater for Stellio NGSI-LD Context Broker

This script processes GeoJSON files containing temperature and humidity sensor data
and creates/updates the corresponding TempHumiditySensor entities in Stellio Context Broker.

Features:
- Parse GeoJSON files from local paths or URLs
- Extract sensor metadata (id, geometry, street address, installation date, etc.)
- Extract measurement data (temperature, humidity, timestamp)
- Format data as NGSI-LD compliant TempHumiditySensor entities
- Create/update entities in Stellio Context Broker with authentication
- Comprehensive error handling and retry logic with exponential backoff
- Dry-run mode for testing without sending data to Stellio

NGSI-LD Entity Structure:
- Entity ID: urn:ngsi-ld:TempHumiditySensor:{sensor_id}
- Entity Type: TempHumiditySensor
- Properties: location (GeoProperty), address, name, dateInstalled, sensorNumber, district
- Measurements: temperature (°C), humidity (%) with observedAt timestamps

Usage Examples:
    # Test with dry-run (no Stellio connection needed)
    python temp_humidity_sensor_updater.py --geojson data/samples/test_sensors.geojson --dry-run --verbose

    # Process real data from URL
    python temp_humidity_sensor_updater.py --geojson https://example.com/sensors.geojson --client-id YOUR_ID --client-secret YOUR_SECRET

    # Process multiple sources
    python temp_humidity_sensor_updater.py --geojson sensors1.geojson --geojson https://example.com/sensors2.geojson --client-id YOUR_ID --client-secret YOUR_SECRET
"""

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

# Import Stellio client components
from stellio_client import StellioClient, StellioTokenManager


# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Update TempHumiditySensor entities in Stellio NGSI-LD Context Broker from GeoJSON data"
    )

    parser.add_argument(
        "--geojson",
        type=str,
        nargs="+",
        required=True,
        help="Path to GeoJSON file or URL. Multiple files can be specified.",
    )
    parser.add_argument(
        "--device-id",
        type=str,
        nargs="+",
        help="Specific device ID(s) to process. Can be specified multiple times. If not provided, all devices will be processed.",
    )

    parser.add_argument("--client-id", type=str, help="OAuth2 Client ID for Stellio authentication")

    parser.add_argument("--client-secret", type=str, help="OAuth2 Client Secret for Stellio authentication")

    parser.add_argument(
        "--dry-run", action="store_true", help="Parse and validate data without updating Stellio broker"
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

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

    parser.add_argument("--max-retries", type=int, default=3, help="Maximum number of retries for Stellio operations")

    parser.add_argument(
        "--verify-upsert", action="store_true", help="Verify upserted entities by fetching their temporal data"
    )

    parser.add_argument(
        "--verify-limit",
        type=int,
        default=5,
        help="Number of latest measurements to fetch when verifying (default: 5)",
    )

    args = parser.parse_args()
    return args


def is_url(string: str) -> bool:
    """Check if string is a valid URL"""
    try:
        result = urlparse(string)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def fetch_geojson_from_url(url: str) -> Dict[str, Any]:
    """
    Fetch GeoJSON data from URL

    Args:
        url: URL to GeoJSON file

    Returns:
        Parsed GeoJSON data as dictionary

    Raises:
        Exception: If fetching or parsing fails
    """
    logger.info(f"📡 Fetching GeoJSON from URL: {url}")

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            response.raise_for_status()

            geojson_data = response.json()
            logger.info(f"✅ Successfully fetched GeoJSON from {url}")
            return geojson_data

    except httpx.HTTPStatusError as e:
        logger.error(f"❌ HTTP error fetching {url}: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON decode error for {url}: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching GeoJSON from {url}: {e}")
        raise


def load_geojson_from_file(file_path: str) -> Dict[str, Any]:
    """
    Load GeoJSON data from local file

    Args:
        file_path: Path to local GeoJSON file

    Returns:
        Parsed GeoJSON data as dictionary

    Raises:
        Exception: If loading or parsing fails
    """
    logger.info(f"📁 Loading GeoJSON from file: {file_path}")

    try:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"GeoJSON file not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)

        logger.info(f"✅ Successfully loaded GeoJSON from {file_path}")
        return geojson_data

    except FileNotFoundError as e:
        logger.error(f"❌ File not found: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON decode error for {file_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Error loading GeoJSON from {file_path}: {e}")
        raise


def fetch_geojson_data(source: str) -> Dict[str, Any]:
    """
    Fetch GeoJSON data from either URL or local file

    Args:
        source: URL or file path to GeoJSON data

    Returns:
        Parsed GeoJSON data as dictionary
    """
    if is_url(source):
        return fetch_geojson_from_url(source)
    else:
        return load_geojson_from_file(source)


def validate_geojson_structure(geojson_data: Dict[str, Any]) -> bool:
    """
    Validate that GeoJSON has expected structure

    Args:
        geojson_data: Parsed GeoJSON data

    Returns:
        True if structure is valid, False otherwise
    """
    required_fields = ["type", "features"]

    for field in required_fields:
        if field not in geojson_data:
            logger.error(f"❌ Missing required field in GeoJSON: {field}")
            return False

    if geojson_data["type"] != "FeatureCollection":
        logger.error(f"❌ Expected FeatureCollection, got: {geojson_data['type']}")
        return False

    if not isinstance(geojson_data["features"], list):
        logger.error("❌ Features should be a list")
        return False

    logger.info("✅ GeoJSON structure validation passed")
    return True


def extract_sensor_data(feature: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract sensor data from GeoJSON feature

    Args:
        feature: GeoJSON feature object

    Returns:
        Dictionary with extracted sensor data
    """
    try:
        # Extract basic feature data
        sensor_data = {"id": feature.get("id"), "geometry": feature.get("geometry"), "properties": {}}

        # Extract properties
        properties = feature.get("properties", {})

        # Extract street address
        if "street" in properties:
            sensor_data["properties"]["street"] = properties["street"]
        elif "field_4" in properties:  # Fallback to field_4 which seems to contain address
            sensor_data["properties"]["street"] = properties["field_4"]

        # Extract measurement data
        measurement = properties.get("measurement", {})
        if measurement:
            sensor_data["measurement"] = {
                "time": measurement.get("time"),
                "temperature": measurement.get("temperature"),
                "humidity": measurement.get("humidity"),
            }

        # Extract additional useful metadata
        for field in ["name", "Date_installed", "Sensor_number", "district"]:
            if field in properties:
                sensor_data["properties"][field] = properties[field]

        return sensor_data

    except Exception as e:
        logger.error(f"❌ Error extracting sensor data from feature: {e}")
        return None


def process_geojson_features(geojson_data: Dict[str, Any], device_ids: List[str] = None) -> List[Dict[str, Any]]:
    """
    Process all features in GeoJSON and extract sensor data

    Args:
        geojson_data: Parsed GeoJSON data

    Returns:
        List of extracted sensor data dictionaries
    """
    logger.info("🔄 Processing GeoJSON features...")

    features = geojson_data.get("features", [])
    processed_sensors = []

    for i, feature in enumerate(features, 1):
        logger.info(f"📍 Processing feature {i}/{len(features)}: {feature.get('id', 'unknown')}")

        sensor_data = extract_sensor_data(feature)
        if sensor_data:
            # Check if device filtering is enabled and device doesn't match
            if device_ids is not None and sensor_data.get("id") not in device_ids:
                logger.info(f"Skipping {sensor_data.get('id')}")
                continue

            processed_sensors.append(sensor_data)

            # Log extracted data for verification
            if sensor_data.get("measurement"):
                temp = sensor_data["measurement"].get("temperature")
                humidity = sensor_data["measurement"].get("humidity")
                time = sensor_data["measurement"].get("time")
                logger.info(f"  📊 Measurement: {temp}°C, {humidity}% at {time}")

            street = sensor_data["properties"].get("street", "N/A")
            logger.info(f"  📍 Location: {street}")
        else:
            logger.warning(f"⚠️ Failed to extract data from feature {i}")

    logger.info(f"✅ Processed {len(processed_sensors)} sensors from {len(features)} features")
    return processed_sensors


def format_ngsi_ld_entity(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format sensor data as NGSI-LD compliant TempHumiditySensor entity

    Args:
        sensor_data: Processed sensor data dictionary

    Returns:
        NGSI-LD compliant entity dictionary
    """
    try:
        # Extract basic data
        sensor_id = sensor_data.get("id")
        geometry = sensor_data.get("geometry", {})
        properties = sensor_data.get("properties", {})
        measurement = sensor_data.get("measurement", {})

        # Create NGSI-LD entity ID
        entity_id = f"urn:ngsi-ld:TempHumiditySensor:{sensor_id}" if sensor_id else None

        if not entity_id:
            logger.error("❌ Cannot create entity without valid sensor ID")
            return None

        # Base entity structure
        entity = {
            "id": entity_id,
            "type": "TempHumiditySensor",
        }

        # Add location if geometry is available
        if geometry and geometry.get("coordinates"):
            coordinates = geometry["coordinates"]
            entity["location"] = {"type": "GeoProperty", "value": {"type": "Point", "coordinates": coordinates}}

        # Add address if available
        street = properties.get("street")
        if street:
            entity["address"] = {
                "type": "Property",
                "value": {"streetAddress": street, "addressLocality": "Helsinki", "addressCountry": "Finland"},
            }

        # Add sensor name if available
        sensor_name = properties.get("name")
        if sensor_name:
            entity["name"] = {"type": "Property", "value": sensor_name}

        # Add installation date if available
        date_installed = properties.get("Date_installed")
        if date_installed:
            entity["dateInstalled"] = {"type": "Property", "value": date_installed}

        # Add sensor number if available
        sensor_number = properties.get("Sensor_number")
        if sensor_number:
            entity["sensorNumber"] = {"type": "Property", "value": sensor_number}

        # Add district if available
        district = properties.get("district")
        if district:
            entity["district"] = {"type": "Property", "value": district}

        # Add measurement data if available
        if measurement:
            measurement_time = measurement.get("time")
            temperature = measurement.get("temperature")
            humidity = measurement.get("humidity")

            if temperature is not None:
                entity["temperature"] = {
                    "type": "Property",
                    "value": temperature,
                    "unitCode": "CEL",  # Celsius
                }
                if measurement_time:
                    entity["temperature"]["observedAt"] = measurement_time

            if humidity is not None:
                entity["humidity"] = {
                    "type": "Property",
                    "value": humidity,
                    "unitCode": "P1",  # Percentage
                }
                if measurement_time:
                    entity["humidity"]["observedAt"] = measurement_time

        return entity

    except Exception as e:
        logger.error(f"❌ Error formatting NGSI-LD entity: {e}")
        return None


def format_ngsi_ld_update(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format sensor data as NGSI-LD compliant update payload (attributes only)

    Args:
        sensor_data: Processed sensor data dictionary

    Returns:
        NGSI-LD compliant update dictionary with attributes only
    """
    try:
        measurement = sensor_data.get("measurement", {})

        if not measurement:
            logger.warning("⚠️ No measurement data available for update")
            return None

        update_data = {}
        measurement_time = measurement.get("time")
        temperature = measurement.get("temperature")
        humidity = measurement.get("humidity")

        if temperature is not None:
            update_data["temperature"] = {"type": "Property", "value": temperature, "unitCode": "CEL"}
            if measurement_time:
                update_data["temperature"]["observedAt"] = measurement_time

        if humidity is not None:
            update_data["humidity"] = {"type": "Property", "value": humidity, "unitCode": "P1"}
            if measurement_time:
                update_data["humidity"]["observedAt"] = measurement_time

        return update_data if update_data else None

    except Exception as e:
        logger.error(f"❌ Error formatting NGSI-LD update: {e}")
        return None


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


def upsert_entities_with_retry(
    stellio_client: StellioClient, entities: List[Dict[str, Any]], max_retries: int = 3
) -> bool:
    """
    Upsert (create or update) multiple entities in Stellio with retry logic

    Args:
        stellio_client: Configured Stellio client
        entities: List of complete NGSI-LD entities
        max_retries: Maximum number of retry attempts

    Returns:
        True if successful, False otherwise
    """
    if not entities:
        logger.error("❌ Cannot process empty entity list")
        return False

    for attempt in range(max_retries + 1):
        try:
            logger.info(f"🔄 Attempting to upsert {len(entities)} entities (attempt {attempt + 1}/{max_retries + 1})")

            if stellio_client.upsert_entities(entities):
                logger.info(f"✅ Successfully upserted {len(entities)} entities")
                return True
            else:
                logger.warning("⚠️ Failed to upsert entities")

        except Exception as e:
            logger.error(f"❌ Error upserting entities (attempt {attempt + 1}): {e}")

            if attempt < max_retries:
                wait_time = 2**attempt  # Exponential backoff
                logger.info(f"⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                logger.error("❌ Max retries exceeded for entity upsert")
                return False

    return False


def verify_upserted_entities(stellio_client: StellioClient, entity_ids: List[str], limit: int = 5) -> Dict[str, int]:
    """
    Verify upserted entities by fetching their temporal data

    Args:
        stellio_client: Configured Stellio client
        entity_ids: List of entity IDs to verify
        limit: Number of latest measurements to fetch per entity

    Returns:
        Dictionary with verification statistics
    """
    stats = {"total": len(entity_ids), "verified": 0, "failed": 0}

    logger.info(f"🔍 Verifying {stats['total']} upserted entities...")

    for i, entity_id in enumerate(entity_ids, 1):
        logger.info(f"📊 Verifying entity {i}/{stats['total']}: {entity_id}")

        try:
            # Fetch temporal data with limit
            temporal_data = stellio_client.get_temporal_data(entity_id)

            if temporal_data:
                stats["verified"] += 1

                # Debug: log the structure of temporal data
                logger.debug(f"Temporal data type: {type(temporal_data)}")
                logger.debug(f"Temporal data sample: {str(temporal_data)[:500]}...")

                # Extract and display recent measurements
                display_temporal_data(entity_id, temporal_data, limit)

            else:
                logger.warning(f"⚠️ No temporal data found for entity: {entity_id}")
                stats["failed"] += 1

        except Exception as e:
            logger.error(f"❌ Error verifying entity {entity_id}: {e}")
            stats["failed"] += 1

    return stats


def display_temporal_data(entity_id: str, temporal_data, limit: int = 5):
    """
    Display temporal data in a readable format

    Args:
        entity_id: Entity ID
        temporal_data: Temporal data from Stellio (can be dict or list)
        limit: Maximum number of measurements to display
    """
    logger.info(f"  📈 Temporal data for {entity_id}:")

    # Handle different temporal data formats
    if isinstance(temporal_data, list):
        # If temporal_data is a list, it might be a list of entities
        if len(temporal_data) > 0:
            # Take the first entity from the list
            entity_data = temporal_data[0]
            logger.info(f"    📊 Found {len(temporal_data)} temporal entities, showing first one")
        else:
            logger.info("    ⚠️ Empty temporal data list")
            return
    elif isinstance(temporal_data, dict):
        # If it's a dict, use it directly
        entity_data = temporal_data
    else:
        logger.error(f"    ❌ Unexpected temporal data type: {type(temporal_data)}")
        return

    # Extract temperature measurements
    if "temperature" in entity_data:
        temp_attr = entity_data["temperature"]
        if isinstance(temp_attr, dict) and "values" in temp_attr:
            temp_values = temp_attr["values"]
        elif isinstance(temp_attr, list):
            temp_values = temp_attr
        else:
            temp_values = []

        if temp_values:
            logger.info(f"    🌡️ Temperature ({len(temp_values)} measurements):")
            for i, measurement in enumerate(temp_values[-limit:]):  # Show latest measurements
                if isinstance(measurement, dict):
                    value = measurement.get("value", "N/A")
                    observed_at = measurement.get("observedAt", "N/A")
                    logger.info(f"      {i + 1}. {value}°C at {observed_at}")
                else:
                    logger.info(f"      {i + 1}. {measurement}")
        else:
            logger.info("    🌡️ Temperature: No measurements found")

    # Extract humidity measurements
    if "humidity" in entity_data:
        humidity_attr = entity_data["humidity"]
        if isinstance(humidity_attr, dict) and "values" in humidity_attr:
            humidity_values = humidity_attr["values"]
        elif isinstance(humidity_attr, list):
            humidity_values = humidity_attr
        else:
            humidity_values = []

        if humidity_values:
            logger.info(f"    💧 Humidity ({len(humidity_values)} measurements):")
            for i, measurement in enumerate(humidity_values[-limit:]):  # Show latest measurements
                if isinstance(measurement, dict):
                    value = measurement.get("value", "N/A")
                    observed_at = measurement.get("observedAt", "N/A")
                    logger.info(f"      {i + 1}. {value}% at {observed_at}")
                else:
                    logger.info(f"      {i + 1}. {measurement}")
        else:
            logger.info("    💧 Humidity: No measurements found")

    # Show location if available
    if "location" in entity_data:
        location_attr = entity_data["location"]
        if isinstance(location_attr, dict) and "values" in location_attr:
            location_values = location_attr["values"]
        elif isinstance(location_attr, list):
            location_values = location_attr
        else:
            location_values = []

        if location_values:
            latest_location = location_values[-1]
            if isinstance(latest_location, dict):
                coordinates = latest_location.get("value", {}).get("coordinates", "N/A")
            else:
                coordinates = str(latest_location)
            logger.info(f"    📍 Location: {coordinates}")

    logger.info("")  # Empty line for readability


def process_sensors_to_stellio(
    stellio_client: StellioClient, sensors: List[Dict[str, Any]], max_retries: int = 3, dry_run: bool = False
) -> tuple[Dict[str, int], List[str]]:
    """
    Process sensor data and send to Stellio broker using batch upsert

    Args:
        stellio_client: Configured Stellio client
        sensors: List of processed sensor data
        max_retries: Maximum retry attempts for batch operation
        dry_run: If True, only format and validate without sending

    Returns:
        Tuple of (processing statistics, list of successfully processed entity IDs)
    """
    stats = {"total": len(sensors), "formatted": 0, "successful": 0, "failed": 0, "skipped": 0}
    processed_entity_ids = []

    logger.info(f"📊 Processing {stats['total']} sensors to Stellio using batch upsert...")

    # Collect all valid entities for batch processing
    entities_to_upsert = []

    for i, sensor_data in enumerate(sensors, 1):
        sensor_id = sensor_data.get("id", f"sensor_{i}")
        logger.info(f"🌡️ Processing sensor {i}/{stats['total']}: {sensor_id}")

        try:
            # Format NGSI-LD entity
            entity_data = format_ngsi_ld_entity(sensor_data)
            if not entity_data:
                logger.error(f"❌ Failed to format entity for sensor: {sensor_id}")
                stats["failed"] += 1
                continue

            # Check if we have measurement data (required for meaningful upsert)
            measurement = sensor_data.get("measurement", {})
            if not measurement or (measurement.get("temperature") is None and measurement.get("humidity") is None):
                logger.warning(f"⚠️ No measurement data for sensor: {sensor_id}")
                stats["skipped"] += 1
                continue

            stats["formatted"] += 1
            entities_to_upsert.append(entity_data)

            if dry_run:
                logger.info(f"🔍 [DRY RUN] Would upsert entity: {entity_data['id']}")
                logger.info(
                    f"  📍 Location: {entity_data.get('location', {}).get('value', {}).get('coordinates', 'N/A')}"
                )
                if "temperature" in entity_data:
                    temp_val = entity_data["temperature"]["value"]
                    logger.info(f"  🌡️ Temperature: {temp_val}°C")
                if "humidity" in entity_data:
                    hum_val = entity_data["humidity"]["value"]
                    logger.info(f"  💧 Humidity: {hum_val}%")

        except Exception as e:
            logger.error(f"❌ Error processing sensor {sensor_id}: {e}")
            stats["failed"] += 1

    # Process entities in batch
    if dry_run:
        stats["successful"] = len(entities_to_upsert)
        processed_entity_ids = [entity["id"] for entity in entities_to_upsert]
        logger.info(f"🔍 [DRY RUN] Would upsert {len(entities_to_upsert)} entities in batch")
    else:
        if entities_to_upsert:
            logger.info(f"🚀 Upserting {len(entities_to_upsert)} entities in batch...")
            if upsert_entities_with_retry(stellio_client, entities_to_upsert, max_retries):
                stats["successful"] = len(entities_to_upsert)
                processed_entity_ids = [entity["id"] for entity in entities_to_upsert]
                logger.info(f"✅ Successfully upserted all {len(entities_to_upsert)} entities")
            else:
                stats["failed"] += len(entities_to_upsert)
                logger.error(f"❌ Failed to upsert {len(entities_to_upsert)} entities")
        else:
            logger.warning("⚠️ No valid entities to upsert")

    return stats, processed_entity_ids


def main():
    """Main function"""
    args = parse_args()

    # Configure verbose logging if requested
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("🌡️ Temperature & Humidity Sensor Updater")
    logger.info("=" * 50)

    all_sensors = []

    # Process each GeoJSON source
    for geojson_source in args.geojson:
        try:
            logger.info(f"\n📋 Processing GeoJSON source: {geojson_source}")

            # Fetch GeoJSON data
            geojson_data = fetch_geojson_data(geojson_source)

            # Validate structure
            if not validate_geojson_structure(geojson_data):
                logger.error(f"❌ Invalid GeoJSON structure in {geojson_source}, skipping...")
                continue

            # Process features
            sensors = process_geojson_features(geojson_data, args.device_id)
            all_sensors.extend(sensors)

            logger.info(f"✅ Processed {len(sensors)} sensors from {geojson_source}")

        except Exception as e:
            logger.error(f"❌ Error processing {geojson_source}: {e}")
            continue

    # Summary
    logger.info("\n📊 Processing Summary:")
    logger.info(f"  Total sensors processed: {len(all_sensors)}")

    if not all_sensors:
        logger.warning("⚠️ No sensors to process")
        return

    # Process sensors to Stellio
    stellio_client = None
    if not args.dry_run:
        try:
            stellio_client = setup_stellio_client(args)
        except Exception as e:
            logger.error(f"❌ Failed to setup Stellio client: {e}")
            logger.info("💡 Use --dry-run to test without Stellio connection")
            return

    # Process all sensors
    stats, processed_entity_ids = process_sensors_to_stellio(
        stellio_client=stellio_client, sensors=all_sensors, max_retries=args.max_retries, dry_run=args.dry_run
    )

    # Final statistics
    logger.info("\n📊 Final Results:")
    logger.info(f"  Total sensors: {stats['total']}")
    logger.info(f"  Successfully formatted: {stats['formatted']}")
    logger.info(f"  Successfully processed: {stats['successful']}")
    logger.info(f"  Failed: {stats['failed']}")
    logger.info(f"  Skipped (no measurement data): {stats['skipped']}")

    if args.dry_run:
        logger.info("\n🔍 Dry run completed - no data was sent to Stellio broker")
        logger.info("💡 Remove --dry-run flag to actually update the broker")
    else:
        success_rate = (stats["successful"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        logger.info(f"\n🚀 Stellio update completed with {success_rate:.1f}% success rate")

    # Verify upserted entities if requested
    if args.verify_upsert and processed_entity_ids and not args.dry_run:
        logger.info("\n🔍 Verifying upserted entities...")
        verify_stats = verify_upserted_entities(stellio_client, processed_entity_ids, args.verify_limit)

        logger.info("\n📊 Verification Results:")
        logger.info(f"  Total entities verified: {verify_stats['total']}")
        logger.info(f"  Successfully verified: {verify_stats['verified']}")
        logger.info(f"  Failed verification: {verify_stats['failed']}")

        verify_rate = (verify_stats["verified"] / verify_stats["total"]) * 100 if verify_stats["total"] > 0 else 0
        logger.info(f"  Verification success rate: {verify_rate:.1f}%")
    elif args.verify_upsert and args.dry_run:
        logger.info("\n💡 Verification skipped in dry-run mode")
    elif args.verify_upsert and not processed_entity_ids:
        logger.info("\n⚠️ No entities to verify")

    logger.info("\n✅ Processing complete!")


if __name__ == "__main__":
    main()
