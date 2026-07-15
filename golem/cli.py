import click

@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Print version details")
def main(version):
    if version:
        click.echo("Golem static site generator v0.1.0")

if __name__ == "__main__":
    main()
