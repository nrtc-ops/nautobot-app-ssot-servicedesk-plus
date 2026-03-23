"""Test ServiceDesk Plus adapter."""

import json
import uuid
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from nautobot.extras.models import Job, JobResult
from nautobot.core.testing import TransactionTestCase
from nautobot_ssot_servicedesk_plus.diffsync.adapters import ServicedeskPlusRemoteAdapter
from nautobot_ssot_servicedesk_plus.jobs import ServicedeskPlusDataSource


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


DEVICE_FIXTURE = load_json("./nautobot_ssot_servicedesk_plus/tests/fixtures/get_devices.json")


class TestServicedeskPlusRemoteAdapterTestCase(TransactionTestCase):
    """Test ServicedeskPlusRemoteAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):  # pylint: disable=invalid-name
        """Initialize test case."""
        self.servicedesk_plus_client = MagicMock()
        self.servicedesk_plus_client.get_devices.return_value = DEVICE_FIXTURE

        self.job = ServicedeskPlusDataSource()
        self.job.job_result = JobResult.objects.create(name=self.job.class_path)
        self.servicedesk_plus = ServicedeskPlusRemoteAdapter(job=self.job, sync=None, client=self.servicedesk_plus_client)

    def test_data_loading(self):
        """Test Nautobot SSOT ServiceDesk Plus load() function."""
        # self.servicedesk_plus.load()
        # self.assertEqual(
        #     {dev["name"] for dev in DEVICE_FIXTURE},
        #     {dev.get_unique_id() for dev in self.servicedesk_plus.get_all("device")},
        # )
