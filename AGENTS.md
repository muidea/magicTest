# AGENTS.md - MagicTest Codebase Guide

## Project Overview
MagicTest is a Python3 test suite project using pytest/unittest. Modules include: session, cas, mock, file, platform, vmi.

## Environment Setup

```bash
source ~/codespace/venv/bin/activate
cd vmi
pip install -r requirements.txt
pip install black isort flake8 mypy  # Dev dependencies
```

## Build/Lint/Test Commands

### Running Tests

```bash
cd vmi

# Run tests by category
python3 run_tests.py --all           # All tests (requires server)
python3 run_tests.py --quick         # Quick validation (offline)
python3 run_tests.py --validation    # Framework validation (offline)
python3 run_tests.py --module        # Module tests (requires server)
python3 run_tests.py --concurrent    # Concurrent tests (requires server)
python3 run_tests.py --scenario      # Scenario tests (requires server)
python3 run_tests.py --aging 60      # Aging test for 60 minutes

# Using pytest
pytest -v                            # All tests verbose
pytest -k "test_name"                # Filter by name
pytest -x                            # Stop on first failure
pytest --cov=. --cov-report=html     # With coverage

# Run a single test (IMPORTANT)
pytest store/store_test.py::StoreTestCase::test_create_store -v
python3 -m unittest store.store_test.StoreTestCase.test_create_store -v
```

### Lint/Type Check

```bash
cd vmi
black . && isort .
flake8 . --max-line-length=120
mypy . --ignore-missing-imports
```

## Code Style Guidelines

### Python Path Setup (CRITICAL)

All test files in subdirectories (store/, credit/, order/, etc.) MUST include this path setup:

```python
import os
import sys

file_dir = os.path.dirname(os.path.abspath(__file__))
project_root = file_dir
while project_root and not os.path.exists(os.path.join(project_root, 'session', 'session.py')):
    parent = os.path.dirname(project_root)
    if parent == project_root:
        break
    project_root = parent

if not os.path.exists(os.path.join(project_root, 'session', 'session.py')):
    if os.path.basename(file_dir) in ['credit', 'order', 'partner', 'product', 'status', 'store', 'warehouse']:
        project_root = os.path.dirname(os.path.dirname(file_dir))
    else:
        project_root = os.path.dirname(file_dir)

for path in ['session', 'cas', 'mock', 'vmi']:
    _path = os.path.join(project_root, path)
    if _path not in sys.path:
        sys.path.insert(0, _path)
```

### Import Order
1. Standard library (alphabetically)
2. Third-party libraries
3. Local modules (session, cas, mock, sdk)

```python
import logging
import os
import sys
import unittest
from typing import Any, Dict, List, Optional

from session import MagicSession
from cas.cas import Cas
from mock import common as mock
from sdk import StoreSDK, PartnerSDK
```

### Naming Conventions
- **Classes**: `PascalCase` (StoreTestCase, SessionManager)
- **Functions/Methods**: `snake_case` (run_concurrent_test, create_session)
- **Variables**: `snake_case` (max_workers, server_url)
- **Constants**: `UPPER_SNAKE_CASE` (MAX_RETRY_COUNT, DEFAULT_TIMEOUT)
- **Private members**: `_leading_underscore` (_init_session, _cleanup)
- **Test methods**: `test_<action>_<entity>` (test_create_store, test_query_partner)

### Type Annotations

```python
def filter(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
def create(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
```

### Error Handling
- SDK methods return `None` on failure, not exceptions
- Use `Optional` return types for methods that may fail
- Log errors before returning None

```python
def query(self, entity_id: int) -> Optional[Dict[str, Any]]:
    try:
        result = self.entity.query(entity_id)
        return result
    except Exception as e:
        logger.error(f"Query failed for {entity_id}: {e}")
        return None
```

## Project Structure

```
magicTest/
├── session/           # MagicSession HTTP client
├── cas/               # Authentication module
├── mock/              # Mock utilities
├── vmi/               # Main test module
│   ├── run_tests.py   # Unified test runner
│   ├── test_config.json
│   ├── conftest.py    # pytest fixtures
│   ├── session_manager.py
│   ├── sdk/           # SDK modules
│   ├── store/         # Store tests
│   ├── credit/        # Credit tests
│   ├── order/         # Order tests
│   ├── product/       # Product tests
│   ├── partner/       # Partner tests
│   └── warehouse/     # Warehouse tests
└── AGENTS.md
```

## Test Class Hierarchy

```
unittest.TestCase
└── TestBaseWithSessionManager  # Session management, SDK init
    └── TestBaseMultiTenant     # Multi-tenant support

VMITestCase (test_vmi_base.py)
├── StoreTestCase
├── ProductTestCase
├── WarehouseTestCase
├── CreditTestCase
├── OrderTestCase
└── PartnerTestCase
```

## Configuration

All runtime config in `vmi/test_config.json`:

```json
{
  "server": {"url": "...", "namespace": "..."},
  "credentials": {"username": "...", "password": "..."},
  "session": {"refresh_interval": 540, "timeout": 1800}
}
```

## Important Notes

- **Always** run tests in virtual environment
- Session auto-refresh: every 9 minutes (to avoid 10-minute timeout)
- Never hardcode credentials - use `test_config.json`
- Test files in subdirectories need Python path setup code
- Import from session/cas/mock requires project root in sys.path
