# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Nautobot SSoT app that synchronizes asset data (devices, locations, tenants, manufacturers, device types) between **ServiceDesk Plus** and **Nautobot** using the DiffSync framework. Supports bidirectional sync via DataSource (SDP → Nautobot) and DataTarget (Nautobot → SDP) jobs.

## Development Environment

Docker-based development using Invoke tasks. Requires Poetry for dependency management.

```bash
# Build and start containers
invoke build
invoke start          # detached mode
invoke debug          # foreground with logs

# Stop/restart
invoke stop
invoke restart
invoke destroy        # tear down everything (--volumes to remove data)

# Useful container commands
invoke cli            # bash shell in nautobot container
invoke nbshell        # nautobot shell
invoke shell_plus     # django shell_plus
invoke migrate        # run migrations
invoke createsuperuser
```

## Common Commands

```bash
# Linting & Formatting
invoke ruff --action lint --action format
invoke pylint
invoke autoformat     # (alias: invoke a)
invoke yamllint

# Tests
invoke unittest
invoke unittest --failfast
invoke unittest --coverage
invoke unittest_coverage   # coverage summary report

# Docs
invoke docs           # serve docs locally
```

All invoke tasks run inside Docker containers. Copy `invoke.example.yml` to `invoke.yml` for local config.

## Architecture

### DiffSync Pattern

The app follows the nautobot-ssot DiffSync pattern:

1. **Models** (`diffsync/models.py`) — Five `NautobotModel` subclasses defining sync identifiers and attributes:
    - `ManufacturerSSoTModel`, `DeviceTypeSSoTModel`, `LocationSSoTModel`, `TenantSSoTModel`, `DeviceSSoTModel`

2. **Adapters** (`diffsync/adapters.py`) — Two adapters that load data into DiffSync model instances:
    - `ServicedeskPlusRemoteAdapter` — fetches from ServiceDesk Plus API via `ServiceDeskPlusClient`
    - `ServicedeskPlusNautobotAdapter` — loads from Nautobot database (extends `NautobotAdapter`)

3. **Jobs** (`jobs.py`) — `ServicedeskPlusDataSource` and `ServicedeskPlusDataTarget` orchestrate the sync. Both accept an `ExternalIntegration` object that provides API URL, token, and SSL settings.

4. **Custom Diff** (`diff.py`) — `CustomOrderingDiff` defers DELETE operations to run last, with location deletions sorted deepest-first to respect hierarchy.

### API Client

`utils/servicedesk_plus.py` contains `ServiceDeskPlusClient` with paginated workstation fetching and constants for status mappings, default role ("NUS"), default status ("Active"), and default location type ("Site").

### Data Flow

- **DataSource:** ServiceDesk Plus API → RemoteAdapter → DiffSync diff → NautobotAdapter → Nautobot DB
- **DataTarget:** Nautobot DB → NautobotAdapter → DiffSync diff (with CustomOrderingDiff) → RemoteAdapter → ServiceDesk Plus API

## Code Style

- **Line length:** 120 characters
- **Linter:** Ruff (pydocstyle/Google convention, flake8, bandit, isort) + Pylint with nautobot plugin
- **Docstrings:** Google convention; not required in tests or private methods
- **Python:** >=3.10, <3.14
- **Nautobot:** >=3.0.0, nautobot-ssot >=4.0.0

## Release Notes

Uses Towncrier. Add changelog fragments to `changes/{type}/{issue_number}.md` where type is one of: breaking, security, added, changed, deprecated, removed, fixed, dependencies, documentation, housekeeping.
