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

    # -- Device name: {name}.{hostname} --

    def test_device_name_combines_name_and_hostname(self):
        """Verify device name is {SDP name}.{UDF hostname} when both exist."""
        self.adapter.load()
        device_names = {d.name for d in self.adapter.get_all("device")}
        # Device 1001: name="DESKTOP-ABC123", hostname="ws-okc-desk01.nrtc.coop"
        self.assertIn("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop", device_names)

    def test_device_name_sdp_name_only_when_no_hostname(self):
        """Verify SDP name alone is used when no UDF hostname."""
        self.adapter.load()
        device_names = {d.name for d in self.adapter.get_all("device")}
        # Device 1004: name="HP-SPARE-01", no UDF hostname
        self.assertIn("HP-SPARE-01", device_names)

    def test_device_name_fallback_to_service_tag(self):
        """Verify service_tag is used when both name and hostname are empty."""
        self.adapter.load()
        device_names = {d.name for d in self.adapter.get_all("device")}
        # Device 1006: empty name, empty UDF, has service_tag SVCTAG006
        self.assertIn("SVCTAG006", device_names)

    def test_load_device_count(self):
        """Verify correct number of devices loaded (duplicates excluded)."""
        self.adapter.load()
        devices = self.adapter.get_all("device")
        # 12 fixtures, all unique combined names
        self.assertEqual(len(devices), 12)

    def test_duplicate_combined_name_skipped(self):
        """Verify second device with identical combined name is skipped."""
        # Manually create a fixture with truly duplicate combined names
        dupes = [
            {
                "id": "2001",
                "name": "SAME",
                "udf_fields": {"udf_sline_14115": "host.nrtc.coop"},
                "computer_system": {"service_tag": "TAG1"},
                "vendor": {"name": "DELL"},
                "state": {"name": "In Use"},
            },
            {
                "id": "2002",
                "name": "SAME",
                "udf_fields": {"udf_sline_14115": "host.nrtc.coop"},
                "computer_system": {"service_tag": "TAG2"},
                "vendor": {"name": "DELL"},
                "state": {"name": "In Use"},
            },
        ]
        self.client.get_workstations.return_value = dupes
        adapter = ServicedeskPlusRemoteAdapter(job=self.job, sync=None, client=self.client)
        adapter.load()
        devices = adapter.get_all("device")
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].name, "SAME.host.nrtc.coop")

    # -- Serial: SDP name → service_tag fallback --

    def test_serial_from_sdp_name(self):
        """Verify serial is populated from SDP name field."""
        self.adapter.load()
        device = self._get_device("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.serial, "DESKTOP-ABC123")

    def test_serial_fallback_to_service_tag(self):
        """Verify serial falls back to service_tag when name is empty."""
        self.adapter.load()
        device = self._get_device("SVCTAG006")
        self.assertEqual(device.serial, "SVCTAG006")

    # -- Status mappings --

    def test_status_mapping_in_use(self):
        """Verify 'In Use' maps to 'Active'."""
        self.adapter.load()
        device = self._get_device("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.status__name, "Active")

    def test_status_mapping_deployed(self):
        """Verify 'Deployed' maps to 'Active'."""
        self.adapter.load()
        device = self._get_device("LAPTOP-XYZ789.lt-tulsa-tech01.nrtc.coop")
        self.assertEqual(device.status__name, "Active")

    def test_status_mapping_in_store(self):
        """Verify 'In Store' maps to 'Inventory'."""
        self.adapter.load()
        device = self._get_device("HP-SPARE-01")
        self.assertEqual(device.status__name, "Inventory")

    def test_status_mapping_retired(self):
        """Verify 'Retired' maps to 'Decommissioning'."""
        self.adapter.load()
        device = self._get_device("OLD-SERVER-RETIRE.srv-old-retire.nrtc.coop")
        self.assertEqual(device.status__name, "Decommissioning")

    def test_status_mapping_maintenance(self):
        """Verify 'Maintenance' maps to 'Planned'."""
        self.adapter.load()
        device = self._get_device("MAINT-SWITCH.sw-okc-maint01.nrtc.coop")
        self.assertEqual(device.status__name, "Planned")

    def test_status_mapping_faulty(self):
        """Verify 'Faulty' maps to 'Failed'."""
        self.adapter.load()
        device = self._get_device("FAULTY-WS.ws-faulty01.nrtc.coop")
        self.assertEqual(device.status__name, "Failed")

    def test_default_status_when_state_missing(self):
        """Verify default 'Active' status when state is null."""
        self.adapter.load()
        device = self._get_device("SVCTAG006")
        self.assertEqual(device.status__name, "Active")

    # -- Manufacturer --

    def test_manufacturer_title_cased(self):
        """Verify manufacturer names are title-cased."""
        self.adapter.load()
        manufacturers = self.adapter.get_all("manufacturer")
        mfr_names = {m.name for m in manufacturers}
        self.assertIn("Dell", mfr_names)
        self.assertIn("Hp", mfr_names)
        self.assertIn("Lenovo", mfr_names)

    def test_manufacturer_deduplication(self):
        """Verify manufacturers are deduplicated."""
        self.adapter.load()
        manufacturers = self.adapter.get_all("manufacturer")
        mfr_names = [m.name for m in manufacturers]
        self.assertEqual(mfr_names.count("Dell"), 1)

    def test_generic_manufacturer_when_vendor_missing(self):
        """Verify 'Generic' manufacturer when vendor is null."""
        self.adapter.load()
        manufacturers = self.adapter.get_all("manufacturer")
        mfr_names = {m.name for m in manufacturers}
        self.assertIn("Generic", mfr_names)

    # -- Device type --

    def test_device_type_udf_preferred(self):
        """Verify UDF device type field is preferred over computer_system.model."""
        self.adapter.load()
        device = self._get_device("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.device_type__model, "OptiPlex 7090 SFF")

    def test_device_type_fallback_to_model(self):
        """Verify computer_system.model is used when UDF device type is missing."""
        self.adapter.load()
        device = self._get_device("MAINT-SWITCH.sw-okc-maint01.nrtc.coop")
        # No udf_sline_14122, model is null → "Generic Device"
        self.assertEqual(device.device_type__model, "Generic Device")

    def test_device_type_deduplication(self):
        """Verify device types are deduplicated."""
        self.adapter.load()
        device_types = self.adapter.get_all("device_type")
        dt_models = [dt.model for dt in device_types]
        self.assertEqual(dt_models.count("ThinkCentre M920"), 1)

    # -- Location --

    def test_location_from_dict(self):
        """Verify location extracted from dict format."""
        self.adapter.load()
        device = self._get_device("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.location__name, "Oklahoma City")

    def test_location_from_string(self):
        """Verify location extracted from plain string format."""
        self.adapter.load()
        device = self._get_device("HP-SPARE-01")
        self.assertEqual(device.location__name, "Norman Warehouse")

    def test_location_invalid_string_defaults(self):
        """Verify invalid location strings (like '-') fall back to default."""
        self.adapter.load()
        device = self._get_device("FAULTY-WS.ws-faulty01.nrtc.coop")
        self.assertEqual(device.location__name, "Default Location")

    def test_location_deduplication(self):
        """Verify locations are deduplicated."""
        self.adapter.load()
        locations = self.adapter.get_all("location")
        loc_names = [loc.name for loc in locations]
        self.assertEqual(loc_names.count("Oklahoma City"), 1)

    def test_location_mapping_huntsville_comma(self):
        """Verify 'Huntsville, AL' is normalized to 'HSV'."""
        fixture = [
            {"id": "9001", "name": "SRV-HSV", "location": "Huntsville, AL",
             "vendor": {"name": "DELL"}, "state": {"name": "In Use"},
             "computer_system": {"service_tag": "T1"}, "udf_fields": {}},
        ]
        self.client.get_workstations.return_value = fixture
        adapter = ServicedeskPlusRemoteAdapter(job=self.job, sync=None, client=self.client)
        adapter.load()
        device = [d for d in adapter.get_all("device")][0]
        self.assertEqual(device.location__name, "HSV")

    def test_location_mapping_huntsville_no_comma(self):
        """Verify 'Huntsville AL' is normalized to 'HSV'."""
        fixture = [
            {"id": "9002", "name": "SRV-HSV2", "location": {"name": "Huntsville AL"},
             "vendor": {"name": "DELL"}, "state": {"name": "In Use"},
             "computer_system": {"service_tag": "T2"}, "udf_fields": {}},
        ]
        self.client.get_workstations.return_value = fixture
        adapter = ServicedeskPlusRemoteAdapter(job=self.job, sync=None, client=self.client)
        adapter.load()
        device = [d for d in adapter.get_all("device")][0]
        self.assertEqual(device.location__name, "HSV")

    # -- Tenant --

    def test_tenant_from_site(self):
        """Verify tenant is mapped from ServiceDesk site."""
        self.adapter.load()
        device = self._get_device("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.tenant__name, "NRTC HQ")

    def test_tenant_none_when_site_missing(self):
        """Verify tenant is None when site is null."""
        self.adapter.load()
        device = self._get_device("SVCTAG006")
        self.assertIsNone(device.tenant__name)

    def test_tenant_inferred_from_hostname_when_common_site(self):
        """Verify tenant is inferred from hostname domain when site is 'Common Site'."""
        self.adapter.load()
        # Device 1011: site="Common Site", hostname="rad0.comporium.net" → "Comporium"
        device = self._get_device("rad0.rad0.comporium.net")
        self.assertEqual(device.tenant__name, "Comporium")

    def test_tenant_falls_back_to_common_site_when_no_hostname(self):
        """Verify 'Common Site' is kept when hostname is unavailable for inference."""
        self.adapter.load()
        # Device 1012: site="Common Site", no UDF hostname
        device = self._get_device("srv-common-nohostname")
        self.assertEqual(device.tenant__name, "Common Site")

    # -- Asset tag / comments / role --

    def test_asset_tag(self):
        """Verify asset_tag is populated."""
        self.adapter.load()
        device = self._get_device("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.asset_tag, "NRTC-0001")

    def test_null_asset_tag(self):
        """Verify null asset_tag is stored as None."""
        self.adapter.load()
        device = self._get_device("HP-SPARE-01")
        self.assertIsNone(device.asset_tag)

    def test_comments(self):
        """Verify description maps to comments."""
        self.adapter.load()
        device = self._get_device("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop")
        self.assertEqual(device.comments, "Main office workstation")

    def test_default_role(self):
        """Verify all devices get the default NUS role."""
        self.adapter.load()
        for device in self.adapter.get_all("device"):
            self.assertEqual(device.role__name, "NUS")

    # -- Power type --

    def test_power_type_from_udf_field(self):
        """Verify power type extracted from UDF power supply field."""
        self.adapter.load()
        device = self._get_device("SRV-DB-PROD.srv-db-prod01.nrtc.coop")
        self.assertEqual(device.power_type, "AC")

    def test_power_type_parsed_from_model(self):
        """Verify power type parsed from model string when UDF field is absent."""
        self.adapter.load()
        # Device 1005: model="PowerEdge R340 (DC)", no udf_pick_8415
        device = self._get_device("OLD-SERVER-RETIRE.srv-old-retire.nrtc.coop")
        self.assertEqual(device.power_type, "DC")

    def test_power_type_none_when_unavailable(self):
        """Verify power type is None when not in UDF or model string."""
        self.adapter.load()
        device = self._get_device("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop")
        self.assertIsNone(device.power_type)

    # -- iDRAC IP --

    def test_idrac_ip_from_udf(self):
        """Verify iDRAC IP extracted from UDF field."""
        self.adapter.load()
        device = self._get_device("SRV-DB-PROD.srv-db-prod01.nrtc.coop")
        self.assertEqual(device.idrac_ip, "96.46.118.19")

    def test_idrac_ip_none_when_missing(self):
        """Verify iDRAC IP is None when UDF field is absent."""
        self.adapter.load()
        device = self._get_device("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop")
        self.assertIsNone(device.idrac_ip)

    def test_idrac_op_id_from_udf(self):
        """Verify iDRAC OP ID extracted from UDF field."""
        self.adapter.load()
        device = self._get_device("SRV-DB-PROD.srv-db-prod01.nrtc.coop")
        self.assertEqual(device.idrac_op_id, "sk6jlxwneeop2calbzoxfextqe")

    def test_idrac_op_id_none_when_missing(self):
        """Verify iDRAC OP ID is None when UDF field is absent."""
        self.adapter.load()
        device = self._get_device("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop")
        self.assertIsNone(device.idrac_op_id)

    # -- Primary IP / Interface --

    def test_primary_ip_extracted(self):
        """Verify primary IP is stored in device_primary_ips mapping."""
        self.adapter.load()
        self.assertEqual(
            self.adapter.device_primary_ips.get("SRV-DB-PROD.srv-db-prod01.nrtc.coop"),
            "96.46.118.18",
        )

    def test_no_primary_ip_when_missing(self):
        """Verify devices without ip_addresses are not in device_primary_ips."""
        self.adapter.load()
        self.assertNotIn("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop", self.adapter.device_primary_ips)

    def test_interface_created_for_device_with_ip(self):
        """Verify em1_bond0 interface is created for devices that have an IP."""
        self.adapter.load()
        interfaces = self.adapter.get_all("interface")
        iface_device_names = {i.device__name for i in interfaces}
        self.assertIn("SRV-DB-PROD.srv-db-prod01.nrtc.coop", iface_device_names)

    def test_no_interface_for_device_without_ip(self):
        """Verify no interface is created for devices without an IP."""
        self.adapter.load()
        interfaces = self.adapter.get_all("interface")
        iface_device_names = {i.device__name for i in interfaces}
        self.assertNotIn("DESKTOP-ABC123.ws-okc-desk01.nrtc.coop", iface_device_names)

    def test_interface_name_is_em1_bond0(self):
        """Verify interface name is em1_bond0."""
        self.adapter.load()
        interfaces = self.adapter.get_all("interface")
        for iface in interfaces:
            self.assertEqual(iface.name, "em1_bond0")

    # -- Helper --

    def _get_device(self, name):
        """Helper to get a device by name from the adapter."""
        for device in self.adapter.get_all("device"):
            if device.name == name:
                return device
        self.fail(f"Device '{name}' not found. Available: {[d.name for d in self.adapter.get_all('device')]}")
