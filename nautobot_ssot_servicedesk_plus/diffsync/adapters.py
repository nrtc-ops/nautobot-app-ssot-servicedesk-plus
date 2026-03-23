"""Diffsync adapters for nautobot_ssot_servicedesk_plus."""

from diffsync import Adapter
from nautobot_ssot.contrib import NautobotAdapter

from nautobot_ssot_servicedesk_plus.diffsync.models import DeviceSSoTModel


class ServicedeskPlusRemoteAdapter(Adapter):
    """DiffSync adapter for ServiceDesk Plus."""

    device = DeviceSSoTModel

    top_level = ["device"]

    def __init__(self, *args, job=None, sync=None, client=None, **kwargs):
        """Initialize ServiceDesk Plus.

        Args:
            *args (tuple): Variable length argument list.
            job (object, optional): ServiceDesk Plus job. Defaults to None.
            sync (object, optional): ServiceDesk Plus SSoT. Defaults to None.
            client (object): ServiceDesk Plus API client connection object.
            **kwargs (dict): Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self.job = job
        self.sync = sync
        self.conn = client

    def load(self):
        """Load data from ServiceDesk Plus into SSoT models."""
        raise NotImplementedError()


class ServicedeskPlusNautobotAdapter(NautobotAdapter):
    """DiffSync adapter for Nautobot."""

    device = DeviceSSoTModel

    top_level = ["device"]
