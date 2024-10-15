# terraform-module-migration

A Python script for bulk-updating the Version Control System source of HCP
Terraform/Terraform Enterprise modules.

## Usage

```shell
# Set required environment variables
export TFC_TOKEN=""
export TFC_ORGANIZATION=""

# Run the migration script (will prompt for confirmation)
tfc-module-migrate \
    --src-namespace="source-github-org" --dst-namespace="dest-github-org" \
    --src-vcs="ot-source" --dst-vcs="ot-dest" \
    --plan-file="migration.csv"
```

## Known limitations

This script currently handles only VCS-, tag-based in the private registry of an
HCP Terraform/Terraform Enterprise deployment. The following would require
additional migration logic and are **not** supported:

- Non-VCS modules
- VCS modules with branch-based publishishing
- No-code modules

Additionally, migrations were only tested with HCP Terraform VCS OAuth Tokens
(`ot-*`) and for GitHub repositories.
