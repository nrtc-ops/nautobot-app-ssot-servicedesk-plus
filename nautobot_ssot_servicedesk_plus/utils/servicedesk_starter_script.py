#!/usr/bin/env python3
"""
ServiceDesk to Nautobot Device Import Tool

Fetches workstation/asset data from ServiceDesk API and imports it into Nautobot DCIM.
Provides field mapping between ServiceDesk and Nautobot data models with relationship handling.

USAGE EXAMPLES:
    # Basic import with default settings
    python servicedesk_to_nautobot_import.py

    # Import specific number of records
    python servicedesk_to_nautobot_import.py --count 100

    # Test mode (validate without importing)
    python servicedesk_to_nautobot_import.py --dry-run

    # Custom ServiceDesk and Nautobot configurations
    python servicedesk_to_nautobot_import.py \
        --servicedesk-url https://servicedesk.example.com \
        --servicedesk-token your_token \
        --nautobot-url https://nautobot.example.com \
        --nautobot-token your_token

FIELD MAPPINGS:
    ServiceDesk → Nautobot:
    - name → name (device hostname)
    - computer_system.service_tag → serial (device serial number)
    - vendor.name → manufacturer (Pascal case conversion, e.g., DELL → Dell)
    - computer_system.system_manufacturer → device_type (hardware manufacturer)
    - computer_system.model → device_family (model family)
    - location → location (physical location, auto-created if missing)
    - site.name → tenant (organizational tenant, auto-created if missing)
    - product_type.name → role (mapped to existing roles)
    - state.name → status (mapped to existing statuses)
    - primary_ip → primary_ip4 (if available)
    - description → comments
    - udf_fields.udf_pick_8415 or model → custom_fields.power_type (AC/DC)

FEATURES:
    • Automatic pagination through all ServiceDesk records
    • Field validation and transformation
    • Relationship mapping with auto-creation of missing objects
    • Bulk API operations for performance
    • Comprehensive logging and error handling
    • Support for both create and update operations

OUTPUT:
    - Console progress updates
    - Detailed log file with operation results
    - Success/failure statistics
    - JSON export of fetched data for review
"""

import argparse
import csv
import json
import os
import sys
from itertools import islice
from pathlib import Path

import httpx
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ====== .ENV FILE LOADING ======
def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # Only set if not already in environment
                    if key not in os.environ:
                        os.environ[key] = value


# Load .env file before setting configuration
load_env_file()

# ====== CONFIG ======
# ServiceDesk Configuration
SERVICEDESK_URL = os.getenv("SERVICEDESK_URL", "https://servicedesk.nrtc.coop")
SERVICEDESK_TOKEN = os.getenv("SERVICEDESK_TOKEN")
SERVICEDESK_ENDPOINT = "/api/v3/workstations"

# Nautobot Configuration
NAUTOBOT_URL = os.getenv("NAUTOBOT_URL", "https://nautobot-dso.oneit.nrtc.coop")
NAUTOBOT_TOKEN = os.getenv("NAUTOBOT_TOKEN")
NAUTOBOT_ENDPOINT = "/api/dcim/devices/"

# Processing Configuration
BULK_SIZE = 50
LOG_CSV = "logs/servicedesk_nautobot_import_log.csv"
DATA_EXPORT = "data/servicedesk_export.json"
UNIQUE_FIELD = "name"


# Validate required environment variables
def validate_environment():
    """Validate that required environment variables are set."""
    missing_vars = []

    if not SERVICEDESK_TOKEN:
        missing_vars.append("SERVICEDESK_TOKEN")
    if not NAUTOBOT_TOKEN:
        missing_vars.append("NAUTOBOT_TOKEN")

    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nPlease set these environment variables before running the script.")
        print("Example:")
        print("  export SERVICEDESK_TOKEN='your-servicedesk-token'")
        print("  export NAUTOBOT_TOKEN='your-nautobot-token'")
        print("\nOr create a .env file:")
        print("  cp .env.template .env")
        print("  # Edit .env with your actual tokens")
        return False
    return True


# Note: Environment validation will be called in main() when operations begin


# ====== HELPER FUNCTIONS FOR HEADERS ======
def get_servicedesk_headers():
    """Get ServiceDesk API headers with token."""
    return {"authtoken": SERVICEDESK_TOKEN, "Content-Type": "application/json"}


def get_nautobot_headers():
    """Get Nautobot API headers with token."""
    return {
        "Authorization": f"Token {NAUTOBOT_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


# ====== FIELD MAPPINGS ======

# Map ServiceDesk fields to Nautobot device fields
SERVICEDESK_TO_NAUTOBOT_MAPPING = {
    # Direct field mappings
    "udf_fields.udf_sline_14115": "name",  # Use hostname/FQDN from UDF field as device name
    "description": "comments",
    "primary_ip": "primary_ip4",
    # Nested field mappings (dot notation for ServiceDesk nested fields)
    "computer_system.service_tag": "serial",
    "asset_tag": "asset_tag",
    # Updated relationship mappings
    "location": "location",  # Maps to physical location name
    "site.name": "tenant",  # Maps ServiceDesk site to Nautobot tenant
    "vendor.name": "manufacturer",  # Maps ServiceDesk vendor to Nautobot manufacturer (Pascal case)
    "udf_fields.udf_sline_14122": "device_type",  # Maps specific hardware model (e.g., PowerEdge R340) to device type
    "computer_system.model": "device_family",  # Maps model to device family
    "product_type.name": "role",  # Maps to device role name
    "state.name": "status",  # Maps to device status name
}

# Default values for required Nautobot fields
NAUTOBOT_DEFAULTS = {
    "status": "active",
    "role": "NUS",  # Default role for all ServiceDesk imported devices
    "manufacturer": "Generic",
    "device_type": "generic-device",
    "location": "default-location",  # Using locations instead of sites
    "tenant": "default-tenant",  # Default tenant for devices
}

# ServiceDesk to Nautobot status mappings
STATUS_MAPPINGS = {
    "In Store": "Inventory",
    "In Use": "Active",
    "Deployed": "Active",
    "Maintenance": "Maintenance",
    "Retired": "Retired",
    "Faulty": "Failed",
    "Returned": "Inventory",  # Devices returned to inventory
}

# ServiceDesk to Nautobot role mappings
ROLE_MAPPINGS = {
    "Server": "NUS",
    "Desktop": "NUS",
    "Laptop": "NUS",
    "Network": "NUS",
    "Printer": "NUS",
    "Workstation": "NUS",
    # All ServiceDesk devices will be assigned the "NUS" role
}

# ====== UTILITY FUNCTIONS ======


def get_nested_value(data, key_path, default=None):
    """Get value from nested dictionary using dot notation."""
    keys = key_path.split(".")
    value = data
    try:
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value if value not in [None, "", "-"] else default
    except (KeyError, TypeError):
        return default


def to_pascal_case(text):
    """Convert text to Pascal case (e.g., 'dell' -> 'Dell')."""
    if not text:
        return text
    return text.title()


def extract_power_type(servicedesk_record):
    """Extract power type (AC/DC) from ServiceDesk record."""
    # First try the UDF field
    power_type = get_nested_value(servicedesk_record, "udf_fields.udf_pick_8415")
    if power_type:
        return power_type.upper()

    # Then try to extract from model name
    model = get_nested_value(servicedesk_record, "computer_system.model") or ""
    if "(AC)" in model.upper():
        return "AC"
    elif "(DC)" in model.upper():
        return "DC"

    return None


def create_basic_interfaces(servicedesk_record, status_id=None):
    """Create basic network interfaces from ServiceDesk IP data."""
    interfaces = []

    # Get IP addresses from ServiceDesk
    ip_addresses_str = get_nested_value(servicedesk_record, "ip_addresses") or ""
    primary_ip = get_nested_value(servicedesk_record, "primary_ip")

    # Parse IP addresses (could be comma-separated)
    ip_addresses = []
    if ip_addresses_str:
        ip_addresses = [ip.strip() for ip in ip_addresses_str.split(",") if ip.strip()]

    # If no IP addresses but we have a primary IP, use that
    if not ip_addresses and primary_ip:
        ip_addresses = [primary_ip]

    # Create interfaces for each IP
    for i, ip in enumerate(ip_addresses):
        interface_name = f"eth{i}" if len(ip_addresses) > 1 else "eth0"

        interface = {
            "name": interface_name,
            "type": "1000base-t",  # Default to 1G copper
            "enabled": True,
            "mgmt_only": False,
        }

        # Add status if provided (match device status)
        if status_id:
            interface["status"] = {"id": status_id}

        # Add IP address if we have one
        if ip and ip != "null" and ip != "-":
            # Format IP address with subnet mask if not present
            if "/" not in ip:
                ip = f"{ip}/24"  # Default to /24 if no subnet specified

            interface["ip_address"] = ip  # Store for later IP creation

        interfaces.append(interface)

    # If no IP addresses found, create a single generic interface
    if not interfaces:
        default_interface = {
            "name": "eth0",
            "type": "1000base-t",
            "enabled": True,
            "mgmt_only": False,
        }
        # Add status if provided (match device status)
        if status_id:
            default_interface["status"] = {"id": status_id}
        interfaces.append(default_interface)

    return interfaces


def clean_value(value):
    """Clean and normalize field values."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value in ["", "-", "N/A", "null"]:
            return None
    return value


def get_all_from_api(url, headers, key_field="results"):
    """Fetch all paginated results from an API endpoint."""
    results = []
    with httpx.Client(http2=True, verify=False, timeout=30.0) as client:
        while url:
            try:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                if isinstance(data, dict) and key_field in data:
                    results.extend(data[key_field])
                    url = data.get("next")
                elif isinstance(data, list):
                    results.extend(data)
                    url = None
                else:
                    break
            except Exception as e:
                print(f"❌ Error fetching data from {url}: {e}")
                break
    return results


def fetch_servicedesk_workstations(count=None, start_index=0):
    """Fetch workstation data from ServiceDesk API with pagination."""
    all_workstations = []
    row_count = min(count or 100, 100)  # ServiceDesk may have limits

    print("🔄 Fetching workstations from ServiceDesk...")

    with httpx.Client(http2=True, verify=False, timeout=30.0) as client:
        current_index = start_index

        while True:
            # Prepare request data
            input_data = {
                "list_info": {
                    "row_count": row_count,
                    "start_index": current_index,
                    "sort_field": "id",
                    "sort_order": "asc",
                    "get_total_count": True,
                }
            }

            params = {"input_data": json.dumps(input_data)}
            url = f"{SERVICEDESK_URL}{SERVICEDESK_ENDPOINT}"

            try:
                resp = client.get(url, headers=get_servicedesk_headers(), params=params)
                resp.raise_for_status()
                data = resp.json()

                if data.get("response_status", [{}])[0].get("status") != "success":
                    print(f"❌ ServiceDesk API error: {data}")
                    break

                workstations = data.get("workstations", [])
                if not workstations:
                    break

                all_workstations.extend(workstations)
                print(f"📥 Fetched {len(workstations)} workstations (total: {len(all_workstations)})")

                # Check if we have more data or reached our limit
                list_info = data.get("list_info", {})
                has_more = list_info.get("has_more_rows", False)
                total_count = list_info.get("total_count", 0)

                if not has_more or (count and len(all_workstations) >= count):
                    break

                current_index += len(workstations)

                # If we have a count limit, adjust row_count for next request
                if count:
                    remaining = count - len(all_workstations)
                    row_count = min(remaining, 100)
                    if row_count <= 0:
                        break

            except Exception as e:
                print(f"❌ Error fetching ServiceDesk data: {e}")
                break

    print(f"✅ Fetched {len(all_workstations)} total workstations from ServiceDesk")
    return all_workstations


def get_or_create_nautobot_object(endpoint, name_field, object_data, log_rows):
    """Get existing object or create new one in Nautobot."""
    if not object_data.get(name_field):
        return None

    try:
        # Try to find existing object
        url = f"{NAUTOBOT_URL}{endpoint}"
        params = {name_field: object_data[name_field]}

        with httpx.Client(http2=True, verify=False, timeout=30.0) as client:
            resp = client.get(url, headers=get_nautobot_headers(), params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if results:
                return results[0]["id"]

            # Create new object if not found
            resp = client.post(url, headers=get_nautobot_headers(), json=object_data)
            if resp.status_code in [200, 201]:
                created_obj = resp.json()
                log_rows.append(
                    {
                        "name": object_data.get(name_field),
                        "endpoint": endpoint,
                        "action": "created_dependency",
                        "status_code": resp.status_code,
                        "response": f"Created {name_field}: {object_data[name_field]}",
                    }
                )
                return created_obj["id"]
            else:
                log_rows.append(
                    {
                        "name": object_data.get(name_field),
                        "endpoint": endpoint,
                        "action": "failed_dependency",
                        "status_code": resp.status_code,
                        "response": resp.text,
                    }
                )
                return None

    except Exception as e:
        print(f"❌ Error creating {name_field} '{object_data.get(name_field)}': {e}")
        return None


def get_uuid_map(endpoint, name_field="name"):
    """Get a mapping of names to UUIDs for an endpoint."""
    mapping = {}
    try:
        objects = get_all_from_api(f"{NAUTOBOT_URL}{endpoint}", get_nautobot_headers())
        for obj in objects:
            if name_field in obj and obj[name_field]:
                mapping[obj[name_field]] = obj["id"]
            # Also map by model field for device types
            if "model" in obj and obj["model"]:
                mapping[obj["model"]] = obj["id"]
    except Exception as e:
        print(f"❌ Error fetching {endpoint} mappings: {e}")
    return mapping


def transform_servicedesk_to_nautobot(servicedesk_record, uuid_maps, log_rows):
    """Transform a ServiceDesk workstation record to Nautobot device format."""
    nautobot_device = {}

    # Process direct field mappings
    for sd_field, nb_field in SERVICEDESK_TO_NAUTOBOT_MAPPING.items():
        value = get_nested_value(servicedesk_record, sd_field)
        value = clean_value(value)

        if value is not None:
            # Special handling for manufacturer from vendor (convert to Pascal case)
            if nb_field == "manufacturer" and sd_field == "vendor.name":
                value = to_pascal_case(value)

            # Handle relationship fields
            if nb_field in [
                "location",
                "manufacturer",
                "device_type",
                "device_family",
                "role",
                "status",
                "tenant",
            ]:
                # Apply status mapping
                if nb_field == "status" and value in STATUS_MAPPINGS:
                    value = STATUS_MAPPINGS[value]

                # Apply role mapping
                if nb_field == "role" and value in ROLE_MAPPINGS:
                    value = ROLE_MAPPINGS[value]

                # Look up UUID in pre-fetched mappings
                uuid_map = uuid_maps.get(nb_field, {})
                if value in uuid_map:
                    nautobot_device[nb_field] = {"id": uuid_map[value]}
                else:
                    # Try to create missing relationship objects
                    object_id = None
                    if nb_field == "manufacturer":
                        object_id = get_or_create_nautobot_object(
                            "/api/dcim/manufacturers/",
                            "name",
                            {"name": value},
                            log_rows,
                        )
                    elif nb_field == "device_type":
                        # For device types, we need manufacturer
                        manufacturer_name = clean_value(get_nested_value(servicedesk_record, "vendor.name"))
                        if manufacturer_name:
                            manufacturer_name = to_pascal_case(manufacturer_name)

                        manufacturer_uuid = uuid_maps.get("manufacturer", {}).get(manufacturer_name)
                        if not manufacturer_uuid:
                            # Create manufacturer first
                            manufacturer_uuid = get_or_create_nautobot_object(
                                "/api/dcim/manufacturers/",
                                "name",
                                {"name": manufacturer_name},
                                log_rows,
                            )

                        if manufacturer_uuid:
                            object_id = get_or_create_nautobot_object(
                                "/api/dcim/device-types/",
                                "model",
                                {
                                    "model": value,
                                    "manufacturer": {"id": manufacturer_uuid},
                                    "slug": value.lower().replace(" ", "-").replace("/", "-")[:50],
                                },
                                log_rows,
                            )
                    elif nb_field == "device_family":
                        # Create device family
                        object_id = get_or_create_nautobot_object(
                            "/api/dcim/device-families/",
                            "name",
                            {"name": value},
                            log_rows,
                        )
                    elif nb_field == "location":
                        # Create location directly - no need for site in newer Nautobot
                        object_id = get_or_create_nautobot_object(
                            "/api/dcim/locations/",
                            "name",
                            {
                                "name": value,
                                "status": {"name": "Active"},  # Required field for locations
                                "location_type": {"name": "Site"},  # May need to be created first
                            },
                            log_rows,
                        )
                    elif nb_field == "tenant":
                        # Create tenant for organizational ownership
                        object_id = get_or_create_nautobot_object(
                            "/api/tenancy/tenants/", "name", {"name": value}, log_rows
                        )
                    elif nb_field == "status":
                        # Don't create status - it should already exist in Nautobot
                        # Log a warning if status is not found
                        if value not in uuid_maps.get("status", {}):
                            print(f"Warning: Status '{value}' not found in Nautobot. Using default 'active'.")
                            if "active" in uuid_maps.get("status", {}):
                                object_id = uuid_maps["status"]["active"]
                            else:
                                object_id = None
                        else:
                            object_id = uuid_maps["status"][value]

                    if object_id:
                        nautobot_device[nb_field] = {"id": object_id}
                        # Update the uuid_map for future use
                        if nb_field not in uuid_maps:
                            uuid_maps[nb_field] = {}
                        uuid_maps[nb_field][value] = object_id
                    else:
                        # Use default if creation failed
                        default_value = NAUTOBOT_DEFAULTS.get(nb_field)
                        if default_value and default_value in uuid_maps.get(nb_field, {}):
                            nautobot_device[nb_field] = {"id": uuid_maps[nb_field][default_value]}
            else:
                # Direct field mapping
                nautobot_device[nb_field] = value

    # Apply defaults for required fields if missing
    for field, default_value in NAUTOBOT_DEFAULTS.items():
        if field not in nautobot_device:
            uuid_map = uuid_maps.get(field, {})
            if default_value in uuid_map:
                nautobot_device[field] = {"id": uuid_map[default_value]}

    # Ensure name is present (required field) with smart fallback
    if "name" not in nautobot_device or not nautobot_device["name"]:
        # Primary: try UDF hostname field
        hostname = get_nested_value(servicedesk_record, "udf_fields.udf_sline_14115")
        if hostname and hostname.strip():
            nautobot_device["name"] = hostname.strip()
        else:
            # Fallback: use service tag
            service_tag = get_nested_value(servicedesk_record, "computer_system.service_tag")
            if service_tag:
                nautobot_device["name"] = service_tag
            else:
                # Final fallback: use original name or device ID
                nautobot_device["name"] = servicedesk_record.get(
                    "name", f"device-{servicedesk_record.get('id', 'unknown')}"
                )

    # Add custom fields
    power_type = extract_power_type(servicedesk_record)
    if power_type:
        nautobot_device["custom_fields"] = {"power_type": power_type}

    # Store interfaces separately for post-device creation
    # Get status ID to apply to interfaces (match device status)
    status_id = None
    if "status" in nautobot_device and "id" in nautobot_device["status"]:
        status_id = nautobot_device["status"]["id"]

    interfaces = create_basic_interfaces(servicedesk_record, status_id)

    return nautobot_device, interfaces


def chunks(iterable, size):
    """Split iterable into chunks of specified size."""
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk


def bulk_request(method, endpoint, records, log_rows, action_label):
    """Perform bulk API request to Nautobot."""
    if not records:
        return

    with httpx.Client(http2=True, verify=False, timeout=60.0) as client:
        for batch in chunks(records, BULK_SIZE):
            url = f"{NAUTOBOT_URL}{endpoint}"

            try:
                if method == "POST":
                    resp = client.post(url, headers=get_nautobot_headers(), json=batch)
                elif method == "PATCH":
                    resp = client.patch(url, headers=get_nautobot_headers(), json=batch)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                # Log each record in the batch
                for record in batch:
                    log_rows.append(
                        {
                            "name": record.get(UNIQUE_FIELD, ""),
                            "endpoint": endpoint,
                            "action": action_label,
                            "status_code": resp.status_code,
                            "response": (resp.text[:200] if len(resp.text) > 200 else resp.text),
                        }
                    )

                if resp.status_code in (200, 201):
                    print(f"✅ Bulk {action_label} {len(batch)} records")
                else:
                    print(f"❌ Bulk {action_label} failed - {resp.status_code}: {resp.text[:100]}")

            except Exception as e:
                print(f"❌ Error in bulk {action_label}: {e}")
                for record in batch:
                    log_rows.append(
                        {
                            "name": record.get(UNIQUE_FIELD, ""),
                            "endpoint": endpoint,
                            "action": f"failed_{action_label}",
                            "status_code": 0,
                            "response": str(e),
                        }
                    )


def create_device_interfaces(device_name, interfaces, log_rows):
    """Create network interfaces for a device in Nautobot."""
    if not interfaces:
        return

    print(f"🔌 Creating interfaces for device: {device_name}")

    # First, get the device ID from Nautobot
    device_id = None
    try:
        with httpx.Client(http2=True, verify=False, timeout=30.0) as client:
            resp = client.get(
                f"{NAUTOBOT_URL}/api/dcim/devices/",
                headers=get_nautobot_headers(),
                params={"name": device_name},
            )
            resp.raise_for_status()
            devices = resp.json().get("results", [])
            if devices:
                device_id = devices[0]["id"]
    except Exception as e:
        print(f"❌ Error getting device ID for {device_name}: {e}")
        return

    if not device_id:
        print(f"❌ Device {device_name} not found in Nautobot")
        return

    # Create interfaces
    created_interfaces = []
    for interface in interfaces:
        interface_data = interface.copy()
        interface_data["device"] = {"id": device_id}

        # Remove ip_address from interface data (we'll create it separately)
        ip_address = interface_data.pop("ip_address", None)

        try:
            with httpx.Client(http2=True, verify=False, timeout=30.0) as client:
                resp = client.post(
                    f"{NAUTOBOT_URL}/api/dcim/interfaces/",
                    headers=get_nautobot_headers(),
                    json=interface_data,
                )

                if resp.status_code in [200, 201]:
                    interface_obj = resp.json()
                    created_interfaces.append(interface_obj)
                    print(f"✅ Created interface {interface_data['name']} for {device_name}")

                    # Create IP address if we have one
                    if ip_address:
                        create_ip_address(device_name, interface_obj["id"], ip_address, log_rows)

                    log_rows.append(
                        {
                            "name": device_name,
                            "endpoint": "/api/dcim/interfaces/",
                            "action": "interface_created",
                            "status_code": resp.status_code,
                            "response": f"Created interface {interface_data['name']}",
                        }
                    )
                else:
                    print(f"❌ Failed to create interface {interface_data['name']}: {resp.status_code}")
                    log_rows.append(
                        {
                            "name": device_name,
                            "endpoint": "/api/dcim/interfaces/",
                            "action": "interface_failed",
                            "status_code": resp.status_code,
                            "response": resp.text[:200],
                        }
                    )
        except Exception as e:
            print(f"❌ Error creating interface {interface_data['name']}: {e}")
            log_rows.append(
                {
                    "name": device_name,
                    "endpoint": "/api/dcim/interfaces/",
                    "action": "interface_error",
                    "status_code": 0,
                    "response": str(e),
                }
            )

    # Set primary IP if we created interfaces with IPs
    if created_interfaces:
        set_primary_ip(device_id, device_name, created_interfaces, log_rows)


def create_ip_address(device_name, interface_id, ip_address, log_rows):
    """Create an IP address and assign it to an interface."""
    try:
        ip_data = {
            "address": ip_address,
            "status": "active",
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": interface_id,
        }

        with httpx.Client(http2=True, verify=False, timeout=30.0) as client:
            resp = client.post(
                f"{NAUTOBOT_URL}/api/ipam/ip-addresses/",
                headers=get_nautobot_headers(),
                json=ip_data,
            )

            if resp.status_code in [200, 201]:
                print(f"✅ Created IP address {ip_address} for {device_name}")
                log_rows.append(
                    {
                        "name": device_name,
                        "endpoint": "/api/ipam/ip-addresses/",
                        "action": "ip_created",
                        "status_code": resp.status_code,
                        "response": f"Created IP {ip_address}",
                    }
                )
                return resp.json()
            else:
                print(f"❌ Failed to create IP address {ip_address}: {resp.status_code}")
                log_rows.append(
                    {
                        "name": device_name,
                        "endpoint": "/api/ipam/ip-addresses/",
                        "action": "ip_failed",
                        "status_code": resp.status_code,
                        "response": resp.text[:200],
                    }
                )
    except Exception as e:
        print(f"❌ Error creating IP address {ip_address}: {e}")
        log_rows.append(
            {
                "name": device_name,
                "endpoint": "/api/ipam/ip-addresses/",
                "action": "ip_error",
                "status_code": 0,
                "response": str(e),
            }
        )
    return None


def set_primary_ip(device_id, device_name, interfaces, log_rows):
    """Set the primary IP for a device from its first interface with an IP."""
    try:
        # Find the first interface with an IP address
        primary_ip_id = None
        for interface in interfaces:
            # Get IP addresses assigned to this interface
            with httpx.Client(http2=True, verify=False, timeout=30.0) as client:
                resp = client.get(
                    f"{NAUTOBOT_URL}/api/ipam/ip-addresses/",
                    headers=get_nautobot_headers(),
                    params={"assigned_object_id": interface["id"]},
                )

                if resp.status_code == 200:
                    ips = resp.json().get("results", [])
                    if ips:
                        primary_ip_id = ips[0]["id"]
                        break

        if primary_ip_id:
            # Update device with primary IP
            device_data = {"primary_ip4": {"id": primary_ip_id}}

            with httpx.Client(http2=True, verify=False, timeout=30.0) as client:
                resp = client.patch(
                    f"{NAUTOBOT_URL}/api/dcim/devices/{device_id}/",
                    headers=get_nautobot_headers(),
                    json=device_data,
                )

                if resp.status_code in [200, 201]:
                    print(f"✅ Set primary IP for {device_name}")
                    log_rows.append(
                        {
                            "name": device_name,
                            "endpoint": "/api/dcim/devices/",
                            "action": "primary_ip_set",
                            "status_code": resp.status_code,
                            "response": "Set primary IP",
                        }
                    )
                else:
                    print(f"❌ Failed to set primary IP for {device_name}: {resp.status_code}")
    except Exception as e:
        print(f"❌ Error setting primary IP for {device_name}: {e}")
        log_rows.append(
            {
                "name": device_name,
                "endpoint": "/api/dcim/devices/",
                "action": "primary_ip_error",
                "status_code": 0,
                "response": str(e),
            }
        )


def push_create_or_update(dest_endpoint, records, log_rows):
    """Create or update devices in Nautobot."""
    print("🔄 Checking existing devices in Nautobot...")

    existing = get_all_from_api(f"{NAUTOBOT_URL}{dest_endpoint}", get_nautobot_headers())
    existing_map = {obj[UNIQUE_FIELD]: obj["id"] for obj in existing}

    to_create = []
    to_update = []

    for record in records:
        device_name = record.get(UNIQUE_FIELD)
        if device_name in existing_map:
            record["id"] = existing_map[device_name]
            to_update.append(record)
        else:
            to_create.append(record)

    print(f"📊 Found {len(to_create)} new devices to create")
    print(f"📊 Found {len(to_update)} existing devices to update")

    if to_create:
        bulk_request("POST", dest_endpoint, to_create, log_rows, "created")

    if to_update:
        bulk_request("PATCH", dest_endpoint, to_update, log_rows, "updated")


def write_log(log_rows, log_file=LOG_CSV):
    """Write operation log to CSV file."""
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["name", "endpoint", "action", "status_code", "response"]
    with open(log_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(log_rows)
    print(f"📝 Log written to {log_file}")


def export_data(data, export_file=DATA_EXPORT):
    """Export fetched data to JSON file for review."""
    Path(export_file).parent.mkdir(parents=True, exist_ok=True)

    with open(export_file, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"💾 ServiceDesk data exported to {export_file}")


def export_nautobot_data(nautobot_devices, export_file):
    """Export transformed Nautobot device objects to JSON file for review."""
    if export_file == "STDOUT":
        # Output to terminal
        print("\n🔧 Transformed Nautobot Device Objects (JSON):")
        print("=" * 60)
        print(json.dumps(nautobot_devices, indent=2, default=str))
        print("=" * 60)
    else:
        # Output to file
        Path(export_file).parent.mkdir(parents=True, exist_ok=True)

        with open(export_file, "w") as f:
            json.dump(nautobot_devices, f, indent=2, default=str)
        print(f"🔧 Nautobot device objects exported to {export_file}")


def main():
    """Main function for ServiceDesk to Nautobot import."""
    global SERVICEDESK_URL, SERVICEDESK_TOKEN, NAUTOBOT_URL, NAUTOBOT_TOKEN, BULK_SIZE

    parser = argparse.ArgumentParser(
        description="Import ServiceDesk workstations into Nautobot as devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:
    # Import all workstations
    python servicedesk_to_nautobot_import.py

    # Import first 50 workstations
    python servicedesk_to_nautobot_import.py --count 50

    # Test mode (validate only)
    python servicedesk_to_nautobot_import.py --dry-run --count 10

    # Export Nautobot objects to JSON for review
    python servicedesk_to_nautobot_import.py --dry-run --output-nautobot-json data/nautobot_devices.json

    # Show transformed objects in terminal
    python servicedesk_to_nautobot_import.py --dry-run --output-nautobot-json

    # Custom configuration
    python servicedesk_to_nautobot_import.py \\
        --servicedesk-url https://servicedesk.example.com \\
        --servicedesk-token your_token \\
        --nautobot-url https://nautobot.example.com \\
        --nautobot-token your_token

FIELD MAPPINGS:
    The tool maps ServiceDesk workstation fields to Nautobot device fields
    with automatic relationship resolution and object creation.

ENVIRONMENT SETUP:
    Required environment variables can be set via .env file:
    1. cp .env.template .env
    2. Edit .env with your actual tokens
    3. Run the script

    Or set via command line arguments (--servicedesk-token, --nautobot-token)
        """,
    )

    parser.add_argument("--count", type=int, help="Number of workstations to import (default: all)")
    parser.add_argument(
        "--servicedesk-url",
        default=SERVICEDESK_URL,
        help=f'ServiceDesk URL (default: {SERVICEDESK_URL or "from SERVICEDESK_URL env var"})',
    )
    parser.add_argument(
        "--servicedesk-token",
        default=SERVICEDESK_TOKEN,
        help="ServiceDesk API token (default: from SERVICEDESK_TOKEN env var)",
    )
    parser.add_argument(
        "--nautobot-url",
        default=NAUTOBOT_URL,
        help=f'Nautobot URL (default: {NAUTOBOT_URL or "from NAUTOBOT_URL env var"})',
    )
    parser.add_argument(
        "--nautobot-token",
        default=NAUTOBOT_TOKEN,
        help="Nautobot API token (default: from NAUTOBOT_TOKEN env var)",
    )
    parser.add_argument(
        "--bulk-size",
        type=int,
        default=BULK_SIZE,
        help=f"Records per API call (default: {BULK_SIZE})",
    )
    parser.add_argument("--log-file", default=LOG_CSV, help=f"Output log file (default: {LOG_CSV})")
    parser.add_argument(
        "--export-file",
        default=DATA_EXPORT,
        help=f"ServiceDesk data export file (default: {DATA_EXPORT})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate only, do not import data")
    parser.add_argument(
        "--output-nautobot-json",
        nargs="?",
        const="STDOUT",
        default=None,
        help="Output transformed Nautobot device objects to JSON file for review. If no filename provided, outputs to terminal.",
    )

    args = parser.parse_args()

    # Update configuration
    SERVICEDESK_URL = args.servicedesk_url
    SERVICEDESK_TOKEN = args.servicedesk_token
    NAUTOBOT_URL = args.nautobot_url
    NAUTOBOT_TOKEN = args.nautobot_token
    BULK_SIZE = args.bulk_size

    # Validate environment after configuration is set
    if not validate_environment():
        sys.exit(1)

    try:
        print("🚀 ServiceDesk to Nautobot Import Tool")
        print("=" * 50)
        print(f"🔗 ServiceDesk URL: {SERVICEDESK_URL}")
        print(f"🔗 Nautobot URL: {NAUTOBOT_URL}")
        print(f"📊 Bulk size: {BULK_SIZE}")
        print(f"📝 Log file: {args.log_file}")
        print(f"💾 Export file: {args.export_file}")
        if args.count:
            print(f"🔢 Import count: {args.count}")
        if args.dry_run:
            print("🧪 DRY RUN MODE - No data will be imported")
        print("")

        log_rows = []

        # Fetch ServiceDesk workstations
        servicedesk_workstations = fetch_servicedesk_workstations(count=args.count)

        if not servicedesk_workstations:
            print("⚠️  No workstations found in ServiceDesk")
            return 1

        # Export ServiceDesk data for review
        export_data(servicedesk_workstations, args.export_file)

        # Pre-fetch Nautobot relationship mappings
        print("🔄 Fetching Nautobot relationship mappings...")
        uuid_maps = {
            "manufacturer": get_uuid_map("/api/dcim/manufacturers/"),
            "device_type": get_uuid_map("/api/dcim/device-types/", "model"),
            "device_family": get_uuid_map("/api/dcim/device-families/"),
            "location": get_uuid_map("/api/dcim/locations/"),
            "tenant": get_uuid_map("/api/tenancy/tenants/"),
            "role": get_uuid_map("/api/extras/roles/"),
            "status": get_uuid_map("/api/extras/statuses/"),
        }

        for rel_type, uuid_map in uuid_maps.items():
            print(f"✅ Loaded {len(uuid_map)} {rel_type} mappings")

        # Transform ServiceDesk records to Nautobot format
        print("🔄 Transforming ServiceDesk records...")
        nautobot_devices = []
        device_interfaces = []  # Store interfaces separately

        for i, workstation in enumerate(servicedesk_workstations, 1):
            try:
                device, interfaces = transform_servicedesk_to_nautobot(workstation, uuid_maps, log_rows)
                nautobot_devices.append(device)
                device_interfaces.append((device["name"], interfaces))  # Store device name with its interfaces

                if i % 50 == 0:
                    print(f"📝 Processed {i}/{len(servicedesk_workstations)} records")

            except Exception as e:
                print(f"❌ Error transforming record {i}: {e}")
                log_rows.append(
                    {
                        "name": workstation.get("name", f"record-{i}"),
                        "endpoint": "transformation",
                        "action": "failed_transform",
                        "status_code": 0,
                        "response": str(e),
                    }
                )

        print(f"✅ Transformed {len(nautobot_devices)} devices for import")

        # Export transformed Nautobot objects to JSON if requested
        if args.output_nautobot_json:
            # Extract just the device data for export (without interfaces)
            devices_only = [device for device, _ in zip(nautobot_devices, device_interfaces)]
            export_nautobot_data(devices_only, args.output_nautobot_json)

            # Also show interfaces that would be created
            print("\n🔌 Network Interfaces to be Created:")
            print("============================================================")
            for device_name, interfaces in device_interfaces:
                print(f"\nDevice: {device_name}")
                for interface in interfaces:
                    print(f"  Interface: {json.dumps(interface, indent=4, default=str)}")
            print("============================================================")

        if args.dry_run:
            print("✅ Validation complete - all records processed successfully")
            print("💡 Use without --dry-run to perform actual import")

            # Write log for dry run
            write_log(log_rows, args.log_file)
            return 0

        # Import devices into Nautobot
        print("📤 Starting device import to Nautobot...")
        push_create_or_update(NAUTOBOT_ENDPOINT, nautobot_devices, log_rows)

        # Create interfaces for devices
        print("🔌 Creating network interfaces...")
        for device_name, interfaces in device_interfaces:
            try:
                create_device_interfaces(device_name, interfaces, log_rows)
            except Exception as e:
                print(f"❌ Error creating interfaces for {device_name}: {e}")
                log_rows.append(
                    {
                        "name": device_name,
                        "endpoint": "interfaces",
                        "action": "failed_interface_creation",
                        "status_code": 0,
                        "response": str(e),
                    }
                )

        # Write operation log
        write_log(log_rows, args.log_file)

        # Summary statistics
        success_count = sum(1 for log in log_rows if str(log["status_code"]).startswith("2"))
        error_count = len(log_rows) - success_count

        print("")
        print("📊 IMPORT SUMMARY")
        print("-" * 30)
        print(f"✅ Successful operations: {success_count}")
        print(f"❌ Failed operations: {error_count}")
        print(f"📝 Total operations: {len(log_rows)}")
        print(f"📱 ServiceDesk records processed: {len(servicedesk_workstations)}")
        print(f"🔧 Nautobot devices created/updated: {len(nautobot_devices)}")

        if error_count > 0:
            print(f"⚠️  Check {args.log_file} for error details")
            return 1
        else:
            print("🎉 All devices imported successfully!")
            return 0

    except Exception as e:
        print(f"❌ Error during import: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
