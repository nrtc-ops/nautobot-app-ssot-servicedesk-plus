"""Jobs for ServiceDesk Plus SSoT integration."""

import ipaddress

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from nautobot.apps.jobs import BooleanVar, ObjectVar, register_jobs
from nautobot.dcim.models import Device, Interface, Location, LocationType
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import ExternalIntegration, Role, Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix
from nautobot_ssot.jobs.base import DataSource

from nautobot_ssot_servicedesk_plus.diffsync.adapters import (
    INTERFACE_NAME,
    ServicedeskPlusNautobotAdapter,
    ServicedeskPlusRemoteAdapter,
)
from nautobot_ssot_servicedesk_plus.utils.geo import (
    COUNTRY,
    UNASSIGNED_REGION,
    UNASSIGNED_SUPER_REGION,
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

    def _ensure_location_taxonomy(self, device_ct, location_ct):
        """Ensure the geographic LocationType chain and fallback holding pen exist.

        Country -> Super Region -> Region -> Site. A Site requires a Region parent
        (see LocationSSoTModel.create), so the wired type chain plus a
        US -> Uncategorized -> Unassigned holding pen must exist before sync.
        """
        lt_country, _ = LocationType.objects.get_or_create(name="Country")
        lt_super, _ = LocationType.objects.get_or_create(name="Super Region", defaults={"parent": lt_country})
        lt_region, _ = LocationType.objects.get_or_create(
            name="Region", defaults={"parent": lt_super, "nestable": True}
        )
        lt_site, _ = LocationType.objects.get_or_create(name=DEFAULT_LOCATION_TYPE, defaults={"parent": lt_region})
        for lt in (lt_region, lt_site):
            if device_ct not in lt.content_types.all():
                lt.content_types.add(device_ct)
        self.logger.info("Ensured LocationType chain Country->Super Region->Region->%s", DEFAULT_LOCATION_TYPE)

        # Fallback holding pen for un-classifiable sites: US -> Uncategorized -> Unassigned.
        active_status, _ = Status.objects.get_or_create(name="Active")
        if location_ct not in active_status.content_types.all():
            active_status.content_types.add(location_ct)
        us_loc, _ = Location.objects.get_or_create(
            name=COUNTRY, location_type=lt_country, defaults={"status": active_status}
        )
        unc_loc, _ = Location.objects.get_or_create(
            name=UNASSIGNED_SUPER_REGION, location_type=lt_super, defaults={"parent": us_loc, "status": active_status}
        )
        Location.objects.get_or_create(
            name=UNASSIGNED_REGION, location_type=lt_region, defaults={"parent": unc_loc, "status": active_status}
        )

    def _ensure_prerequisites(self):
        """Ensure required Nautobot objects exist before sync.

        Creates LocationType, Role, and Status objects that the DiffSync models
        reference via FK lookups. These must exist before devices/locations can be created.
        """
        device_ct = ContentType.objects.get_for_model(Device)
        location_ct = ContentType.objects.get_for_model(Location)

        self._ensure_location_taxonomy(device_ct, location_ct)

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
            # Ensure status is applicable to devices, locations, interfaces, prefixes, and IPs
            for ct in (device_ct, location_ct):
                if ct not in status.content_types.all():
                    status.content_types.add(ct)

        # Ensure Active status applies to interfaces, IP addresses, and prefixes
        active_status = Status.objects.get(name="Active")
        for model_class in (Interface, IPAddress, Prefix):
            ct = ContentType.objects.get_for_model(model_class)
            if ct not in active_status.content_types.all():
                active_status.content_types.add(ct)

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

    def _get_or_create_prefix(self, ip_str, namespace, active_status):
        """Find the most specific existing prefix containing an IP, or create a /32.

        Strategy (matching hivelocity_sync pattern):
        1. Find all prefixes in namespace that contain the IP
        2. Use the most specific (longest prefix_length)
        3. If none exist, create a /32 (fallback /30)
        """
        # Check for existing containing prefixes
        containing = Prefix.objects.filter(namespace=namespace).net_contains(ip_str)
        if containing.exists():
            most_specific = containing.order_by("-prefix_length").first()
            return most_specific, most_specific.prefix_length

        # No containing prefix — create /32, fallback /30
        for try_mask in (32, 30):
            network = ipaddress.ip_network(f"{ip_str}/{try_mask}", strict=False)
            prefix, created = Prefix.objects.get_or_create(
                network=str(network.network_address),
                prefix_length=try_mask,
                namespace=namespace,
                defaults={"status": active_status},
            )
            if created:
                self.logger.info("Created prefix %s/%s", network.network_address, try_mask)
            return prefix, try_mask

        return None, 32  # pragma: no cover

    def _assign_ip_addresses(self):
        """Post-sync: create Prefixes, IPAddresses, and assign to device interfaces.

        For each device with an IP from SDP:
        1. Find or create a containing Prefix
        2. Find or create the IPAddress
        3. Associate IP to the em1_bond0 interface via IPAddressToInterface
        4. Set as the device's primary_ip4
        """
        device_ips = self.source_adapter.device_primary_ips
        if not device_ips:
            return

        namespace = Namespace.objects.get(name="Global")
        active_status = Status.objects.get(name="Active")

        self.logger.info("Assigning IP addresses to %d devices", len(device_ips))

        for device_name, ip_str in device_ips.items():
            try:
                ipaddress.ip_address(ip_str)
            except ValueError:
                self.logger.warning("Invalid IP '%s' for device '%s', skipping", ip_str, device_name)
                continue

            try:
                device = Device.objects.get(name=device_name)
            except Device.DoesNotExist:
                self.logger.warning("Device '%s' not found in Nautobot, skipping IP assignment", device_name)
                continue

            try:
                interface = Interface.objects.get(name=INTERFACE_NAME, device=device)
            except Interface.DoesNotExist:
                self.logger.warning("Interface '%s' not found on device '%s'", INTERFACE_NAME, device_name)
                continue

            # Find or create containing prefix
            prefix, mask_length = self._get_or_create_prefix(ip_str, namespace, active_status)
            if not prefix:
                self.logger.warning("Could not create prefix for %s, skipping", ip_str)
                continue

            # Find or create IP address
            ip_address, created = IPAddress.objects.get_or_create(
                host=ip_str,
                mask_length=mask_length,
                parent=prefix,
                defaults={"status": active_status},
            )
            if created:
                self.logger.info("Created IP %s/%s for '%s'", ip_str, mask_length, device_name)

            # Associate IP to interface via IPAddressToInterface
            IPAddressToInterface.objects.get_or_create(
                ip_address=ip_address,
                interface=interface,
            )

            # Set as primary IP on device
            if device.primary_ip4 != ip_address:
                device.primary_ip4 = ip_address
                device.validated_save()
                self.logger.info("Set primary_ip4=%s on '%s'", ip_str, device_name)

    def load_source_adapter(self):
        """Load data from ServiceDesk Plus into DiffSync models."""
        client = self._get_servicedesk_client()
        self.source_adapter = ServicedeskPlusRemoteAdapter(job=self, sync=self.sync, client=client)
        self.source_adapter.load()

    def _reconcile_one_asset_tag(self, src, dry_run):
        """Resolve one source device's asset_tag against any existing Nautobot holder.

        SDP is the source of truth and servicedesk_plus_id is the identity, so a colliding
        asset_tag is resolved in SDP's favour rather than being allowed to abort the sync:
        adopt the same physical box (matched by serial), delete a stale unclaimed NUS record,
        or drop the tag from this source record when another SDP device / a non-NUS device
        legitimately holds it. Never modifies non-NUS devices.
        """
        tag, src_id = src.asset_tag, src.servicedesk_plus_id
        holder = Device.objects.filter(asset_tag=tag).first()
        if holder is None or (holder.cf or {}).get("servicedesk_plus_id") == src_id:
            return
        holder_sdp_id = (holder.cf or {}).get("servicedesk_plus_id")
        holder_role = holder.role.name if holder.role else None
        prefix = "[dry-run] would " if dry_run else ""

        if holder_role != DEFAULT_ROLE:
            self.logger.warning(
                "asset_tag %s held by non-NUS device %s; dropping it from SDP id %s", tag, holder.name, src_id
            )
            src.asset_tag = None
        elif holder_sdp_id:
            self.logger.warning(
                "asset_tag %s already owned by SDP id %s (%s); dropping it from SDP id %s",
                tag,
                holder_sdp_id,
                holder.name,
                src_id,
            )
            src.asset_tag = None
        elif holder.serial and holder.serial == src.serial:
            self.logger.info("%sadopt %s (serial %s) as SDP id %s", prefix, holder.name, holder.serial, src_id)
            if not dry_run:
                try:
                    holder.cf["servicedesk_plus_id"] = src_id
                    holder.validated_save()
                except ValidationError as exc:
                    self.logger.warning(
                        "Adopt failed for %s (%s); dropping asset_tag from SDP id %s", holder.name, exc, src_id
                    )
                    src.asset_tag = None
        else:
            self.logger.warning(
                "%sdelete stale NUS device %s (asset_tag %s) superseded by SDP id %s", prefix, holder.name, tag, src_id
            )
            if not dry_run:
                try:
                    holder.delete()
                except ProtectedError as exc:
                    self.logger.warning(
                        "Delete failed for %s (%s); dropping asset_tag from SDP id %s", holder.name, exc, src_id
                    )
                    src.asset_tag = None

    def _reconcile_asset_tags(self, dry_run):
        """Pre-sync: resolve every source device's asset_tag so a collision never aborts the run."""
        for src in self.source_adapter.get_all("device"):
            if src.asset_tag and src.servicedesk_plus_id:
                self._reconcile_one_asset_tag(src, dry_run)

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = ServicedeskPlusNautobotAdapter(job=self, sync=self.sync)
        self.target_adapter.get_or_create_metadatatype()
        self._reconcile_asset_tags(self.dryrun)
        self.target_adapter.load()

    def run(self, dryrun, memory_profiling, debug, integration, *args, **kwargs):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        self.integration = integration
        self._ensure_prerequisites()
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)
        if not self.dryrun:
            self._assign_ip_addresses()


jobs = [ServicedeskPlusDataSource]
register_jobs(*jobs)
