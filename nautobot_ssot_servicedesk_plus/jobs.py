"""Jobs for ServiceDesk Plus SSoT integration."""

from nautobot.apps.jobs import BooleanVar, register_jobs
from nautobot_ssot.jobs.base import DataSource, DataTarget

from nautobot_ssot_servicedesk_plus.diff import CustomOrderingDiff
from nautobot_ssot_servicedesk_plus.diffsync.adapters import (
    ServicedeskPlusNautobotAdapter,
    ServicedeskPlusRemoteAdapter,
)

name = "ServiceDesk Plus SSoT"  # pylint: disable=invalid-name


class ServicedeskPlusDataSource(DataSource):
    """ServiceDesk Plus SSoT Data Source."""

    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for ServiceDesk Plus."""

        name = "ServiceDesk Plus to Nautobot"
        data_source = "ServiceDesk Plus"
        data_target = "Nautobot"
        description = "Sync information from ServiceDesk Plus to Nautobot"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return ()

    def load_source_adapter(self):
        """Load data from ServiceDesk Plus into DiffSync models."""
        self.source_adapter = ServicedeskPlusRemoteAdapter(job=self, sync=self.sync)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = ServicedeskPlusNautobotAdapter(job=self, sync=self.sync)
        self.target_adapter.load()

    def run(self, dryrun, memory_profiling, debug, *args, **kwargs):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


class ServicedeskPlusDataTarget(DataTarget):
    """ServiceDesk Plus SSoT Data Target."""

    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for ServiceDesk Plus."""

        name = "Nautobot to ServiceDesk Plus"
        data_source = "Nautobot"
        data_target = "ServiceDesk Plus"
        description = "Sync information from Nautobot to ServiceDesk Plus"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataTarget."""
        return {}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return ()

    def load_source_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.source_adapter = ServicedeskPlusNautobotAdapter(job=self, sync=self.sync)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from ServiceDesk Plus into DiffSync models."""
        self.target_adapter = ServicedeskPlusRemoteAdapter(job=self, sync=self.sync)
        self.target_adapter.load()

    def run(self, dryrun, memory_profiling, debug, *args, **kwargs):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)

    def execute_sync(self):
        """Method to synchronize the difference from `self.diff`, from SOURCE to TARGET adapter.

        Overridden to use a CustomOrderingDiff diff_class.
        """
        if self.source_adapter is not None and self.target_adapter is not None:
            self.source_adapter.sync_to(self.target_adapter, flags=self.diffsync_flags, diff_class=CustomOrderingDiff)
        else:
            self.logger.warning("One of the adapters was not properly initialized prior to synchronization.")


jobs = [ServicedeskPlusDataSource, ServicedeskPlusDataTarget]
register_jobs(*jobs)
