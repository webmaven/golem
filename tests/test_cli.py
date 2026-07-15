from click.testing import CliRunner
from golem.cli import main

def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "Golem" in result.output

def test_cli_subcommands_exist():
    runner = CliRunner()
    for cmd in ["init", "new", "build", "serve"]:
        result = runner.invoke(main, [cmd, "--help"])
        assert result.exit_code == 0
        assert cmd in result.output or "Show this message and exit" in result.output
