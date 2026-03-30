"""ServiceDesk Plus API client for fetching workstation data."""

import json
import logging

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# ServiceDesk Plus status → Nautobot status name mappings
STATUS_MAPPINGS = {
    "In Store": "Inventory",
    "In Use": "Active",
    "Deployed": "Active",
    "Maintenance": "Planned",
    "Retired": "Decommissioning",
    "Faulty": "Failed",
    "Returned": "Inventory",
    "Expired": "End-of-Life",
    "Staging": "Staged",
    "To Be Returned": "Inventory",
}

# Default values for required Nautobot fields
DEFAULT_ROLE = "NUS"
DEFAULT_STATUS = "Active"
DEFAULT_LOCATION_TYPE = "Site"

# Location name normalization — maps SDP location variants to canonical Nautobot names
LOCATION_MAPPINGS = {
    "Huntsville, AL": "HSV",
    "Huntsville AL": "HSV",
}


def get_nested_value(data, key_path, default=None):
    """Get value from nested dictionary using dot notation.

    Args:
        data: Dictionary to traverse.
        key_path: Dot-separated path (e.g., "computer_system.service_tag").
        default: Value to return if path not found.

    Returns:
        The value at the path, or default if not found or empty.
    """
    keys = key_path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    if value in (None, "", "-", "N/A", "null"):
        return default
    return value


class ServiceDeskPlusClient:  # pylint: disable=too-few-public-methods
    """Client for the ServiceDesk Plus REST API.

    Handles authentication, pagination, and data retrieval for workstation assets.
    """

    def __init__(self, url, token, verify_ssl=true):
        """Initialize the ServiceDesk Plus client.

        Args:
            url: Base URL of the ServiceDesk Plus instance.
            token: API authentication token.
            verify_ssl: Whether to verify SSL certificates.
        """
        self.url = url.rstrip("/")
        self.token = token
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.headers.update({"authtoken": self.token})
        self.session.verify = self.verify_ssl

    def get_workstations(self, page_size=100, product_type="Server"):
        """Fetch workstations from ServiceDesk Plus with automatic pagination.

        Args:
            page_size: Number of records per API request (max 100).
            product_type: Filter by product type name (e.g., "Server"). None to fetch all.

        Returns:
            List of workstation dictionaries from the ServiceDesk Plus API.
        """
        all_workstations = []
        start_index = 0

        while True:
            list_info = {
                "row_count": page_size,
                "start_index": start_index,
                "sort_field": "id",
                "sort_order": "asc",
                "get_total_count": True,
            }

            if product_type:
                list_info["search_criteria"] = {
                    "field": "product_type.name",
                    "condition": "is",
                    "value": product_type,
                }

            input_data = {"list_info": list_info}
            params = {"input_data": json.dumps(input_data)}
            url = f"{self.url}/api/v3/workstations"

            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # Validate response status
            response_status = data.get("response_status", [{}])
            if isinstance(response_status, list) and response_status:
                if response_status[0].get("status") != "success":
                    raise ValueError(f"ServiceDesk Plus API error: {data}")

            workstations = data.get("workstations", [])
            if not workstations:
                break

            all_workstations.extend(workstations)

            resp_list_info = data.get("list_info", {})
            has_more = resp_list_info.get("has_more_rows", False)

            if not has_more:
                break

            start_index += len(workstations)

        logger.info(
            "Fetched %d workstations (product_type=%s) from ServiceDesk Plus", len(all_workstations), product_type
        )
        return all_workstations
