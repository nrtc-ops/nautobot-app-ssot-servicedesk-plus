# v0.1 Release Notes

This document describes all new features and changes in the release. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Overview

- Major features or milestones
- Changes to compatibility with Nautobot and/or other apps, libraries etc.

<!-- towncrier release notes start -->

## [v0.1.0 (2026-03-30)](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/releases/tag/v0.1.0)

### Fixed

- [#1](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/issues/1) - Fixed pylint violations (R0914, R0915, R0903, R0904, R1721) by refactoring `load()` into helper methods and suppressing framework-driven false positives.
- [#2](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/issues/2) - Syntax error with boolean usage on verify ssl.
