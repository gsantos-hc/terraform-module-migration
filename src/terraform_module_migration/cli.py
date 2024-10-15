import os
from pathlib import Path
from typing import Dict

import click
from terrasnek.api import TFC as TerraformClient
from terrasnek.api import TFC_SAAS_URL as HCP_TERRAFORM_URL

from . import get_logger
from .migrator import TerraformModuleMigrator
from .models.modules import TerraformModuleVcsSource


def _get_vcs_source(source: str) -> Dict[str, str]:
    if source.startswith("ghain-"):
        return {"github_install_id": source}
    return {"oauth_token_id": source}


@click.command()
@click.option(
    "--src-namespace",
    type=str,
    required=True,
    help="Source namespace (e.g., GitHub organization) for module repositories.",
)
@click.option(
    "--dst-namespace",
    type=str,
    required=True,
    help="Destination namespace (e.g., GitHub organization) for module repositories.",
)
@click.option(
    "--src-vcs",
    type=str,
    required=True,
    help="Identifier for the source VCS connection, e.g. 'ot-*' or 'ghain-*'.",
)
@click.option(
    "--dst-vcs",
    type=str,
    required=True,
    help="Identifier for the destination VCS connection, e.g. 'ot-*' or 'ghain-*'.",
)
@click.option(
    "--plan-file",
    type=click.Path(file_okay=True, dir_okay=False, writable=True, path_type=Path),
    required=True,
    help="Path to the CSV file to which the migration plan will be saved.",
)
def cli(
    src_namespace: str, dst_namespace: str, src_vcs: str, dst_vcs: str, plan_file: Path
):
    logger = get_logger(__name__)

    # Check that all required user inputs are present and valid
    if not any([src_vcs.startswith("ot-"), src_vcs.startswith("ghain-")]):
        logger.error("Invalid source VCS connection identifier '%s'.", src_vcs)
        return

    if not any([dst_vcs.startswith("ot-"), dst_vcs.startswith("ghain-")]):
        logger.error("Invalid destination VCS connection identifier '%s'.", dst_vcs)
        return

    if not all(os.getenv(v) is not None for v in ["TFC_TOKEN", "TFC_ORGANIZATION"]):
        logger.error(
            "TFC_TOKEN and TFC_ORGANIZATION environment variables must be set."
        )
        return

    if plan_file.exists():
        logger.error("Plan file '%s' already exists", plan_file)
        return

    # Configure the source and destination VCS objects
    source_vcs = TerraformModuleVcsSource(src_namespace, **_get_vcs_source(src_vcs))
    dest_vcs = TerraformModuleVcsSource(dst_namespace, **_get_vcs_source(dst_vcs))

    # Instantiate the Terraform API client
    tfc_client = TerraformClient(
        url=os.getenv("TFC_URL", HCP_TERRAFORM_URL), api_token=os.getenv("TFC_TOKEN")
    )
    tfc_client.set_org(os.getenv("TFC_ORGANIZATION"))

    # Test connection to the Terraform API
    try:
        tfc_client.account.show()
    except Exception as exc:
        logger.error("Failed to query information from Terraform API: %s", str(exc))
        res = click.prompt("Do you want to continue? (Only 'yes' will be accepted)")
        if res != "yes":
            return

    # Instantiate the migrator and initiate interactive migration
    migrator = TerraformModuleMigrator(tfc_client, source_vcs, dest_vcs, logger)
    migrator.migrate(plan_file, interactive=True)
