import csv
import io
import logging
from functools import cached_property
from pathlib import Path
from typing import Dict, List, Optional

import click
from prettytable import PrettyTable
from terrasnek.api import TFC as TerraformClient
from tqdm import tqdm

from . import get_logger
from .client import get_private_modules
from .models.modules import (
    TerraformModule,
    TerraformModulePayload,
    TerraformModuleVcsSource,
)


class TerraformModuleMigrationPlan:
    HEADERS = (
        "Module Name",
        "No-Code",
        "Source VCS",
        "Source Repo",
        "Source Branch",
        "Dest VCS",
        "Dest Repo",
        "Dest Branch",
    )

    def __init__(
        self,
        source_modules: Dict[str, TerraformModule],
        dest_payloads: Dict[str, TerraformModulePayload],
    ):
        self.source_modules = source_modules
        self.dest_payloads = dest_payloads

    @cached_property
    def plan_entries(self) -> List[tuple]:
        return [self._get_plan_entry(name) for name in self.dest_payloads.keys()]

    def get_plan(self, headers: bool = False) -> List[tuple]:
        if headers:
            return [self.HEADERS] + self.plan_entries
        return self.plan_entries

    def get_plan_csv(self) -> str:
        output = io.StringIO()
        csv.writer(output).writerows(self.get_plan(headers=True))
        return output.getvalue()

    def _get_plan_entry(self, name: str) -> tuple:
        return (
            name,
            self.dest_payloads[name].no_code,
            (
                self.source_modules[name].vcs_source.value
                if self.source_modules[name].vcs_source is not None
                else None
            ),
            self.source_modules[name].vcs_repo_identifier,
            self.source_modules[name].vcs_repo_branch,
            self.dest_payloads[name].vcs_repo_source.value,
            self.dest_payloads[name].vcs_repo_identifier,
            self.dest_payloads[name].vcs_repo_branch,
        )


class TerraformModuleMigrator:
    def __init__(
        self,
        tfc_client: TerraformClient,
        source_vcs: TerraformModuleVcsSource,
        dest_vcs: TerraformModuleVcsSource,
        logger: Optional[logging.Logger] = None,
    ):
        self.client = tfc_client
        self.source_vcs = source_vcs
        self.dest_vcs = dest_vcs
        self.no_code = False  # No-code modules not yet supported

        if logger is not None:
            self.logger = logger
        else:
            self.logger = get_logger(__name__)

    def migrate(self, plan_file: Path, interactive: bool = True) -> None:
        # Query the API for all private registry modules
        self.logger.info("Querying the Terraform API for all private registry modules")
        modules = get_private_modules(self.client)
        self.logger.info("Found %d private registry modules", len(modules))

        # Filter modules
        filtered = self._filter_modules(modules=modules)
        if len(filtered) < 1:
            self.logger.info("No modules match migration criteria")
            return

        # Construct payloads for new modules to replace old modules
        payloads = self._get_new_module_payloads(filtered)

        # Write out the specification of modules to be deleted and recreated
        plan = TerraformModuleMigrationPlan(filtered, payloads)
        self.logger.debug("Writing migration plan to %s", plan_file)
        with plan_file.open("w") as fout:
            fout.write(plan.get_plan_csv())

        # If in interactive mode, print a summary table and request user confirmation
        if interactive:
            table = PrettyTable(plan.HEADERS)
            table.add_rows(plan.get_plan(headers=False))

            click.echo(table)

            response = input("Do you want to proceed (only 'yes' will be accepted)? ")
            if response.lower() != "yes":
                return

        # Migrate modules. If in interactive mode, print a progress bar.
        if interactive:
            with tqdm(total=len(payloads), unit="modules") as pbar:
                for name, payload in payloads.items():
                    self._migrate_module(name, payload)
                    pbar.update(1)
        else:
            for name, payload in payloads.items():
                self._migrate_module(name, payload)

    def _filter_modules(
        self, modules: Dict[str, TerraformModule]
    ) -> Dict[str, TerraformModule]:
        return {
            name: module
            for name, module in modules.items()
            if self._filter_module(module)
        }

    def _filter_module(self, module: TerraformModule) -> bool:
        if not self.no_code and module.no_code:
            self.logger.info("'%s' excluded: no-code module", module.name)
            return False
        if module.vcs_source is None:
            self.logger.info("'%s' excluded: not a VCS module", module.name)
            return False
        if module.vcs_source.key_val_dict != self.source_vcs.key_val_dict:
            self.logger.info(
                "'%s' excluded: does not match source VCS provider for migration",
                module.name,
            )
            return False
        if module.vcs_source.namespace != self.source_vcs.namespace:
            self.logger.info(
                "'%s' excluded: does not match source namespace for migration",
                module.name,
            )
            return False
        return True

    def _get_new_module_payloads(
        self, modules: Dict[str, TerraformModule]
    ) -> Dict[str, TerraformModulePayload]:
        """Returns a dictionary of module names to their corresponding new-module payloads."""
        return {
            name: self._get_new_module_payload(module)
            for name, module in modules.items()
        }

    def _get_new_module_payload(self, module) -> TerraformModulePayload:
        """Returns a payload object for a new private registry module, replacing the given module's
        VCS connection with the destination VCS connection."""
        if module.vcs_repo_identifier != module.vcs_repo_display_identifier:
            raise NotImplementedError(
                "Support is only available for repositories with the same identifier and display identifier"
            )

        new_id = self._get_new_repo_identifier(module)
        return TerraformModulePayload(
            vcs_repo_source=self.dest_vcs,
            vcs_repo_identifier=new_id,
            vcs_repo_display_identifier=new_id,
            vcs_repo_branch=module.vcs_repo_branch,
            no_code=module.no_code,
        )

    def _get_new_repo_identifier(self, module: TerraformModule) -> str:
        if module.vcs_repo_identifier is None:
            raise ValueError("Module does not have a VCS repository identifier")

        if module.vcs_repo_identifier.count("/") != 1:
            raise NotImplementedError(
                "Only repository names in the format :org/:repo are supported"
            )

        return f"{self.dest_vcs.namespace}/{module.vcs_repo_identifier.split("/")[1]}"

    def _migrate_module(self, name: str, payload: TerraformModulePayload) -> None:
        # Delete the existing module
        try:
            self.logger.info("Deleting module '%s'", name)
            self.client.registry_modules.destroy(name)
        except Exception as exc:
            raise RuntimeError(f"Failed to delete module {name}") from exc

        # Create the new module
        try:
            self.logger.info("Creating module '%s'", name)
            self.client.registry_modules.publish_from_vcs(payload.serialize())
        except Exception as exc:
            raise RuntimeError(f"Failed to create module {name}") from exc
