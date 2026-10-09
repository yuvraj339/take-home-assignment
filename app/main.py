from fastapi import FastAPI

app = FastAPI(title="Tenant Provisioning Control Plane")


@app.get("/health")
def health_check():
    # TODO: Report service and dependency health when database/broker are configured.
    pass
