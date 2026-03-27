"""DiffSync models for nautobot_ssot_servicedesk_plus."""

from typing import Annotated, Optional

from nautobot.dcim.models import Device, DeviceType, Location, Manufacturer
from nautobot.tenancy.models import Tenant
from nautobot_ssot.contrib import CustomFieldAnnotation, NautobotModel


class ManufacturerSSoTModel(NautobotModel):
    """SSoT model for hardware manufacturers (e.g., Dell, HP)."""

    _model = Manufacturer
    _modelname = "manufacturer"
    _identifiers = ("name",)
    _attributes = ()

    name: str


class DeviceTypeSSoTModel(NautobotModel):
    """SSoT model for device types / hardware models (e.g., PowerEdge R340)."""

    _model = DeviceType
    _modelname = "device_type"
    _identifiers = ("model",)
    _attributes = ("manufacturer__name",)

    model: str
    manufacturer__name: Optional[str] = None


class LocationSSoTModel(NautobotModel):
    """SSoT model for physical locations."""

    _model = Location
    _modelname = "location"
    _identifiers = ("name", "location_type__name")
    _attributes = ("status__name",)

    name: str
    location_type__name: Optional[str] = "Site"
    status__name: Optional[str] = "Active"


class TenantSSoTModel(NautobotModel):
    """SSoT model for tenants (mapped from ServiceDesk Plus sites)."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ()

    name: str


class DeviceSSoTModel(NautobotModel):
    """SSoT model for devices (mapped from ServiceDesk Plus workstations)."""

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "serial",
        "asset_tag",
        "comments",
        "status__name",
        "role__name",
        "device_type__model",
        "location__name",
        "tenant__name",
        "power_type",
    )

    name: str
    serial: Optional[str] = ""
    asset_tag: Optional[str] = None
    comments: Optional[str] = ""
    status__name: Optional[str] = None
    role__name: Optional[str] = None
    device_type__model: Optional[str] = None
    location__name: Optional[str] = None
    tenant__name: Optional[str] = None
    power_type: Annotated[Optional[str], CustomFieldAnnotation(key="power_type")] = None
