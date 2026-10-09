"""Tenant lifecycle business rules."""


def create_tenant():
    # TODO: Create a provisioning tenant and accepted deploy task in one transaction.
    pass


def update_tenant():
    # TODO: Validate state and expected version before changing tenant data.
    pass


def request_tenant_destruction():
    # TODO: Move an eligible tenant to destroying and create a destroy task.
    pass
