# v0.3 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Major features or milestones
- Changes to compatibility with Nautobot and/or other apps, libraries etc.

<!-- towncrier release notes start -->

## [v0.3.3 (2026-07-14)](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/releases/tag/v0.3.3)

### Fixed

- [#27](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/issues/27) - The Nautobot device queryset now screens the `servicedesk_plus_id` value in Python so absent, JSON-null, and empty-string values are all excluded. The prior DB-side `__isnull=False` filter still loaded Hivelocity/AWS-imported devices whose custom-field key is present with an explicit JSON `null` (Django treats that as non-null), which crashed the sync with `ObjectAlreadyExists` on a `None` identifier. Only the devices with a real ServiceDesk Plus id are loaded now.

## [v0.3.2 (2026-07-14)](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/releases/tag/v0.3.2)

### Fixed

- [#24](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/issues/24) - The Nautobot device queryset now excludes devices whose `servicedesk_plus_id` custom field is an empty string (not just null). Unrelated devices — e.g. XCP/AWS imports — carry the field blank; loading several of them gave every one an empty identifier and crashed the sync with `ObjectAlreadyExists` before any comparison ran.

## [v0.3.1 (2026-07-14)](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/releases/tag/v0.3.1)

### Fixed

- [#21](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/issues/21) - Devices are now identified by their ServiceDesk Plus record id (custom field `servicedesk_plus_id`) instead of by name. The Nautobot adapter loads devices carrying that id, so an existing device is matched and UPDATED rather than re-created — which previously failed on Nautobot's globally-unique `asset_tag` and per-location-tenant unique `name`.

## [v0.3.1a1 (2026-07-14)](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/releases/tag/v0.3.1a1)

No significant changes.

## [v0.3.0 (2026-07-13)](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/releases/tag/v0.3.0)

### Added

- [#17](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/issues/17) - ServiceDesk-imported Sites are now placed under their US state Region (parsed from the site name and created on demand under the correct Census Super Region), with an "Unassigned" holding-pen Region as a fallback. The parent is set only on create, so a later reconciliation that re-groups a Site is not reverted on subsequent syncs.
