"""DiffSync adapters for nautobot_ssot_servicedesk_plus."""

import logging
import re

from diffsync import Adapter
from nautobot_ssot.contrib import NautobotAdapter

from nautobot_ssot_servicedesk_plus.diffsync.models import (
    DeviceSSoTModel,
    DeviceTypeSSoTModel,
    InterfaceSSoTModel,
    LocationSSoTModel,
    ManufacturerSSoTModel,
    TenantSSoTModel,
)
from nautobot_ssot_servicedesk_plus.utils.servicedesk_plus import (
    DEFAULT_LOCATION_TYPE,
    DEFAULT_ROLE,
    DEFAULT_STATUS,
    LOCATION_MAPPINGS,
    STATUS_MAPPINGS,
    get_nested_value,
)

logger = logging.getLogger(__name__)

INTERFACE_NAME = "em1_bond0"

# Placeholder asset_tag values that must be treated as "no asset tag" (None). Nautobot enforces
# global asset_tag uniqueness, so a literal shared placeholder like "n/a" collides across devices.
JUNK_ASSET_TAGS = {"", "n/a", "na", "n\\a", "none", "null", "-", "--", "tbd", "unknown"}


class ServicedeskPlusRemoteAdapter(Adapter):  # pylint: disable=too-few-public-methods
    """DiffSync adapter for loading data from ServiceDesk Plus."""

    manufacturer = ManufacturerSSoTModel
    device_type = DeviceTypeSSoTModel
    location = LocationSSoTModel
    tenant = TenantSSoTModel
    device = DeviceSSoTModel
    interface = InterfaceSSoTModel

    top_level = ["manufacturer", "device_type", "location", "tenant", "device", "interface"]

    def __init__(self, *args, job=None, sync=None, client=None, **kwargs):
        """Initialize the ServiceDesk Plus adapter.

        Args:
            *args: Variable length argument list.
            job: The SSoT job instance.
            sync: The SSoT sync instance.
            client: ServiceDeskPlusClient instance for API access.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.client = client
        # Store device→IP mapping for post-sync IP assignment
        self.device_primary_ips = {}

    def _extract_device_name(self, workstation):
        """Build device name from SDP name and UDF hostname.

        Format: {name}.{hostname} when both are available.
        Fallback: name → service_tag → device-{id}.
        """
        sdp_name = workstation.get("name")
        if isinstance(sdp_name, str):
            sdp_name = sdp_name.strip()
        if sdp_name in (None, "", "-", "N/A", "null"):
            sdp_name = None

        hostname = get_nested_value(workstation, "udf_fields.udf_sline_14115")

        if sdp_name and hostname:
            return f"{sdp_name}.{hostname}"
        if sdp_name:
            return sdp_name
        if hostname:
            return hostname

        service_tag = get_nested_value(workstation, "computer_system.service_tag")
        if service_tag:
            return str(service_tag).strip()

        return f"device-{workstation.get('id', 'unknown')}"

    def _extract_serial(self, workstation):
        """Extract serial number: SDP name first, then service_tag fallback."""
        name = workstation.get("name")
        if isinstance(name, str):
            name = name.strip()
        if name and name not in ("", "-", "N/A", "null"):
            return name

        service_tag = get_nested_value(workstation, "computer_system.service_tag")
        return str(service_tag).strip() if service_tag else ""

    def _extract_location_name(self, workstation):
        """Extract location name, handling both string and dict formats.

        Applies LOCATION_MAPPINGS to normalize known variants.
        """
        location = workstation.get("location")
        if isinstance(location, dict):
            name = location.get("name")
        elif isinstance(location, str) and location.strip() and location.strip() not in ("-", "N/A", "null"):
            name = location.strip()
        else:
            return None
        return LOCATION_MAPPINGS.get(name, name)

    def _extract_tenant_name(self, workstation):
        """Extract tenant name from ServiceDesk site.

        If site is "Common Site", infer the tenant from the server hostname's domain.
        Example: hostname "rad0.comporium.net" → tenant "Comporium".
        """
        site_name = get_nested_value(workstation, "site.name")

        if site_name and site_name != "Common Site":
            return site_name

        # Infer from hostname domain
        hostname = get_nested_value(workstation, "udf_fields.udf_sline_14115")
        if hostname:
            parts = hostname.split(".")
            if len(parts) >= 2:
                return parts[1].title()

        # Fall back to the literal site name if we can't infer
        return site_name

    def _extract_power_type(self, workstation):
        """Extract power type (AC/DC) from workstation.

        Priority: UDF power supply field → parse from model string.
        """
        power_type = get_nested_value(workstation, "udf_fields.udf_pick_8415")
        if power_type:
            return power_type.upper()

        model = get_nested_value(workstation, "computer_system.model") or ""
        match = re.search(r"\b(AC|DC)\b", model, re.IGNORECASE)
        if match:
            return match.group(1).upper()

        return None

    def _extract_primary_ip(self, workstation):
        """Extract primary IP address from workstation.

        Uses ip_addresses field (first entry if comma-separated).
        """
        ip_str = workstation.get("ip_addresses")
        if isinstance(ip_str, str) and ip_str.strip():
            # Take the first IP if comma-separated
            ip = ip_str.split(",")[0].strip()
            if ip and ip not in ("-", "N/A", "null"):
                return ip
        return None

    @staticmethod
    def _normalize_asset_tag(raw):
        """Return a real asset tag, or None for missing/placeholder values (e.g. 'n/a')."""
        value = (raw or "").strip()
        return None if value.lower() in JUNK_ASSET_TAGS else value

    def _extract_device_fields(self, workstation):
        """Extract and transform all device-related fields from a workstation.

        Args:
            workstation: Workstation dict from the ServiceDesk Plus API.

        Returns:
            dict: Dict with keys: name, serial, asset_tag, comments, status_name, role_name,
                manufacturer_name, device_type_model, location_name, tenant_name,
                power_type, idrac_ip, idrac_op_id, servicedesk_plus_id, primary_ip.
        """
        name = self._extract_device_name(workstation)
        serial = self._extract_serial(workstation)
        comments = get_nested_value(workstation, "description") or ""

        raw_status = get_nested_value(workstation, "state.name")
        status_name = STATUS_MAPPINGS.get(raw_status, DEFAULT_STATUS) if raw_status else DEFAULT_STATUS

        manufacturer_name = get_nested_value(workstation, "vendor.name")
        manufacturer_name = manufacturer_name.title() if manufacturer_name else "Generic"

        device_type_model = get_nested_value(workstation, "udf_fields.udf_sline_14122")
        if not device_type_model:
            device_type_model = get_nested_value(workstation, "computer_system.model")
        if not device_type_model:
            device_type_model = "Generic Device"

        return {
            "name": name,
            "serial": serial,
            "asset_tag": self._normalize_asset_tag(get_nested_value(workstation, "asset_tag")),
            "comments": comments,
            "status_name": status_name,
            "role_name": DEFAULT_ROLE,
            "manufacturer_name": manufacturer_name,
            "device_type_model": device_type_model,
            "location_name": self._extract_location_name(workstation) or "Default Location",
            "tenant_name": self._extract_tenant_name(workstation),
            "power_type": self._extract_power_type(workstation),
            "idrac_ip": get_nested_value(workstation, "udf_fields.udf_sline_14127"),
            "idrac_op_id": get_nested_value(workstation, "udf_fields.udf_sline_14128"),
            "servicedesk_plus_id": str(workstation.get("id", "")) or None,
            "primary_ip": self._extract_primary_ip(workstation),
        }

    def _add_related_objects(self, fields, seen):
        """Add deduplicated related objects (manufacturer, device_type, location, tenant).

        Args:
            fields: Dict of extracted device fields.
            seen: Dict of sets tracking already-added objects.
        """
        if fields["manufacturer_name"] not in seen["manufacturers"]:
            self.add(ManufacturerSSoTModel(name=fields["manufacturer_name"]))
            seen["manufacturers"].add(fields["manufacturer_name"])

        if fields["device_type_model"] not in seen["device_types"]:
            self.add(
                DeviceTypeSSoTModel(
                    model=fields["device_type_model"],
                    manufacturer__name=fields["manufacturer_name"],
                )
            )
            seen["device_types"].add(fields["device_type_model"])

        if fields["location_name"] not in seen["locations"]:
            self.add(
                LocationSSoTModel(
                    name=fields["location_name"],
                    location_type__name=DEFAULT_LOCATION_TYPE,
                    status__name="Active",
                )
            )
            seen["locations"].add(fields["location_name"])

        if fields["tenant_name"] and fields["tenant_name"] not in seen["tenants"]:
            self.add(TenantSSoTModel(name=fields["tenant_name"]))
            seen["tenants"].add(fields["tenant_name"])

    def load(self):
        """Load data from ServiceDesk Plus into DiffSync models."""
        workstations = self.client.get_workstations()
        self.job.logger.info("Loading %d workstations from ServiceDesk Plus", len(workstations))

        seen = {
            "manufacturers": set(),
            "device_types": set(),
            "locations": set(),
            "tenants": set(),
            "devices": set(),
            "asset_tags": {},
        }

        for workstation in workstations:
            fields = self._extract_device_fields(workstation)
            name = fields["name"]

            if not name or name in seen["devices"]:
                if name in seen["devices"]:
                    self.job.logger.warning("Skipping duplicate device name: %s", name)
                continue
            seen["devices"].add(name)

            # asset_tag is globally unique in Nautobot; a value repeated across SDP records
            # (a source data error) is kept on the first device and nulled on the rest.
            tag = fields["asset_tag"]
            if tag:
                if tag in seen["asset_tags"]:
                    self.job.logger.warning(
                        "SDP asset_tag %s duplicated (already on %s); nulling it on %s",
                        tag,
                        seen["asset_tags"][tag],
                        name,
                    )
                    fields["asset_tag"] = None
                else:
                    seen["asset_tags"][tag] = name

            if fields["primary_ip"]:
                self.device_primary_ips[name] = fields["primary_ip"]

            self._add_related_objects(fields, seen)

            self.add(
                DeviceSSoTModel(
                    name=name,
                    serial=fields["serial"],
                    asset_tag=fields["asset_tag"],
                    comments=fields["comments"],
                    status__name=fields["status_name"],
                    role__name=fields["role_name"],
                    device_type__model=fields["device_type_model"],
                    location__name=fields["location_name"],
                    tenant__name=fields["tenant_name"],
                    power_type=fields["power_type"],
                    idrac_ip=fields["idrac_ip"],
                    idrac_op_id=fields["idrac_op_id"],
                    servicedesk_plus_id=fields["servicedesk_plus_id"],
                )
            )

            if fields["primary_ip"]:
                self.add(
                    InterfaceSSoTModel(
                        name=INTERFACE_NAME,
                        device__name=name,
                        type="other",
                        status__name="Active",
                    )
                )

        self.job.logger.info(
            "Loaded %d devices, %d with IPs, %d manufacturers, %d device types, %d locations, %d tenants",
            len(seen["devices"]),
            len(self.device_primary_ips),
            len(seen["manufacturers"]),
            len(seen["device_types"]),
            len(seen["locations"]),
            len(seen["tenants"]),
        )


class ServicedeskPlusNautobotAdapter(NautobotAdapter):  # pylint: disable=too-few-public-methods
    """DiffSync adapter for loading data from Nautobot."""

    manufacturer = ManufacturerSSoTModel
    device_type = DeviceTypeSSoTModel
    location = LocationSSoTModel
    tenant = TenantSSoTModel
    device = DeviceSSoTModel
    interface = InterfaceSSoTModel

    top_level = ["manufacturer", "device_type", "location", "tenant", "device", "interface"]
