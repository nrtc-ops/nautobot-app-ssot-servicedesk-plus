"""DiffSync adapters for nautobot_ssot_servicedesk_plus."""

import logging

from diffsync import Adapter
from nautobot_ssot.contrib import NautobotAdapter

from nautobot_ssot_servicedesk_plus.diffsync.models import (
    DeviceSSoTModel,
    DeviceTypeSSoTModel,
    LocationSSoTModel,
    ManufacturerSSoTModel,
    TenantSSoTModel,
)
from nautobot_ssot_servicedesk_plus.utils.servicedesk_plus import (
    DEFAULT_LOCATION_TYPE,
    DEFAULT_ROLE,
    DEFAULT_STATUS,
    STATUS_MAPPINGS,
    get_nested_value,
)

logger = logging.getLogger(__name__)


class ServicedeskPlusRemoteAdapter(Adapter):
    """DiffSync adapter for loading data from ServiceDesk Plus."""

    manufacturer = ManufacturerSSoTModel
    device_type = DeviceTypeSSoTModel
    location = LocationSSoTModel
    tenant = TenantSSoTModel
    device = DeviceSSoTModel

    top_level = ["manufacturer", "device_type", "location", "tenant", "device"]

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

    def _extract_device_name(self, workstation):
        """Extract the best available device name from a workstation record.

        Priority: UDF hostname → service tag → original name → device-{id}.
        """
        name = get_nested_value(workstation, "udf_fields.udf_sline_14115")
        if not name:
            name = get_nested_value(workstation, "computer_system.service_tag")
        if not name:
            name = workstation.get("name")
        if not name:
            name = f"device-{workstation.get('id', 'unknown')}"
        return str(name).strip()

    def _extract_location_name(self, workstation):
        """Extract location name, handling both string and dict formats."""
        location = workstation.get("location")
        if isinstance(location, dict):
            return location.get("name")
        if isinstance(location, str) and location.strip() and location.strip() not in ("-", "N/A", "null"):
            return location.strip()
        return None

    def load(self):
        """Load data from ServiceDesk Plus into DiffSync models."""
        workstations = self.client.get_workstations()
        self.job.logger.info("Loading %d workstations from ServiceDesk Plus", len(workstations))

        # Track unique related objects to avoid duplicate adds
        seen_manufacturers = set()
        seen_device_types = set()
        seen_locations = set()
        seen_tenants = set()
        seen_devices = set()

        for workstation in workstations:
            name = self._extract_device_name(workstation)
            if not name or name in seen_devices:
                if name in seen_devices:
                    self.job.logger.warning("Skipping duplicate device name: %s", name)
                continue
            seen_devices.add(name)

            # -- Extract and transform fields --

            serial = get_nested_value(workstation, "computer_system.service_tag") or ""
            asset_tag = get_nested_value(workstation, "asset_tag")
            comments = get_nested_value(workstation, "description") or ""

            # Status: map ServiceDesk state to Nautobot status
            raw_status = get_nested_value(workstation, "state.name")
            status_name = STATUS_MAPPINGS.get(raw_status, DEFAULT_STATUS) if raw_status else DEFAULT_STATUS

            # Role: all ServiceDesk devices get the default role
            role_name = DEFAULT_ROLE

            # Manufacturer: from vendor name, title-cased
            manufacturer_name = get_nested_value(workstation, "vendor.name")
            manufacturer_name = manufacturer_name.title() if manufacturer_name else "Generic"

            # Device type: prefer UDF model field, fall back to computer_system.model
            device_type_model = get_nested_value(workstation, "udf_fields.udf_sline_14122")
            if not device_type_model:
                device_type_model = get_nested_value(workstation, "computer_system.model")
            if not device_type_model:
                device_type_model = "Generic Device"

            # Location
            location_name = self._extract_location_name(workstation) or "Default Location"

            # Tenant: mapped from ServiceDesk site
            tenant_name = get_nested_value(workstation, "site.name")

            # -- Add related objects (deduplicated) --

            if manufacturer_name not in seen_manufacturers:
                self.add(ManufacturerSSoTModel(name=manufacturer_name))
                seen_manufacturers.add(manufacturer_name)

            if device_type_model not in seen_device_types:
                self.add(
                    DeviceTypeSSoTModel(
                        model=device_type_model,
                        manufacturer__name=manufacturer_name,
                    )
                )
                seen_device_types.add(device_type_model)

            if location_name not in seen_locations:
                self.add(
                    LocationSSoTModel(
                        name=location_name,
                        location_type__name=DEFAULT_LOCATION_TYPE,
                        status__name="Active",
                    )
                )
                seen_locations.add(location_name)

            if tenant_name and tenant_name not in seen_tenants:
                self.add(TenantSSoTModel(name=tenant_name))
                seen_tenants.add(tenant_name)

            # -- Add device --

            self.add(
                DeviceSSoTModel(
                    name=name,
                    serial=serial,
                    asset_tag=asset_tag if asset_tag else None,
                    comments=comments,
                    status__name=status_name,
                    role__name=role_name,
                    device_type__model=device_type_model,
                    location__name=location_name,
                    tenant__name=tenant_name,
                )
            )

        self.job.logger.info(
            "Loaded %d devices, %d manufacturers, %d device types, %d locations, %d tenants",
            len(seen_devices),
            len(seen_manufacturers),
            len(seen_device_types),
            len(seen_locations),
            len(seen_tenants),
        )


class ServicedeskPlusNautobotAdapter(NautobotAdapter):
    """DiffSync adapter for loading data from Nautobot."""

    manufacturer = ManufacturerSSoTModel
    device_type = DeviceTypeSSoTModel
    location = LocationSSoTModel
    tenant = TenantSSoTModel
    device = DeviceSSoTModel

    top_level = ["manufacturer", "device_type", "location", "tenant", "device"]
