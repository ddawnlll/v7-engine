"""Data Lake — centralized dataset specs, catalog, storage paths, and passports.

Provides :class:`DatasetSpec` (what data we need), :class:`DataCatalog`
(what data we have, with gap analysis), :class:`DataLakePaths`
(medallion-architecture path resolution), and :class:`DataPassport`
(quality passport for a dataset at a point in time).

Domain-boundary compliant: imports only lib/ primitives and stdlib.
"""

from lib.data_lake.catalog import DataCatalog
from lib.data_lake.passport import DataPassport
from lib.data_lake.spec import DatasetSpec
from lib.data_lake.storage import DataLakePaths

__all__ = [
    "DataCatalog",
    "DataLakePaths",
    "DataPassport",
    "DatasetSpec",
]

__version__ = "0.3.0"
