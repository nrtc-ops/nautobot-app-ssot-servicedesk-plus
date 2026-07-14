"""DiffSync models for nautobot_ssot_servicedesk_plus."""

from typing import Annotated, Optional

from diffsync.enum import DiffSyncModelFlags
from nautobot.dcim.models import Device, DeviceType, Interface, Location, Manufacturer
from nautobot.extras.models import MetadataType
from nautobot.tenancy.models import Tenant
from nautobot_ssot.contrib import CustomFieldAnnotation, NautobotModel

from nautobot_ssot_servicedesk_plus.utils.geo import ensure_region_parent

SDP_METADATA_NAME = "Last sync from ServiceDesk Plus"


class ManufacturerSSoTModel(NautobotModel):
    """SSoT model for hardware manufacturers (e.g., Dell, HP)."""

    _model = Manufacturer
    _modelname = "manufacturer"
    _identifiers = ("name",)
    _attributes = ()
    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    name: str


class DeviceTypeSSoTModel(NautobotModel):
    """SSoT model for device types / hardware models (e.g., PowerEdge R340)."""

    _model = DeviceType
    _modelname = "device_type"
    _identifiers = ("model",)
    _attributes = ("manufacturer__name",)
    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    model: str
    manufacturer__name: Optional[str] = None


class LocationSSoTModel(NautobotModel):
    """SSoT model for physical locations."""

    _model = Location
    _modelname = "location"
    _identifiers = ("name", "location_type__name")
    _attributes = ("status__name",)
    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    name: str
    location_type__name: Optional[str] = "Site"
    status__name: Optional[str] = "Active"
    # Set only on create (see create()); intentionally NOT in _attributes so that a later
    # reconciliation which re-groups a Site into its real Region is never reverted on sync.
    parent__name: Optional[str] = None

    @classmethod
    def create(cls, adapter, ids, attrs):
        """Give new Sites a Region parent (the Site LocationType requires one).

        ServiceDesk can't reliably supply a geographic region, so we resolve it from the
        site name's US state — creating the Region on demand — and fall back to an
        'Unassigned' holding pen when the state can't be parsed.
        """
        attrs = dict(attrs)
        attrs["parent__name"] = ensure_region_parent(ids["name"])
        return super().create(adapter, ids, attrs)


class TenantSSoTModel(NautobotModel):
    """SSoT model for tenants (mapped from ServiceDesk Plus sites)."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ()
    model_flags: DiffSyncModelFlags = DiffSyncModelFlags.SKIP_UNMATCHED_DST

    name: str


class DeviceSSoTModel(NautobotModel):
    """SSoT model for devices (mapped from ServiceDesk Plus workstations)."""

    _model = Device
    _modelname = "device"
    # Identify devices by the ServiceDesk Plus record id (a stable, globally-unique source
    # key that survives rename/move), NOT by name. Nautobot uses DEVICE_UNIQUENESS=
    # location_tenant_name (name unique per location+tenant) and a globally-unique asset_tag,
    # so a name-based identifier fails to match existing devices and collides on create.
    _identifiers = ("servicedesk_plus_id",)
    _attributes = (
        "name",
        "serial",
        "asset_tag",
        "comments",
        "status__name",
        "role__name",
        "device_type__model",
        "location__name",
        "tenant__name",
        "power_type",
        "idrac_ip",
        "idrac_op_id",
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
    idrac_ip: Annotated[Optional[str], CustomFieldAnnotation(key="idrac_ip")] = None
    idrac_op_id: Annotated[Optional[str], CustomFieldAnnotation(key="idrac_op_id")] = None
    servicedesk_plus_id: Annotated[Optional[str], CustomFieldAnnotation(key="servicedesk_plus_id")] = None

    @classmethod
    def get_queryset(cls):
        """Load SSoT-managed devices: those carrying a servicedesk_plus_id.

        Scoping by the servicedesk_plus_id custom field (the identifier) rather than by the
        SSoT metadata stamp lets devices that already carry the id — e.g. from an earlier
        import that never applied the stamp — be matched and UPDATED instead of re-created
        (which fails on the globally-unique asset_tag / per-location-tenant name).

        The empty string is excluded as well as null: unrelated devices (e.g. XCP/AWS
        imports) carry the field blank, and loading several with an empty identifier would
        collide (ObjectAlreadyExists) on the diffsync store.
        """
        return cls._model.objects.filter(_custom_field_data__servicedesk_plus_id__isnull=False).exclude(
            _custom_field_data__servicedesk_plus_id=""
        )


class InterfaceSSoTModel(NautobotModel):
    """SSoT model for device network interfaces."""

    _model = Interface
    _modelname = "interface"
    _identifiers = ("name", "device__name")
    _attributes = ("type", "status__name")

    name: str
    device__name: str
    type: str = "other"
    status__name: Optional[str] = "Active"

    @classmethod
    def get_queryset(cls):
        """Only load interfaces managed by the ServiceDesk Plus SSoT sync."""
        try:
            mt = MetadataType.objects.get(name=SDP_METADATA_NAME)
            return cls._model.objects.filter(associated_object_metadata__metadata_type=mt)
        except MetadataType.DoesNotExist:
            return cls._model.objects.none()
