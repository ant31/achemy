import sys
from pathlib import Path

import pytest
from tests.models import MockCombinedModel
from typer.testing import CliRunner

from achemy.cli import app
from achemy.codegen import generate_pydantic_code, generate_schemas_from_module_code

runner = CliRunner()


class TestCodegen:
    """Tests for achemy/codegen.py"""

    @pytest.fixture(autouse=True)
    def patch_sys_path(self, monkeypatch):
        # The CLI runs in a separate process, so we need to ensure
        # the project root is in sys.path for it to find 'tests.models'
        project_root = str(Path(__file__).parent.parent)
        monkeypatch.syspath_prepend(project_root)

    def test_generate_pydantic_code_single_model(self):
        """Test generating a Pydantic schema for a single model."""
        code, imports = generate_pydantic_code(MockCombinedModel)

        assert "class MockCombinedModelSchema(BaseModel):" in code
        assert "model_config = ConfigDict(from_attributes=True)" in code
        # Check for fields - order might vary in dict, so check for presence
        assert "name: str" in code
        assert "value: int | None = None" in code
        assert "id: UUID" in code  # from UUIDPKMixin
        assert "created_at: datetime" in code  # from UpdateMixin
        assert "updated_at: datetime" in code  # from UpdateMixin

        assert "from pydantic import BaseModel, ConfigDict" in imports
        assert "from uuid import UUID" in imports
        assert "from datetime import datetime" in imports

    def test_generate_schemas_from_module(self):
        """Test generating schemas from a full module."""
        # We use tests.models as the target module
        full_code = generate_schemas_from_module_code("tests.models")

        # Check that all concrete models have a schema
        assert "class MockCombinedModelSchema(BaseModel):" in full_code
        assert "class MockPKModelSchema(BaseModel):" in full_code
        assert "class MockUpdateModelSchema(BaseModel):" in full_code

        # Check that an abstract model does not have a schema
        assert "MockMixinBaseSchema" not in full_code

        # Check for model rebuild calls
        assert "MockCombinedModelSchema.model_rebuild()" in full_code

        # Check for collected imports at the top (sorted alphabetically)
        expected_imports = [
            "from datetime import datetime",
            "from pydantic import BaseModel, ConfigDict",
            "from uuid import UUID",
        ]
        actual_imports = full_code.split("\n\n\n")[0].splitlines()
        assert actual_imports == expected_imports

        # Check one of the generated schemas in more detail
        assert "class MockPKModelSchema(BaseModel):" in full_code
        # Be robust to field order
        assert "    name: str" in full_code
        assert "    id: UUID" in full_code

    def test_generate_schemas_from_invalid_module(self):
        """Test schema generation with an invalid module path."""
        full_code = generate_schemas_from_module_code("non.existent.module")
        assert "# Could not import module 'non.existent.module'." in full_code
        # Check for underlying error message
        assert "No module named 'non'" in full_code

    def test_no_models_found_in_module(self, tmp_path):
        """Test schema generation for a module with no AlchemyModels."""
        empty_models_file = tmp_path / "empty_models.py"
        empty_models_file.write_text("class NotAnAlchemyModel: pass")

        # Add tmp_path to sys.path to make it importable
        sys.path.insert(0, str(tmp_path))
        try:
            full_code = generate_schemas_from_module_code("empty_models")
            assert "# No concrete AlchemyModel subclasses found in empty_models" in full_code
        finally:
            sys.path.pop(0)


class TestCLI:
    """Tests for achemy/cli.py"""

    @pytest.fixture(autouse=True)
    def patch_sys_path(self, monkeypatch):
        # The CLI runs in a separate process, so we need to ensure
        # the project root is in sys.path for it to find 'tests.models'
        project_root = str(Path(__file__).parent.parent)
        monkeypatch.syspath_prepend(project_root)

    def test_generate_schemas_command_success(self, tmp_path):
        """Test the 'generate-schemas' CLI command successfully creates a file."""
        output_file = tmp_path / "schemas.py"
        result = runner.invoke(app, ["tests.models", "--output", str(output_file)])

        assert result.exit_code == 0
        assert "Pydantic schemas generated successfully" in result.stdout
        assert output_file.exists()

        content = output_file.read_text()
        assert "class MockCombinedModelSchema(BaseModel):" in content
        assert "class MockPKModelSchema(BaseModel):" in content
        assert "class MockUpdateModelSchema(BaseModel):" in content

    def test_generate_schemas_command_creates_dir(self, tmp_path):
        """Test that the output path directory is created if it doesn't exist."""
        output_dir = tmp_path / "generated" / "schemas"
        output_file = output_dir / "models.py"

        assert not output_dir.exists()

        result = runner.invoke(app, ["tests.models", "--output", str(output_file)])

        assert result.exit_code == 0
        assert output_dir.exists()
        assert output_file.exists()

    def test_generate_schemas_command_invalid_module(self, tmp_path):
        """Test the CLI command with a non-existent module."""
        output_file = tmp_path / "schemas.py"
        result = runner.invoke(app, ["non.existent.module", "--output", str(output_file)])

        assert result.exit_code == 0  # The command succeeds but writes an error comment
        assert "Pydantic schemas generated successfully" in result.stdout
        assert output_file.exists()

        content = output_file.read_text()
        assert "# Could not import module 'non.existent.module'." in content
