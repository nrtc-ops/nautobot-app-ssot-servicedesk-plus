"""Tests for the Nautobot-side ServiceDesk Plus SSoT adapter/models."""

from django.contrib.contenttypes.models import ContentType
from nautobot.core.testing import TestCase
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Role, Status

from nautobot_ssot_servicedesk_plus.diffsync.models import DeviceSSoTModel


class DeviceGetQuerysetTests(TestCase):
    """The Nautobot adapter must scope devices by the servicedesk_plus_id custom field.

    Keying on that id (not name) lets a device already carrying the id — e.g. from an
    earlier import that never applied the SSoT metadata stamp — be matched and updated
    instead of re-created (which fails on the unique asset_tag / per-location name).
    """

    @classmethod
    def setUpTestData(cls):
        """Create the servicedesk_plus_id custom field, device prerequisites, and two devices."""
        device_ct = ContentType.objects.get_for_model(Device)

        cf = CustomField.objects.create(
            key="servicedesk_plus_id",
            label="ServiceDesk Plus ID",
            type=CustomFieldTypeChoices.TYPE_TEXT,
        )
        cf.content_types.set([device_ct])

        # get_or_create (not get) so the test is independent of DB state: a preceding
        # TransactionTestCase in the suite truncates migration-created statuses.
        location_ct = ContentType.objects.get_for_model(Location)
        active, _ = Status.objects.get_or_create(name="Active")
        active.content_types.add(device_ct, location_ct)
        manufacturer = Manufacturer.objects.create(name="Test Manufacturer")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Test Model")
        role = Role.objects.create(name="Test Role")
        role.content_types.set([device_ct])
        location_type = LocationType.objects.create(name="Test Site")
        location_type.content_types.set([device_ct])
        location = Location.objects.create(name="Test Location", location_type=location_type, status=active)

        common = {
            "device_type": device_type,
            "role": role,
            "status": active,
            "location": location,
        }
        cls.with_id = Device.objects.create(name="has-sdp-id", **common)
        cls.with_id.cf["servicedesk_plus_id"] = "12345"
        cls.with_id.validated_save()
        cls.without_id = Device.objects.create(name="no-sdp-id", **common)
        # A non-SDP device (e.g. XCP/AWS import) that carries the CF but blank. It must be
        # excluded: several such devices would otherwise all load with an empty identifier
        # and collide (ObjectAlreadyExists).
        cls.blank_id = Device.objects.create(name="blank-sdp-id", **common)
        cls.blank_id.cf["servicedesk_plus_id"] = ""
        cls.blank_id.validated_save()

    def test_loads_only_devices_with_nonempty_servicedesk_plus_id(self):
        """get_queryset returns devices with a non-empty servicedesk_plus_id, excluding null/blank."""
        queryset = DeviceSSoTModel.get_queryset()
        self.assertIn(self.with_id, queryset)
        self.assertNotIn(self.without_id, queryset)
        self.assertNotIn(self.blank_id, queryset)
