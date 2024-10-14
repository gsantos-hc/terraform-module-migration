from dataclasses import dataclass
from functools import cached_property
from typing import Dict, Optional


@dataclass
class TerraformModuleVcsSource:
    namespace: str
    oauth_token_id: Optional[str] = None
    github_install_id: Optional[str] = None

    def __post_init__(self):
        if self.oauth_token_id is None and self.github_install_id is None:
            raise ValueError(
                "Either oauth_token_id or github_install_id must be provided"
            )

        if self.oauth_token_id is not None and self.github_install_id is not None:
            raise ValueError(
                "Only one of oauth_token_id or github_install_id can be provided"
            )

    @property
    def is_oauth(self) -> bool:
        return self.oauth_token_id is not None

    @property
    def is_github(self) -> bool:
        return not self.is_oauth

    @property
    def key(self) -> str:
        if self.is_github:
            return "github-app-installation-id"
        return "oauth-token-id"

    @property
    def value(self) -> str:
        if self.is_github:
            return self.github_install_id  # type:ignore (None isn't possible in this code path)
        return self.oauth_token_id  # type:ignore (None isn't possible in this code path)

    @property
    def key_val_dict(self) -> Dict[str, str]:
        return {self.key: self.value}


class TerraformModule:
    """Helper class for parsing data from an HCP Terraform or Terraform Enterprise private registry
    module."""

    def __init__(self, module: dict):
        self._data = module["data"] if "data" in module.keys() else module

    @cached_property
    def attrs(self) -> dict:
        if "attributes" not in self._data.keys():
            return self._data
        return self._data["attributes"]

    @cached_property
    def vcs_attrs(self) -> Optional[dict]:
        return self.attrs.get("vcs-repo", None)

    @property
    def name(self) -> str:
        return self.attrs["name"]

    @property
    def no_code(self) -> bool:
        return self.attrs.get("no-code", False)

    @property
    def vcs_repo_branch(self) -> Optional[str]:
        if self.vcs_attrs is None:
            return None
        return self.vcs_attrs.get("branch", None)

    @property
    def vcs_repo_identifier(self) -> Optional[str]:
        if self.vcs_attrs is None:
            return None
        return self.vcs_attrs.get("identifier", None)

    @property
    def vcs_repo_display_identifier(self) -> Optional[str]:
        if self.vcs_attrs is None:
            return None
        return self.vcs_attrs.get("display-identifier", None)

    @cached_property
    def vcs_repo_namespace(self) -> Optional[str]:
        if self.vcs_repo_identifier is None:
            return None

        if self.vcs_repo_identifier.count("/") != 1:
            raise NotImplementedError(
                "Only repository names in the format :org/:repo are supported"
            )

        return self.vcs_repo_identifier.split("/")[0]

    @cached_property
    def vcs_source(self) -> Optional[TerraformModuleVcsSource]:
        if self.vcs_attrs is None or self.vcs_repo_namespace is None:
            return None

        return TerraformModuleVcsSource(
            namespace=self.vcs_repo_namespace,
            oauth_token_id=self.vcs_attrs.get("oauth-token-id", None),
            github_install_id=self.vcs_attrs.get("github-app-installation-id", None),
        )


@dataclass
class TerraformModulePayload:
    """Dataclass representing a payload for creating a new VCS-backed private registry module in
    HCP Terraform and Terraform Enterprise."""

    vcs_repo_source: TerraformModuleVcsSource
    vcs_repo_identifier: str
    vcs_repo_display_identifier: str
    vcs_repo_branch: Optional[str] = None
    no_code: bool = False

    def serialize(self):
        payload = {
            "data": {
                "type": "registry-modules",
                "attributes": {
                    "no-code": self.no_code,
                    "vcs-repo": {
                        "identifier": self.vcs_repo_identifier,
                        "display_identifier": self.vcs_repo_display_identifier,
                        **self.vcs_repo_source.key_val_dict,
                    },
                },
            }
        }

        # Add branch if provided
        if self.vcs_repo_branch:
            payload["data"]["attributes"]["vcs-repo"]["branch"] = self.vcs_repo_branch

        return payload
