"""Test ServiceDesk Plus adapter."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import JobResult

from nautobot_ssot_servicedesk_plus.diffsync.adapters import ServicedeskPlusRemoteAdapter
from nautobot_ssot_servicedesk_plus.jobs import ServicedeskPlusDataSource


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


FIXTURES_DIR = Path(__file__).parent / "fixtures"
WORKSTATION_FIXTURE = load_json(FIXTURES_DIR / "get_devices.json")


class TestServicedeskPlusRemoteAdapter(TransactionTestCase):
    """Test ServicedeskPlusRemoteAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Initialize test case."""
        self.client = MagicMock()
        self.client.get_workstations.return_value = WORKSTATION_FIXTURE

        self.job = ServicedeskPlusDataSource()
        self.job.job_result = JobResult.objects.create(name=self.job.class_path)
        self.adapter = ServicedeskPlusRemoteAdapter(job=self.job, sync=None, client=self.client)

    def test_load_calls_get_workstations(self):
        """Verify load() calls client.get_workstations()."""
        self.adapter.load()
        self.client.get_workstations.assert_called_once()

    def test_load_device_count(self):
        """Verify correct number of devices loaded (duplicates and empty names excluded)."""
        self.adapter.load()
        devices = self.adapter.get_all("device")
        # 10 fixtures: 1006 gets name from service_tag, 1008 is duplicate of 1007 (same UDF hostname) = 9
        self.assertEqual(len(devices), 9)

    def test_udf_hostname_preferred_over_name(self):
        """Verify UDF hostname field is used as device name when available."""
        self.adapter.load()
        device_names = {d.name for d in self.adapter.get_all("device")}
        # Device 1001 has UDF hostname "ws-okc-desk01.nrtc.coop", not "DESKTOP-ABC123"
        self.assertIn("ws-okc-desk01.nrtc.coop", device_names)
        self.assertNotIn("DESKTOP-ABC123", device_names)

    def test_service_tag_fallback_for_name(self):
        """Verify service_tag is used as name when UDF hostname and name are empty."""
        self.adapter.load()
        device_names = {d.name for d in self.adapter.get_all("device")}
        # Device 1006: empty name, empty UDF, but has service_tag SVCTAG006
        self.assertIn("SVCTAG006", device_names)

    def test_duplicate_hostname_skipped(self):
        """Verify second device with same UDF hostname is skipped."""
        self.adapter.load()
        devices = self.adapter.get_all("device")
        dupe_devices = [d for d in devices if d.name == "dupe-host.nrtc.coop"]
        self.assertEqual(len(dupe_devices), 1)

    def test_status_mapping_in_use(self):
        """Verify 'In Use' maps to 'Active'."""
        self.adapter.load()
        device = self._get_device("ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.status__name, "Active")

    def test_status_mapping_deployed(self):
        """Verify 'Deployed' maps to 'Active'."""
        self.adapter.load()
        device = self._get_device("lt-tulsa-tech01.nrtc.coop")
        self.assertEqual(device.status__name, "Active")

    def test_status_mapping_in_store(self):
        """Verify 'In Store' maps to 'Inventory'."""
        self.adapter.load()
        # Device 1004: no UDF hostname, falls back to service_tag "HPSVCTAG01"
        device = self._get_device("HPSVCTAG01")
        self.assertEqual(device.status__name, "Inventory")

    def test_status_mapping_retired(self):
        """Verify 'Retired' maps to 'Decommissioning'."""
        self.adapter.load()
        device = self._get_device("srv-old-retire.nrtc.coop")
        self.assertEqual(device.status__name, "Decommissioning")

    def test_status_mapping_maintenance(self):
        """Verify 'Maintenance' maps to 'Planned'."""
        self.adapter.load()
        device = self._get_device("sw-okc-maint01.nrtc.coop")
        self.assertEqual(device.status__name, "Planned")

    def test_status_mapping_faulty(self):
        """Verify 'Faulty' maps to 'Failed'."""
        self.adapter.load()
        device = self._get_device("ws-faulty01.nrtc.coop")
        self.assertEqual(device.status__name, "Failed")

    def test_default_status_when_state_missing(self):
        """Verify default 'Active' status when state is null."""
        self.adapter.load()
        device = self._get_device("SVCTAG006")
        self.assertEqual(device.status__name, "Active")

    def test_manufacturer_title_cased(self):
        """Verify manufacturer names are title-cased."""
        self.adapter.load()
        manufacturers = self.adapter.get_all("manufacturer")
        mfr_names = {m.name for m in manufacturers}
        # "DELL" -> "Dell", "HP" -> "Hp", "LENOVO" -> "Lenovo"
        self.assertIn("Dell", mfr_names)
        self.assertIn("Hp", mfr_names)
        self.assertIn("Lenovo", mfr_names)

    def test_manufacturer_deduplication(self):
        """Verify manufacturers are deduplicated."""
        self.adapter.load()
        manufacturers = self.adapter.get_all("manufacturer")
        mfr_names = [m.name for m in manufacturers]
        # "Dell" appears in many fixtures but should only be added once
        self.assertEqual(mfr_names.count("Dell"), 1)

    def test_device_type_udf_preferred(self):
        """Verify UDF device type field is preferred over computer_system.model."""
        self.adapter.load()
        device = self._get_device("ws-okc-desk01.nrtc.coop")
        # UDF field has "OptiPlex 7090 SFF", computer_system.model has "OptiPlex 7090"
        self.assertEqual(device.device_type__model, "OptiPlex 7090 SFF")

    def test_device_type_fallback_to_model(self):
        """Verify computer_system.model is used when UDF device type is missing."""
        self.adapter.load()
        device = self._get_device("sw-okc-maint01.nrtc.coop")
        # Device 1009 has no udf_sline_14122 but has computer_system.model = null
        # Both missing, should fall back to "Generic Device"
        self.assertEqual(device.device_type__model, "Generic Device")

    def test_location_from_dict(self):
        """Verify location extracted from dict format."""
        self.adapter.load()
        device = self._get_device("ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.location__name, "Oklahoma City")

    def test_location_from_string(self):
        """Verify location extracted from plain string format."""
        self.adapter.load()
        device = self._get_device("HPSVCTAG01")
        self.assertEqual(device.location__name, "Norman Warehouse")

    def test_location_invalid_string_defaults(self):
        """Verify invalid location strings (like '-') fall back to default."""
        self.adapter.load()
        device = self._get_device("ws-faulty01.nrtc.coop")
        self.assertEqual(device.location__name, "Default Location")

    def test_location_deduplication(self):
        """Verify locations are deduplicated."""
        self.adapter.load()
        locations = self.adapter.get_all("location")
        loc_names = [loc.name for loc in locations]
        # "Oklahoma City" appears in many fixtures but should only be added once
        self.assertEqual(loc_names.count("Oklahoma City"), 1)

    def test_tenant_from_site(self):
        """Verify tenant is mapped from ServiceDesk site."""
        self.adapter.load()
        device = self._get_device("ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.tenant__name, "NRTC HQ")

    def test_tenant_none_when_site_missing(self):
        """Verify tenant is None when site is null."""
        self.adapter.load()
        device = self._get_device("SVCTAG006")
        self.assertIsNone(device.tenant__name)

    def test_serial_from_service_tag(self):
        """Verify serial is populated from service_tag."""
        self.adapter.load()
        device = self._get_device("ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.serial, "SVCTAG001")

    def test_asset_tag(self):
        """Verify asset_tag is populated."""
        self.adapter.load()
        device = self._get_device("ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.asset_tag, "NRTC-0001")

    def test_null_asset_tag(self):
        """Verify null asset_tag is stored as None."""
        self.adapter.load()
        device = self._get_device("HPSVCTAG01")
        self.assertIsNone(device.asset_tag)

    def test_comments(self):
        """Verify description maps to comments."""
        self.adapter.load()
        device = self._get_device("ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.comments, "Main office workstation")

    def test_default_role(self):
        """Verify all devices get the default NUS role."""
        self.adapter.load()
        for device in self.adapter.get_all("device"):
            self.assertEqual(device.role__name, "NUS")

    def test_generic_manufacturer_when_vendor_missing(self):
        """Verify 'Generic' manufacturer when vendor is null."""
        self.adapter.load()
        device = self._get_device("SVCTAG006")
        self.assertEqual(device.device_type__model, "Generic Device")
        manufacturers = self.adapter.get_all("manufacturer")
        mfr_names = {m.name for m in manufacturers}
        self.assertIn("Generic", mfr_names)

    def test_device_type_deduplication(self):
        """Verify device types are deduplicated."""
        self.adapter.load()
        device_types = self.adapter.get_all("device_type")
        dt_models = [dt.model for dt in device_types]
        # "ThinkCentre M920" appears in both 1007 and 1008 but should only be added once
        self.assertEqual(dt_models.count("ThinkCentre M920"), 1)

    def _get_device(self, name):
        """Helper to get a device by name from the adapter."""
        for device in self.adapter.get_all("device"):
            if device.name == name:
                return device
        self.fail(f"Device '{name}' not found. Available: {[d.name for d in self.adapter.get_all('device')]}")
