import argparse
import json
from datetime import datetime
from pathlib import Path

from stellio_client import StellioClient, StellioTokenManager


OUTPUT_DIR = Path(__file__).parent.parent / "data" / "raw"


def parse_args():
    parser = argparse.ArgumentParser(description="Explore Stellio data")
    parser.add_argument("--client-id", type=str, help="Client ID")
    parser.add_argument("--client-secret", type=str, help="Client secret")
    # parser.add_argument("--base-url", type=str, help="Base URL")
    # parser.add_argument("--tenant", type=str, help="Tenant")
    return parser.parse_args()


def ensure_output_dir():
    """Create OUTPUT_DIR if it doesn't exist"""
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)


def save_data_by_type(data, data_type, description=""):
    """Save data to type-specific file in OUTPUT_DIR"""
    ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{data_type}_{timestamp}.json"
    filepath = Path(OUTPUT_DIR) / filename

    data_to_save = {
        "type": data_type,
        "description": description,
        "timestamp": datetime.now().isoformat(),
        "data": data,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, indent=2, ensure_ascii=False)
    print(f"✅ {data_type} data saved to {filepath}")
    return filepath


def explore_stellio_data(args: argparse.Namespace):
    """Inspect Stellio broker data step by step"""

    # 1. Initialize token manager and get token
    print("1. Checking for existing token...")
    ensure_output_dir()
    token_file = Path(OUTPUT_DIR) / "access_token.json"
    token_manager = StellioTokenManager(token_file)

    CLIENT_ID = args.client_id
    CLIENT_SECRET = args.client_secret

    token = token_manager.get_or_refresh_token(CLIENT_ID, CLIENT_SECRET)
    if not token:
        print("❌ Token hakeminen epäonnistui")
        return

    # 2. Create Stellio client with token manager for automatic refresh
    stellio = StellioClient(
        base_url="https://sedimark-helsinki.stellio.io",
        access_token=token,
        tenant="urn:ngsi-ld:tenant:sedimark-helsinki",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_manager=token_manager,
    )

    # 3. Tutki mitä tyyppejä on saatavilla
    print("\n2. Fetching all entity types...")
    types = stellio.get_all_types()
    if types:
        # Save types data
        save_data_by_type(types, "entity_types", "All available entity types in Stellio")
        print("✅ Found entity types:")
        for entity_type in types:
            print(f"  - {entity_type}")

    # 4. Hae kaikkien entiteettityyppien tiedot
    if types and "typeList" in types:
        print(f"\n3. Fetching entities for all {len(types['typeList'])} entity types...")
        for i, entity_type in enumerate(types["typeList"], 1):
            print(f"\n3.{i}. Fetching {entity_type} entities...")
            entities = stellio.get_entities_by_type(entity_type)
            if entities:
                # Convert entity type to snake_case for filename
                filename_type = entity_type.lower().replace(" ", "_")
                save_data_by_type(entities, f"{filename_type}_entities", f"All {entity_type} entities")
                print(f"✅ Found {len(entities)} {entity_type} entities")

                # Show first few entities
                for entity in entities[:2]:  # Show first two
                    print(f"  - ID: {entity.get('id')}")
                    if "name" in entity and isinstance(entity["name"], dict):
                        print(f"    Name: {entity['name'].get('value', 'N/A')}")
            else:
                print(f"❌ No {entity_type} entities found or error occurred")
    else:
        print("❌ No entity types available, skipping entity fetching")

    # 5. Hae yksittäisen entiteetin tiedot
    print("\n4. Fetching individual station data...")
    station_data = stellio.get_entity("urn:sedimark:station:1")
    if station_data:
        # Save individual station data
        save_data_by_type(station_data, "station_entity", "Individual station entity data (urn:sedimark:station:1)")
        print("✅ Station data:")
        print(f"  - ID: {station_data.get('id')}")
        print(f"  - Tyyppi: {station_data.get('type')}")
        # Show some key attributes
        for key, value in station_data.items():
            if key not in ["id", "type", "@context"]:
                if isinstance(value, dict) and "value" in value:
                    print(f"  - {key}: {value['value']}")

    # 6. Hae historiallista dataa
    print("\n5. Fetching historical data...")
    temporal_data = stellio.get_temporal_data("urn:sedimark:station:1", "temporalValues")
    if temporal_data:
        # Save temporal data
        save_data_by_type(
            temporal_data, "temporal_data", "Temporal/historical data for station urn:sedimark:station:1"
        )
        print("✅ Historical data fetched (limited to first item)")
        print(f"  - Entity: {temporal_data.get('id')}")
        # Näytä ensimmäinen attribuutti jossa on temporaalista dataa
        for key, value in temporal_data.items():
            if key not in ["id", "type", "@context"] and isinstance(value, dict):
                if "values" in value:
                    values_count = len(value["values"])
                    print(f"  - {key}: {values_count} values in history")
                    if values_count > 0:
                        latest = value["values"][0]
                        print(f"    Latest: {latest}")
                break

    print(f"\n✅ All data saved to {OUTPUT_DIR}")
    print("📁 Saved files:")
    output_path = Path(OUTPUT_DIR)
    if output_path.exists():
        for file in sorted(output_path.glob("*.json")):
            print(f"  - {file.name}")


if __name__ == "__main__":
    args = parse_args()
    print("🔍 Stellio NGSI-LD Explorer")
    print("=" * 40)
    explore_stellio_data(args)
