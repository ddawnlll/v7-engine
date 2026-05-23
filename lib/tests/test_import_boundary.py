"""
Test suite for lib/ — validates import boundary: lib/ must NOT import v7.* or alphaforge.*
"""

import sys
import pytest


def _get_all_lib_module_names() -> list[str]:
    """Discover all lib submodules by importing lib and walking subpackages."""
    import lib  # noqa: F401 — ensure lib is importable
    import pkgutil
    import lib as lib_root

    def walk(pkg, prefix: str) -> list[str]:
        modules = []
        for _importer, modname, is_pkg in pkgutil.walk_packages(
            pkg.__path__, prefix=prefix,
        ):
            if is_pkg:
                modules.append(modname)
                try:
                    __import__(modname)
                    sub = sys.modules[modname]
                    modules.extend(walk(sub, f"{modname}."))
                except ImportError:
                    pass
            else:
                modules.append(modname)
        return modules

    return walk(lib_root, "lib.")


def test_lib_does_not_import_v7_or_alphaforge():
    """HARD STOP: lib_import_boundary_violation.

    Every module in lib/ is loaded and checked. If any imported symbol
    originates from v7 or alphaforge, the test fails.
    """
    import lib  # noqa: F401

    module_names = _get_all_lib_module_names()
    tested = 0
    for name in module_names:
        try:
            mod = __import__(name)
        except ImportError as e:
            print(f"  skipping {name}: {e}")
            continue

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            mod_name = getattr(attr, "__module__", "") or getattr(attr, "__name__", "")
            if mod_name.startswith("v7."):
                pytest.fail(
                    f"LIB IMPORT BOUNDARY VIOLATION: {name} imports {mod_name} "
                    f"via '{attr_name}'"
                )
            if mod_name.startswith("alphaforge.") or mod_name.startswith("alphaforge"):
                pytest.fail(
                    f"LIB IMPORT BOUNDARY VIOLATION: {name} imports {mod_name} "
                    f"via '{attr_name}'"
                )
        tested += 1

    print(f"\n  Checked {tested} lib modules — boundary clean.")
