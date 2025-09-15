import importlib
import inspect
import sys
import types
from pathlib import Path
from typing import Any, ForwardRef, Union, get_args, get_origin

from achemy.model import AlchemyModel


def _get_type_repr(t: Any) -> tuple[str, set[str]]:
    """
    Generates a string representation for a type and collects necessary imports.

    Args:
        t: The type to represent.

    Returns:
        A tuple containing the string representation of the type and a set of
        required import statements.
    """
    imports = set()

    if isinstance(t, ForwardRef):
        return f"'{t.__forward_arg__}'", imports

    origin = get_origin(t)
    args = get_args(t)

    # Handle Union types (e.g., int | str) and Optional types (e.g., str | None)
    if origin is Union or origin is types.UnionType:
        # Filter out NoneType for cleaner representation if present
        type_args = [arg for arg in args if arg is not types.NoneType]
        arg_reprs = []
        for arg in type_args:
            arg_repr, arg_imports = _get_type_repr(arg)
            arg_reprs.append(arg_repr)
            imports.update(arg_imports)

        type_str = " | ".join(sorted(arg_reprs))  # Sort for consistent output
        if types.NoneType in args:
            type_str += " | None"
        return type_str, imports

    # Handle generic types like list[int], dict[str, Any]
    if origin:
        origin_module = inspect.getmodule(origin)
        if origin_module and origin_module.__name__ not in ("builtins", "__main__", "collections.abc"):
            imports.add(f"from {origin_module.__name__} import {origin.__name__}")

        origin_name = getattr(origin, "__name__", str(origin))
        arg_reprs = []
        for arg in args:
            arg_repr, arg_imports = _get_type_repr(arg)
            arg_reprs.append(arg_repr)
            imports.update(arg_imports)

        type_str = f"{origin_name}[{', '.join(arg_reprs)}]"
        return type_str, imports

    # Handle simple types
    module = inspect.getmodule(t)
    if module and module.__name__ not in ("builtins", "__main__"):
        imports.add(f"from {module.__name__} import {t.__name__}")

    if hasattr(t, "__name__"):
        return t.__name__, imports

    return str(t), imports  # Fallback


def generate_pydantic_code(model_cls: type[AlchemyModel]) -> tuple[str, set[str]]:
    """
    Generates Python code for a Pydantic schema from an AlchemyModel.

    Args:
        model_cls: The AlchemyModel subclass to inspect.

    Returns:
        A tuple containing the generated Pydantic schema code as a string
        and a set of required import statements.
    """
    schema = model_cls.pydantic_schema()
    schema_name = f"{model_cls.__name__}Schema"

    all_imports = {"from pydantic import BaseModel, ConfigDict"}
    fields_str = []

    for name, field_info in schema.model_fields.items():
        type_annotation = field_info.annotation
        type_repr, field_imports = _get_type_repr(type_annotation)
        all_imports.update(field_imports)

        default_val_repr = ""
        if not field_info.is_required():
            default = field_info.default
            # Only include defaults for simple, repr-able types.
            if isinstance(default, (str, int, float, bool, type(None))):
                default_val_repr = f" = {default!r}"

        fields_str.append(f"    {name}: {type_repr}{default_val_repr}")

    docstring = f'"""Pydantic schema for {model_cls.__name__}."""'
    code_lines = [
        f"class {schema_name}(BaseModel):",
        f"    {docstring}",
        "    model_config = ConfigDict(from_attributes=True)",
        "",
    ]
    code_lines.extend(fields_str)

    return "\n".join(code_lines), all_imports


def generate_schemas_from_module_code(module_path: str) -> str:
    """
    Finds all AlchemyModels in a module and generates a single string
    containing all Pydantic schemas.

    Args:
        module_path: The Python import path to the module (e.g., 'my_app.models').

    Returns:
        A string containing the generated Python code for all discovered schemas.
    """
    # Add CWD to path to allow for local module imports.
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        return (
            f"# Could not import module '{module_path}'.\n"
            f"# Please ensure the path is correct and your project is in PYTHONPATH.\n# Error: {e}"
        )

    all_schema_codes = []
    all_imports = set()
    all_schema_names = []

    # Explicitly find concrete (non-abstract) subclasses of AlchemyModel.
    model_classes = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        is_alchemy_model = inspect.isclass(obj) and issubclass(obj, AlchemyModel)
        # The `__abstract__` flag on the class itself is the correct way to check.
        is_concrete_model = hasattr(obj, "__mapper__")
        if is_alchemy_model and is_concrete_model:
            model_classes.append(obj)

    model_classes.sort(key=lambda x: x.__name__)  # Sort for consistent output

    for model_cls in model_classes:
        schema_code, imports = generate_pydantic_code(model_cls)
        all_schema_codes.append(schema_code)
        all_imports.update(imports)
        all_schema_names.append(f"{model_cls.__name__}Schema")

    if not all_schema_codes:
        return f"# No concrete AlchemyModel subclasses found in {module_path}"

    header = sorted(list(all_imports))
    full_code = "\n".join(header) + "\n\n\n" + "\n\n\n".join(all_schema_codes)

    # Add calls to resolve forward references for relationships
    if all_schema_names:
        rebuild_calls = "\n".join([f"{name}.model_rebuild()" for name in sorted(all_schema_names)])
        full_code += "\n\n\n# Resolve forward references for relationships\n"
        full_code += rebuild_calls

    return full_code
