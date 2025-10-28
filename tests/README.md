# NetWatcher Tests

Automated test suite for NetWatcher using pytest.

## Quick Start

### Install Test Dependencies

```bash
pip install -e ".[test]"
```

This installs:
- `pytest` - Test framework
- `pytest-mock` - Enhanced mocking support
- `pytest-cov` - Code coverage reporting

### Run All Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=src --cov-report=html
```

### Run Specific Tests

```bash
# Run only unit tests
pytest -m unit

# Run specific test file
pytest tests/test_proxy_detection.py

# Run specific test function
pytest tests/test_proxy_detection.py::TestGetUrllibProxyHandler::test_pac_proxy_handler_no_double_http

# Run tests matching a pattern
pytest -k "proxy"
```

## Test Structure

```
tests/
├── conftest.py                    # Shared fixtures and configuration
├── test_proxy_detection.py        # Proxy detection tests (CRITICAL)
├── test_ipinfo.py                 # IP/location API tests
├── test_shell_proxy.py            # Shell proxy configuration tests
└── test_config.py                 # Configuration loading tests
```

## Test Categories

Tests are marked with categories:

- `@pytest.mark.unit` - Fast, isolated unit tests (default)
- `@pytest.mark.integration` - Integration tests requiring system resources
- `@pytest.mark.slow` - Tests that take significant time
- `@pytest.mark.network` - Tests requiring network access

Run specific categories:
```bash
pytest -m unit        # Only unit tests
pytest -m "not slow"  # Skip slow tests
```

## Critical Tests

### Bug Prevention Tests

These tests specifically prevent regressions of bugs we've fixed:

1. **`test_pac_proxy_handler_no_double_http`** (test_proxy_detection.py)
   - Prevents: Double "http://" prefix in PAC proxy URLs
   - Bug: pac_parser returns "http://proxy:8080" but code was adding "http://" again

2. **`test_user_configured_pac_url_is_used`** (test_shell_proxy.py)
   - Prevents: Ignoring user-configured PAC URLs from config.toml
   - Bug: shell_proxy was querying system proxy instead of using provided URL

3. **`test_config_uses_stdlib_logging`** (test_config.py)
   - Prevents: Premature logging initialization
   - Bug: config.py was using custom logger before debug flag was read

## Coverage

View coverage report after running tests with `--cov`:

```bash
# Generate HTML coverage report
pytest --cov=src --cov-report=html

# Open in browser (macOS)
open htmlcov/index.html
```

Target coverage: 80%+ for critical modules:
- `src/network/proxy_detection.py`
- `src/external/ipinfo.py`
- `src/network/shell_proxy.py`
- `src/config.py`

## Writing New Tests

### Test File Template

```python
"""
Unit tests for src/path/to/module.py

Brief description of what this module does.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestYourClass:
    """Tests for YourClass."""

    def test_something(self):
        """Test description."""
        from src.path.to.module import your_function

        result = your_function()

        assert result is not None
```

### Using Fixtures

Fixtures are defined in `conftest.py`:

```python
def test_with_fixtures(mock_config, temp_config_dir):
    """Example using shared fixtures."""
    assert "locations" in mock_config
    assert temp_config_dir.exists()
```

### Mocking

```python
from unittest.mock import patch, MagicMock

def test_with_mocking():
    """Example of mocking external dependencies."""
    with patch('src.module.external_function') as mock_func:
        mock_func.return_value = "mocked result"

        # Your test code
        result = function_that_calls_external()

        assert result == "mocked result"
        mock_func.assert_called_once()
```

## Continuous Integration

Tests run automatically on:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`
- Manual workflow dispatch

See `.github/workflows/tests.yml` for CI configuration.

## Troubleshooting

### Import Errors

If you see import errors, ensure you've installed the package in editable mode:

```bash
pip install -e ".[test]"
```

### macOS-Specific Issues

Some tests may require macOS-specific frameworks (PyObjC). These are:
- Automatically available when using system Python (`/usr/bin/python3`)
- Installed via pip when using virtual environments

### Skipping Tests

Skip tests that require specific conditions:

```python
@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_macos_specific():
    pass
```

## Best Practices

1. **Keep tests fast** - Mock external dependencies
2. **Test one thing** - Each test should verify one behavior
3. **Use descriptive names** - Test names should explain what they verify
4. **Test edge cases** - Include error conditions and boundary cases
5. **Avoid test interdependence** - Tests should run independently
6. **Use fixtures** - Share setup code via fixtures in conftest.py

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-mock documentation](https://pytest-mock.readthedocs.io/)
- [Python unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
