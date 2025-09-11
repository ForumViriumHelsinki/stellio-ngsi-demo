"""
Stellio NGSI-LD Context Broker Client

This module provides a client for interacting with Stellio NGSI-LD Context Broker,
including authentication and basic CRUD operations for entities.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import httpx


class StellioClient:
    """Client for Stellio NGSI-LD Context Broker"""

    def __init__(
        self,
        base_url: str,
        access_token: str,
        tenant: str,
        client_id: str = None,
        client_secret: str = None,
        token_manager: "StellioTokenManager" = None,
    ):
        """
        Initialize Stellio client

        Args:
            base_url: Base URL of the Stellio broker
            access_token: OAuth2 access token for authentication
            tenant: NGSI-LD tenant identifier
            client_id: OAuth2 client ID for token refresh (optional)
            client_secret: OAuth2 client secret for token refresh (optional)
            token_manager: Token manager instance for automatic token refresh (optional)
        """
        self.base_url = base_url
        self.tenant = tenant
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_manager = token_manager
        self.access_token = access_token
        self._update_headers()

    def _update_headers(self):
        """Update headers with current access token"""
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "NGSILD-Tenant": self.tenant,
            "Link": '<https://sedimark.github.io/broker/jsonld-contexts/sedimark-helsinki-compound.jsonld>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"',
        }

    def _refresh_token_if_needed(self):
        """Refresh access token if credentials are available"""
        if self.client_id and self.client_secret:
            logging.info("🔄 Token expired, refreshing...")
            new_token = self.get_access_token(self.client_id, self.client_secret)
            if new_token:
                self.access_token = new_token
                self._update_headers()
                if self.token_manager:
                    self.token_manager.save_token(new_token)
                logging.info("✅ Token refreshed successfully")
                return True
            else:
                logging.error("❌ Failed to refresh token")
        else:
            logging.error("❌ Cannot refresh token: client credentials not provided")
        return False

    def _make_request(self, method: str, url: str, **kwargs):
        """
        Make HTTP request with automatic token refresh on 401 errors

        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            url: Request URL
            **kwargs: Additional arguments for httpx request

        Returns:
            httpx.Response object
        """
        with httpx.Client() as client:
            # First attempt
            response = getattr(client, method.lower())(url, headers=self.headers, **kwargs)

            # If 401 Unauthorized, try to refresh token and retry once
            if response.status_code == 401:
                logging.warning(f"🔐 Received 401 Unauthorized for {url}")
                if self._refresh_token_if_needed():
                    logging.info("🔄 Retrying request with new token...")
                    response = getattr(client, method.lower())(url, headers=self.headers, **kwargs)
                else:
                    logging.error("❌ Could not refresh token, request failed")

            return response

    def get_all_types(self):
        """Fetch all available entity types"""
        try:
            url = f"{self.base_url}/ngsi-ld/v1/types"
            response = self._make_request("GET", url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error fetching types: {e}")
            return None

    def get_entities_by_type(self, entity_type: str):
        """Fetch all entities of a specific type"""
        try:
            url = f"{self.base_url}/ngsi-ld/v1/entities?type={entity_type}"
            response = self._make_request("GET", url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error fetching entities: {e}")
            return None

    def get_entity(self, entity_id: str):
        """Fetch a single entity by ID"""
        try:
            url = f"{self.base_url}/ngsi-ld/v1/entities/{entity_id}"
            response = self._make_request("GET", url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error fetching entity: {e}")
            return None

    def get_temporal_data(self, entity_id: str, format_type: str | None = None):
        """Fetch temporal/historical data for an entity"""
        try:
            url = f"{self.base_url}/ngsi-ld/v1/temporal/entities/{entity_id}"
            if format_type:
                url += f"?format={format_type}"
            response = self._make_request("GET", url, timeout=20)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error fetching temporal data: {e}")
            return None

    def create_entity(self, entity_data: dict):
        """Create a new entity"""
        try:
            url = f"{self.base_url}/ngsi-ld/v1/entities"
            response = self._make_request("POST", url, json=entity_data)
            response.raise_for_status()
            return True
        except Exception as e:
            logging.error(f"Error creating entity: {e}")
            return False

    def update_entity(self, entity_id: str, update_data: dict):
        """Update an existing entity"""
        try:
            url = f"{self.base_url}/ngsi-ld/v1/entities/{entity_id}/attrs"
            response = self._make_request("PATCH", url, json=update_data)
            response.raise_for_status()
            return True
        except Exception as e:
            logging.error(f"Error updating entity: {e}")
            return False

    def upsert_entities(self, entities: list):
        """
        Create or update multiple entities using batch upsert operation

        Args:
            entities: List of NGSI-LD entity dictionaries

        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/ngsi-ld/v1/entityOperations/upsert"
            response = self._make_request("POST", url, json=entities)
            response.raise_for_status()

            # Handle different success responses
            if response.status_code == 204:
                # No Content - entities were already up to date, no changes needed
                logging.info(f"✅ Entities already up to date, no changes needed ({len(entities)} entities)")
                return True
            elif response.status_code == 201:
                # Created - new entities were created
                logging.info(f"✅ Successfully created {len(entities)} new entities")
                return True
            elif response.status_code == 207:
                # Multi-Status - mixed results, some succeeded, some failed
                try:
                    result = response.json()
                    logging.info(f"Response: {result}")
                    if isinstance(result, list):
                        # Simple list of entity IDs (all successful)
                        logging.info(f"✅ Successfully upserted {len(result)} entities")
                        return True
                    elif isinstance(result, dict) and "success" in result:
                        # Detailed response with success/error breakdown
                        success_count = len(result.get("success", []))
                        error_count = len(result.get("errors", []))
                        logging.info(f"✅ Upsert completed: {success_count} successful, {error_count} errors")
                        return success_count > 0  # Consider partial success as success
                    else:
                        logging.info(f"✅ Successfully upserted {len(entities)} entities")
                        return True
                except Exception as json_error:
                    # If JSON parsing fails but status is 207, assume success
                    logging.info(f"✅ Successfully upserted {len(entities)} entities (JSON parse error: {json_error})")
                    return True
            else:
                logging.info(f"✅ Successfully upserted {len(entities)} entities (status: {response.status_code})")
                return True

        except Exception as e:
            logging.error(f"Error upserting entities: {e}")
            return False

    @staticmethod
    def get_access_token(client_id: str, client_secret: str) -> str | None:
        """
        Get OAuth2 access token for Stellio authentication

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret

        Returns:
            Access token string or None if authentication failed
        """
        token_url = "https://sso.eglobalmark.com/auth/realms/sedimark-helsinki/protocol/openid-connect/token"

        data = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}

        try:
            with httpx.Client() as client:
                response = client.post(
                    token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                response.raise_for_status()
                return response.json().get("access_token")
        except Exception as e:
            logging.error(f"Token authentication error: {e}")
            return None


class StellioTokenManager:
    """Helper class for managing Stellio access tokens"""

    def __init__(self, token_file_path: Path | str):
        """
        Initialize token manager

        Args:
            token_file_path: Path where to store/load the access token
        """
        self.token_file_path = Path(token_file_path)

    def save_token(self, token: str):
        """Save access token to file"""
        self.token_file_path.parent.mkdir(parents=True, exist_ok=True)
        token_data = {"access_token": token, "timestamp": datetime.now().isoformat()}
        with open(self.token_file_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)
        logging.info(f"✅ Token saved to {self.token_file_path}")

    def load_token(self) -> str | None:
        """Load access token from file if it exists"""
        if self.token_file_path.exists():
            try:
                with open(self.token_file_path, "r", encoding="utf-8") as f:
                    token_data = json.load(f)
                logging.info(f"✅ Token loaded from {self.token_file_path}")
                return token_data.get("access_token")
            except Exception as e:
                logging.error(f"❌ Error loading token: {e}")
        return None

    def get_or_refresh_token(self, client_id: str, client_secret: str) -> str | None:
        """
        Get token from file or fetch new one if not available

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret

        Returns:
            Access token string or None if failed
        """
        # Try to load existing token
        token = self.load_token()

        if not token:
            logging.info("No saved token found. Getting new token...")
            token = StellioClient.get_access_token(client_id, client_secret)
            if token:
                self.save_token(token)
                logging.info(f"✅ New token retrieved and saved. {token[:20]}...")
            else:
                logging.error("❌ Failed to get access token")
                return None
        else:
            logging.info(f"✅ Using saved token. {token[:20]}...")

        return token
