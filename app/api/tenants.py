"""Tenant HTTP endpoints."""


def create_tenant():
    # TODO: Validate tenant data, persist tenant and deploy task, then publish after commit.
    pass


def list_tenants():
    # TODO: Return a paginated tenant collection.
    pass


def get_tenant():
    # TODO: Return one tenant or the structured tenant_not_found error.
    pass


def update_tenant():
    # TODO: Apply a partial update only from active state and enforce version locking.
    pass


def delete_tenant():
    # TODO: Start a destroy task only when the tenant state allows deletion.
    pass
