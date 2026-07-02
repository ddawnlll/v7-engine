"""Data Lake — centralized dataset specs, catalog, storage paths,
passports, and data-health verification.

Provides :class:`DatasetSpec` (what data we need), :class:`DataCatalog`
(what data we have, with gap analysis), :class:`DataLakePaths`
(medallion-architecture path resolution), :class:`DataPassport`
(quality passport for a dataset at a point in time), and
:class:`DataHealthChecker` (verify coverage and auto-repair).

Domain-boundary compliant: imports only lib/ primitives and stdlib.
"""

from lib.data_lake.catalog import DataCatalog
from lib.data_lake.health import DataHealthChecker, HealthReport
from lib.data_lake.passport import DataPassport
from lib.data_lake.spec import DatasetSpec
from lib.data_lake.storage import DataLakePaths

__all__ = [
    "DataCatalog",
    "DataHealthChecker",
    "DataLakePaths",
    "DataPassport",
    "DatasetSpec",
    "HealthReport",
]

__version__ = "0.4.0"
