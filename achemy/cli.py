from pathlib import Path
from typing import Annotated

import typer

from achemy.codegen import generate_schemas_from_module_code

app = typer.Typer(
    name="achemy",
    help="Achemy CLI: A toolkit for managing your Achemy projects.",
    add_completion=False,
)


@app.command()
def generate_schemas(
    module_path: str = typer.Argument(
        ...,
        help="The Python import path to the module containing your AlchemyModels (e.g., 'my_app.models').",
    ),
    output_file: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="The path to the output file where schemas will be written.",
            show_default=True,
        ),
    ] = Path("schemas.py"),
):
    """
    Generates static Pydantic schemas from SQLAlchemy models in a given module.
    """
    typer.echo(f"Inspecting module: {module_path}")

    schema_code = generate_schemas_from_module_code(module_path)

    # Ensure parent directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(schema_code)

    typer.secho(f"✅ Pydantic schemas generated successfully at: {output_file}", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
