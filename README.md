# Nautobot SSOT ServiceDesk Plus SSoT

An app for [Nautobot](https://github.com/nautobot/nautobot).

> **⚠️ Alpha Software**: This project is currently in **alpha** and is under active development. APIs, configuration options, and behavior may change between releases. Use in production environments is not recommended until a stable release is published.

The term SSoT, or Single Source of Truth, refers to the intention of using Nautobot to consolidate data from disparate Systems of Record to create a single resource for all automation needs. This is done by extending the [Nautobot SSoT framework](https://github.com/nautobot/nautobot-app-ssot) which uses the DiffSync library. This app is built with the capability in mind to import and export data from your desired System of Record.

<p align="center">
  <img src="https://raw.githubusercontent.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/develop/docs/images/icon-nautobot-ssot-servicedesk-plus.png" class="logo" height="200px">
  <br>
  <a href="https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/actions"><img src="https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <a href="https://docs.nrtc.cloud/projects/nautobot-ssot-servicedesk-plus/en/latest/"><img src="https://readthedocs.org/projects/nautobot-app-ssot-servicedesk-plus/badge/"></a>
  <a href="https://pypi.org/project/nautobot-ssot-servicedesk-plus/"><img src="https://img.shields.io/pypi/v/nautobot-ssot-servicedesk-plus"></a>
  <a href="https://pypi.org/project/nautobot-ssot-servicedesk-plus/"><img src="https://img.shields.io/pypi/dm/nautobot-ssot-servicedesk-plus"></a>
  <br>
  An <a href="https://networktocode.com/nautobot-apps/">App</a> for <a href="https://nautobot.com/">Nautobot</a>.
</p>

## Overview

Pulls "Servers" from ServiceDesk Plus, and puts them into a particular Nautobot Role with some particular field mappings. If you would like to use this app outside of our org, you would need to fork, and change those mappings for now. I have some todos to extract this out into app config.

### Screenshots

> Developer Note: Add any representative screenshots of the App in action. These images should also be added to the `docs/user/app_use_cases.md` section.

> Developer Note: Place the files in the `docs/images/` folder and link them using only full URLs from GitHub, for example: `![Overview](https://raw.githubusercontent.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/develop/docs/images/app-overview.png)`. This absolute static linking is required to ensure the README renders properly in GitHub, the docs site, and any other external sites like PyPI.

More screenshots can be found in the [Using the App](https://docs.nrtc.cloud/projects/nautobot-ssot-servicedesk-plus/en/latest/user/app_use_cases/) page in the documentation. Here's a quick overview of some of the app's added functionality:

![](https://raw.githubusercontent.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/develop/docs/images/placeholder.png)

## Try it out!

> Developer Note: Only keep this section if appropriate. Update link to correct sandbox.

> For a full list of all the available always-on sandbox environments, head over to the main page on [networktocode.com](https://www.networktocode.com/nautobot/sandbox-environments/).

## Documentation

Full documentation for this App can be found over on the [Nautobot Docs](https://docs.nrtc.cloud) website:

- [User Guide](https://docs.nrtc.cloud/projects/nautobot-ssot-servicedesk-plus/en/latest/user/app_overview/) - Overview, Using the App, Getting Started.
- [Administrator Guide](https://docs.nrtc.cloud/projects/nautobot-ssot-servicedesk-plus/en/latest/admin/install/) - How to Install, Configure, Upgrade, or Uninstall the App.
- [Developer Guide](https://docs.nrtc.cloud/projects/nautobot-ssot-servicedesk-plus/en/latest/dev/contributing/) - Extending the App, Code Reference, Contribution Guide.
- [Release Notes / Changelog](https://docs.nrtc.cloud/projects/nautobot-ssot-servicedesk-plus/en/latest/admin/release_notes/).
- [Frequently Asked Questions](https://docs.nrtc.cloud/projects/nautobot-ssot-servicedesk-plus/en/latest/user/faq/).

### Contributing to the Documentation

You can find all the Markdown source for the App documentation under the [`docs`](https://github.com/nrtc-ops/nautobot-app-ssot-servicedesk-plus/tree/develop/docs) folder in this repository. For simple edits, a Markdown capable editor is sufficient: clone the repository and edit away.

If you need to view the fully-generated documentation site, you can build it with [MkDocs](https://www.mkdocs.org/). A container hosting the documentation can be started using the `invoke` commands (details in the [Development Environment Guide](https://docs.nrtc.cloud/projects/nautobot-ssot-servicedesk-plus/en/latest/dev/dev_environment/#docker-development-environment)) on [http://localhost:8001](http://localhost:8001). Using this container, as your changes to the documentation are saved, they will be automatically rebuilt and any pages currently being viewed will be reloaded in your browser.

Any PRs with fixes or improvements are very welcome!

## Questions

For any questions or comments, please check the [FAQ](https://docs.nrtc.cloud/projects/nautobot-ssot-servicedesk-plus/en/latest/user/faq/) first.
