"""App declaration for nautobot_ssot_servicedesk_plus."""

# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

from nautobot.apps import NautobotAppConfig

__version__ = metadata.version(__name__)


class NautobotSsotServicedeskPlusConfig(NautobotAppConfig):
    """App configuration for the nautobot_ssot_servicedesk_plus app."""

    name = "nautobot_ssot_servicedesk_plus"
    verbose_name = "Nautobot SSOT ServiceDesk Plus"
    version = __version__
    author = "NRTC DSO"
    description = "Nautobot SSOT ServiceDesk Plus."
    base_url = "ssot-servicedesk-plus"
    required_settings = []
    default_settings = {}
    docs_view_name = "plugins:nautobot_ssot_servicedesk_plus:docs"
    searchable_models = []


config = NautobotSsotServicedeskPlusConfig  # pylint:disable=invalid-name
