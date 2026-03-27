#!/usr/bin/env python3
"""ServiceDesk API Data Fetcher.

Simple script to fetch workstation data from ServiceDesk API.
Useful for exploring data structure and testing API connectivity.

USAGE:
    python servicedesk_api_fetch.py [--count 20] [--output data.json]

Requires SERVICEDESK_URL and SERVICEDESK_TOKEN environment variables,
either exported or defined in a .env file in the project root.
"""

import argparse
import json
import os
from pathlib import Path

import requests
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip().removeprefix("export ")
                    value = value.strip().strip('"').strip("'")
                    if key not in os.environ:
                        os.environ[key] = value


load_env_file()

SERVICEDESK_URL = os.getenv("SERVICEDESK_URL")
SERVICEDESK_TOKEN = os.getenv("SERVICEDESK_TOKEN")


def fetch_workstations(count=20, start_index=0, output_file=None):
    """Fetch workstation data from ServiceDesk API."""
    if not SERVICEDESK_URL or not SERVICEDESK_TOKEN:
        print("Missing SERVICEDESK_URL or SERVICEDESK_TOKEN.")
        print("Set them as environment variables or in a .env file.")
        return None

    url = f"{SERVICEDESK_URL}/api/v3/workstations"
    headers = {"authtoken": SERVICEDESK_TOKEN}

    input_data = {
        "list_info": {
            "row_count": count,
            "start_index": start_index,
            "sort_field": "id",
            "sort_order": "asc",
            "get_total_count": True,
        }
    }

    params = {"input_data": json.dumps(input_data)}

    try:
        print(f"Fetching {count} workstations from ServiceDesk...")
        response = requests.get(url, headers=headers, params=params, verify=False)
        response.raise_for_status()

        data = response.json()

        print(f"Response Status: {response.status_code}")

        if data.get("response_status", [{}])[0].get("status") == "success":
            workstations = data.get("workstations", [])
            list_info = data.get("list_info", {})

            print(f"Fetched {len(workstations)} workstations")
            print(f"Total available: {list_info.get('total_count', 'unknown')}")
            print(f"Has more: {list_info.get('has_more_rows', False)}")

            if output_file:
                Path(output_file).parent.mkdir(parents=True, exist_ok=True)
                with open(output_file, "w") as f:
                    json.dump(data, f, indent=2)
                print(f"Data saved to {output_file}")

            if workstations:
                print("\nSample workstation data structure:")
                sample = workstations[0]
                print(f"ID: {sample.get('id')}")
                print(f"Name: {sample.get('name')}")
                print(f"Location: {sample.get('location')}")
                print(f"Site: {sample.get('site', {}).get('name', 'N/A')}")
                print(f"Manufacturer: {sample.get('computer_system', {}).get('system_manufacturer', 'N/A')}")
                print(f"Model: {sample.get('computer_system', {}).get('model', 'N/A')}")
                print(f"Service Tag: {sample.get('computer_system', {}).get('service_tag', 'N/A')}")
                print(f"Asset Tag: {sample.get('asset_tag', 'N/A')}")
                print(f"Status: {sample.get('state', {}).get('name', 'N/A')}")
                print(f"Product Type: {sample.get('product_type', {}).get('name', 'N/A')}")

            return data
        else:
            print(f"ServiceDesk API error: {data}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return None


def main():
    """Run the ServiceDesk API data fetcher."""
    parser = argparse.ArgumentParser(description="Fetch workstation data from ServiceDesk API")
    parser.add_argument("--count", type=int, default=20, help="Number of records to fetch (default: 20)")
    parser.add_argument("--start", type=int, default=0, help="Starting index (default: 0)")
    parser.add_argument("--output", help="Output JSON file path")

    args = parser.parse_args()

    result = fetch_workstations(count=args.count, start_index=args.start, output_file=args.output)

    if result:
        print("Data fetch completed successfully")
        return 0
    else:
        print("Data fetch failed")
        return 1


if __name__ == "__main__":
    exit(main())
