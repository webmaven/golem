from click.testing import CliRunner
from golem.cli import main

def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "Golem" in result.output
