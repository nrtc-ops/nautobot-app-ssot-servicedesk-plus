"""Jobs for ServiceDesk Plus SSoT integration."""

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.jobs import BooleanVar, ObjectVar, register_jobs
from nautobot.dcim.models import Device, Location, LocationType
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import ExternalIntegration, Role, Status
from nautobot_ssot.jobs.base import DataSource

from nautobot_ssot_servicedesk_plus.diffsync.adapters import (
    ServicedeskPlusNautobotAdapter,
    ServicedeskPlusRemoteAdapter,
)
from nautobot_ssot_servicedesk_plus.utils.servicedesk_plus import (
    DEFAULT_LOCATION_TYPE,
    DEFAULT_ROLE,
    STATUS_MAPPINGS,
    ServiceDeskPlusClient,
)

name = "ServiceDesk Plus SSoT"  # pylint: disable=invalid-name


class ServicedeskPlusDataSource(DataSource):
    """ServiceDesk Plus SSoT Data Source."""

    integration = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        label="ServiceDesk Plus Instance",
        required=True,
    )

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

    def _ensure_prerequisites(self):
        """Ensure required Nautobot objects exist before sync.

        Creates LocationType, Role, and Status objects that the DiffSync models
        reference via FK lookups. These must exist before devices/locations can be created.
        """
        device_ct = ContentType.objects.get_for_model(Device)
        location_ct = ContentType.objects.get_for_model(Location)

        # LocationType "Site" — must allow devices to be assigned to it
        location_type, created = LocationType.objects.get_or_create(name=DEFAULT_LOCATION_TYPE)
        if created or device_ct not in location_type.content_types.all():
            location_type.content_types.add(device_ct)
            self.logger.info("Ensured LocationType '%s' exists with device content type", DEFAULT_LOCATION_TYPE)

        # Role "NUS"
        role, created = Role.objects.get_or_create(name=DEFAULT_ROLE)
        if created or device_ct not in role.content_types.all():
            role.content_types.add(device_ct)
            self.logger.info("Ensured Role '%s' exists with device content type", DEFAULT_ROLE)

        # Statuses used by our mappings
        required_statuses = set(STATUS_MAPPINGS.values())
        for status_name in required_statuses:
            status, created = Status.objects.get_or_create(name=status_name)
            if created:
                self.logger.info("Created Status '%s'", status_name)
            # Ensure status is applicable to both devices and locations
            for ct in (device_ct, location_ct):
                if ct not in status.content_types.all():
                    status.content_types.add(ct)

    def _get_servicedesk_client(self):
        """Build a ServiceDeskPlusClient from the selected ExternalIntegration.

        The ExternalIntegration should have:
        - remote_url: The ServiceDesk Plus base URL
        - secrets_group: A SecretsGroup containing an HTTP token secret
        - verify_ssl: Whether to verify SSL certificates
        """
        self.logger.info(
            "Building client for integration '%s' (url=%s, secrets_group=%s)",
            self.integration,
            self.integration.remote_url,
            self.integration.secrets_group,
        )
        if not self.integration.secrets_group:
            raise ValueError(
                f"ExternalIntegration '{self.integration}' has no Secrets Group assigned. "
                "Please configure a Secrets Group with an HTTP Token secret."
            )
        token = self.integration.secrets_group.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
        )
        return ServiceDeskPlusClient(
            url=self.integration.remote_url,
            token=token,
            verify_ssl=self.integration.verify_ssl,
        )

    def load_source_adapter(self):
        """Load data from ServiceDesk Plus into DiffSync models."""
        client = self._get_servicedesk_client()
        self.source_adapter = ServicedeskPlusRemoteAdapter(job=self, sync=self.sync, client=client)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = ServicedeskPlusNautobotAdapter(job=self, sync=self.sync)
        self.target_adapter.load()

    def run(self, dryrun, memory_profiling, debug, integration, *args, **kwargs):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        self.integration = integration
        self._ensure_prerequisites()
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [ServicedeskPlusDataSource]
register_jobs(*jobs)
