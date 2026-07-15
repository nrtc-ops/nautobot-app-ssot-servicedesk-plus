"""Tests for SDP-as-SoT asset_tag reconciliation (ServicedeskPlusDataSource._reconcile_asset_tags)."""

from types import SimpleNamespace

from django.contrib.contenttypes.models import ContentType
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, JobResult, Role, Status

from nautobot_ssot_servicedesk_plus.diffsync.models import DeviceSSoTModel
from nautobot_ssot_servicedesk_plus.jobs import ServicedeskPlusDataSource


class AssetTagReconcileTests(TransactionTestCase):
    """Verify the pre-sync reconcile resolves asset_tag collisions in SDP's favour."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Create the CF, prerequisites, roles, and a job with a stubbed source adapter."""
        super().setUp()
        device_ct = ContentType.objects.get_for_model(Device)
        cf, _ = CustomField.objects.get_or_create(
            key="servicedesk_plus_id",
            defaults={"label": "ServiceDesk Plus ID", "type": CustomFieldTypeChoices.TYPE_TEXT},
        )
        cf.content_types.add(device_ct)
        self.active, _ = Status.objects.get_or_create(name="Active")
        self.active.content_types.add(device_ct, ContentType.objects.get_for_model(Location))
        manufacturer = Manufacturer.objects.create(name="Test Manufacturer")
        self.device_type = DeviceType.objects.create(manufacturer=manufacturer, model="Test Model")
        self.nus, _ = Role.objects.get_or_create(name="NUS")
        self.nus.content_types.add(device_ct)
        self.infra, _ = Role.objects.get_or_create(name="Router")
        self.infra.content_types.add(device_ct)
        location_type = LocationType.objects.create(name="Test Site")
        location_type.content_types.add(device_ct)
        self.location = Location.objects.create(name="Loc", location_type=location_type, status=self.active)
        self.job = ServicedeskPlusDataSource()
        self.job.job_result = JobResult.objects.create(name=self.job.class_path)
        self.job.dryrun = False

    def _device(self, name, asset_tag=None, serial="", role=None, sdp_id=None):  # pylint: disable=too-many-arguments
        device = Device.objects.create(
            name=name,
            device_type=self.device_type,
            role=role or self.nus,
            status=self.active,
            location=self.location,
            asset_tag=asset_tag,
            serial=serial,
        )
        if sdp_id is not None:
            device.cf["servicedesk_plus_id"] = sdp_id
            device.validated_save()
        return device

    def _run(self, models, dry_run=False):
        self.job.source_adapter = SimpleNamespace(get_all=lambda _model: models)
        self.job._reconcile_asset_tags(dry_run)  # pylint: disable=protected-access

    def test_adopt_same_serial(self):
        """An unclaimed NUS device with the same serial is adopted (CF stamped), tag kept."""
        holder = self._device("old-name", asset_tag="T1", serial="S1")
        src = DeviceSSoTModel(name="new.name", servicedesk_plus_id="100", asset_tag="T1", serial="S1")
        self._run([src])
        holder.refresh_from_db()
        self.assertEqual(holder.cf["servicedesk_plus_id"], "100")
        self.assertEqual(src.asset_tag, "T1")

    def test_delete_stale_unclaimed_different_serial(self):
        """An unclaimed NUS device of different hardware is deleted so SDP can take the tag."""
        self._device("stale", asset_tag="T2", serial="SX")
        src = DeviceSSoTModel(name="n", servicedesk_plus_id="200", asset_tag="T2", serial="SDIFF")
        self._run([src])
        self.assertFalse(Device.objects.filter(asset_tag="T2").exists())
        self.assertEqual(src.asset_tag, "T2")

    def test_drop_tag_when_owned_by_other_sdp_device(self):
        """When another SDP device owns the tag, the source record drops its tag; holder untouched."""
        holder = self._device("owned", asset_tag="T3", serial="SY", sdp_id="999")
        src = DeviceSSoTModel(name="n", servicedesk_plus_id="300", asset_tag="T3", serial="SZ")
        self._run([src])
        self.assertIsNone(src.asset_tag)
        holder.refresh_from_db()
        self.assertEqual(holder.asset_tag, "T3")
        self.assertEqual(holder.cf["servicedesk_plus_id"], "999")

    def test_non_nus_holder_never_touched(self):
        """A non-NUS holder is never modified even on a serial match; the source drops its tag."""
        holder = self._device("infra-box", asset_tag="T4", serial="SI", role=self.infra)
        src = DeviceSSoTModel(name="n", servicedesk_plus_id="400", asset_tag="T4", serial="SI")
        self._run([src])
        self.assertIsNone(src.asset_tag)
        holder.refresh_from_db()
        self.assertEqual(holder.asset_tag, "T4")

    def test_dry_run_performs_no_writes(self):
        """In dry-run, an adopt-eligible holder is not stamped and nothing is changed."""
        holder = self._device("old", asset_tag="T5", serial="S5")
        src = DeviceSSoTModel(name="n", servicedesk_plus_id="500", asset_tag="T5", serial="S5")
        self._run([src], dry_run=True)
        holder.refresh_from_db()
        self.assertIsNone(holder.cf.get("servicedesk_plus_id"))
        self.assertEqual(src.asset_tag, "T5")
