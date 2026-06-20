# Changelog

## 0.2.0

- Add one-line install, upgrade, uninstall, and doctor workflows.
- Support curl-pipe installation by downloading the repository tarball when the
  script is not running from a local clone.
- Add timestamped backups for upgrade/reinstall by default.
- Add `uninstall --purge-backups` for explicit cleanup of upgrade backups.
- Add root and skill-level `VERSION` files.
- Add `Makefile` shortcuts and installer smoke tests in CI.

## 0.1.0

- Initial Codex skill package with paragraph reconstruction, full-paper context,
  figure/table extraction, MacDown-safe math rendering, and output validation.
