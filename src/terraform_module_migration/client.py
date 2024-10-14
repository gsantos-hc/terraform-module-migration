from typing import Dict

from terrasnek.api import TFC as TerraformClient

from .models.modules import TerraformModule


def get_private_modules(client: TerraformClient) -> Dict[str, TerraformModule]:
    """Queries the HCP Terraform / Terraform Enterprise API for all private registry modules."""
    raw_modules = client.registry_modules.list_all()
    modules = {}
    for rm in raw_modules["data"]:
        module = TerraformModule(rm)
        modules[module.name] = module
    return modules
