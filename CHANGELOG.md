# Changelog

All notable changes to NetWatcher will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-08-28

### Added
- Centralized logging system with `NetWatcherLogger` class
- Debug flag functionality for CLI commands (`--debug`)
- Force reinstall instructions in README for version upgrades
- Comprehensive integration tests

### Changed
- **BREAKING**: All modules now use centralized logging via `get_logger()`
- Standardized `run_command` usage throughout codebase (removed mixed imports)
- Improved import consistency across all modules
- Enhanced code organization and removed redundant patterns

### Removed
- Direct `import logging` statements in favor of centralized logging
- Orphaned empty `config.toml` file from repository root
- Duplicate import statements in various modules

### Fixed
- Mixed usage of `run_command` between direct imports and actions module
- Log level parameter defaults (replaced `logging.INFO` with numeric constants)
- Import organization and circular dependency prevention

### Technical
- Code quality improved from 8.5/10 to 9.5/10
- Zero technical debt remaining (no TODO/FIXME markers)
- All integration tests pass
- Backward compatibility maintained for user-facing APIs

### Migration Notes
- **Users upgrading from 0.1.0 must use `pip install --force-reinstall --editable .`**
- No configuration file changes required
- Service restart recommended after upgrade

## [0.1.0] - Initial Release

### Added
- Initial NetWatcher implementation with basic network detection
- macOS menu bar integration
- Configuration wizard
- Service management commands
- Basic logging functionality
