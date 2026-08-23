from __future__ import annotations

from pathlib import Path
from typing import Sequence

import griffe


def create_griffe_loader(
    search_paths: Sequence[str | Path] | None = None,
    docstring_parser: griffe.DocstringStyle | griffe.Parser | None = None,
) -> griffe.GriffeLoader:
    """Create and configure a GriffeLoader instance with the given search paths."""
    sp = [str(p) for p in search_paths] if search_paths is not None else None
    return griffe.GriffeLoader(search_paths=sp, docstring_parser=docstring_parser)


def resolve_symbol(
    loader: griffe.GriffeLoader,
    symbol_path: str,
) -> griffe.Object | griffe.Alias:
    """Resolve a fully qualified symbol path (module, class, function, or attribute)

    using the provided GriffeLoader.
    """
    parts = symbol_path.strip().split(".")
    if not parts or not parts[0]:
        raise ValueError(f"Invalid empty symbol path: '{symbol_path}'")

    # Try loading from the longest module prefix to the shortest
    loaded_mod: griffe.Module | None = None
    remaining_parts: list[str] = []

    for i in range(len(parts), 0, -1):
        mod_name = ".".join(parts[:i])
        try:
            mod = loader.load(mod_name)
            if isinstance(mod, griffe.Module):
                loaded_mod = mod
                remaining_parts = parts[i:]
                break
        except Exception:
            continue

    if loaded_mod is None:
        raise ValueError(f"Could not load or resolve module for symbol path: '{symbol_path}'")

    current: griffe.Object | griffe.Alias = loaded_mod
    for part in remaining_parts:
        if isinstance(current, (griffe.Module, griffe.Class)):
            if part in current.members:
                current = current.members[part]
            else:
                raise ValueError(f"Symbol '{part}' not found in '{current.path}'")
        else:
            raise ValueError(f"Cannot resolve child member '{part}' from '{current.path}' ({type(current).__name__})")

    return current


def is_symbol_visible(
    name: str,
    include_private: bool = False,
    include_special: bool = False,
    is_init_allowed: bool = True,
) -> bool:
    """Determine if a symbol name should be included in documentation based on visibility rules."""
    if name == "__init__" and is_init_allowed:
        return True
    if name.startswith("__") and name.endswith("__"):
        return include_special
    if name.startswith("_"):
        return include_private
    return True


def get_module_members(
    module: griffe.Module,
    include_private: bool = False,
    include_special: bool = False,
) -> dict[str, list[griffe.Object | griffe.Alias]]:
    """Extract grouped members (classes, functions, attributes, modules) for a module."""
    classes: list[griffe.Object | griffe.Alias] = [
        cls
        for name, cls in module.classes.items()
        if is_symbol_visible(name, include_private=include_private, include_special=include_special)
    ]
    functions: list[griffe.Object | griffe.Alias] = [
        func
        for name, func in module.functions.items()
        if is_symbol_visible(name, include_private=include_private, include_special=include_special)
    ]
    attributes: list[griffe.Object | griffe.Alias] = [
        attr
        for name, attr in module.attributes.items()
        if is_symbol_visible(name, include_private=include_private, include_special=include_special)
    ]
    submodules: list[griffe.Object | griffe.Alias] = [
        submod
        for name, submod in module.modules.items()
        if is_symbol_visible(name, include_private=include_private, include_special=include_special)
    ]

    return {
        "classes": classes,
        "functions": functions,
        "attributes": attributes,
        "submodules": submodules,
    }


def get_class_members(
    cls: griffe.Class,
    include_private: bool = False,
    include_special: bool = False,
) -> dict[str, list[griffe.Object | griffe.Alias]]:
    """Extract grouped members (methods, attributes, nested classes) for a class."""
    methods: list[griffe.Object | griffe.Alias] = [
        func
        for name, func in cls.functions.items()
        if is_symbol_visible(name, include_private=include_private, include_special=include_special)
    ]
    attributes: list[griffe.Object | griffe.Alias] = [
        attr
        for name, attr in cls.attributes.items()
        if is_symbol_visible(name, include_private=include_private, include_special=include_special)
    ]
    nested_classes: list[griffe.Object | griffe.Alias] = [
        nested
        for name, nested in cls.classes.items()
        if is_symbol_visible(name, include_private=include_private, include_special=include_special)
    ]

    return {
        "methods": methods,
        "attributes": attributes,
        "nested_classes": nested_classes,
    }
