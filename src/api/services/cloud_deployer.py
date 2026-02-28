"""Cloud Run deployer for per-user MCP instances."""

from __future__ import annotations

import logging

from google.cloud import run_v2
from glyx_python_sdk.settings import settings

logger = logging.getLogger(__name__)

# Pre-built image in Artifact Registry (pushed during CI or manually)
IMAGE = "us-central1-docker.pkg.dev/cs-poc-fu4tioc8i2w4ev3epp69dm3/glyx/glyx-cloud:latest"
REGION = "us-central1"
PROJECT = "cs-poc-fu4tioc8i2w4ev3epp69dm3"


def _service_name(user_id: str) -> str:
    """Deterministic Cloud Run service name from user ID."""
    return f"glyx-user-{user_id[:8]}"


async def deploy(user_id: str) -> tuple[str, str]:
    """Deploy a per-user Cloud Run service.

    Returns (service_name, endpoint_url).
    """
    client = run_v2.ServicesAsyncClient()
    svc_name = _service_name(user_id)
    parent = f"projects/{PROJECT}/locations/{REGION}"

    service = run_v2.Service(
        template=run_v2.RevisionTemplate(
            containers=[
                run_v2.Container(
                    image=IMAGE,
                    ports=[run_v2.ContainerPort(container_port=8080)],
                    env=[
                        run_v2.EnvVar(name="OWNER_USER_ID", value=user_id),
                        run_v2.EnvVar(name="SUPABASE_URL", value=settings.supabase_url),
                        run_v2.EnvVar(name="SUPABASE_ANON_KEY", value=settings.supabase_anon_key),
                    ],
                    resources=run_v2.ResourceRequirements(
                        limits={"memory": "512Mi", "cpu": "1"},
                    ),
                ),
            ],
            scaling=run_v2.RevisionScaling(min_instance_count=0, max_instance_count=1),
        ),
        ingress=run_v2.IngressTraffic.INGRESS_TRAFFIC_ALL,
    )

    logger.info(f"[CLOUD] Deploying {svc_name} for user {user_id[:8]}...")

    operation = await client.create_service(
        parent=parent,
        service=service,
        service_id=svc_name,
    )
    result = await operation.result()
    endpoint = result.uri

    # Allow unauthenticated access (auth handled by OwnerOnly verifier in the MCP server)
    iam_client = run_v2.ServicesAsyncClient()
    await _allow_unauthenticated(iam_client, f"{parent}/services/{svc_name}")

    logger.info(f"[CLOUD] Deployed {svc_name} at {endpoint}")
    return svc_name, endpoint


async def _allow_unauthenticated(client: run_v2.ServicesAsyncClient, resource: str) -> None:
    """Set IAM policy to allow unauthenticated invocations."""
    from google.iam.v1 import iam_policy_pb2, policy_pb2
    from google.protobuf import field_mask_pb2  # noqa: F401

    policy = policy_pb2.Policy(
        bindings=[
            policy_pb2.Binding(
                role="roles/run.invoker",
                members=["allUsers"],
            ),
        ],
    )
    await client.set_iam_policy(
        request=iam_policy_pb2.SetIamPolicyRequest(resource=resource, policy=policy),
    )


async def teardown(user_id: str) -> None:
    """Delete the user's Cloud Run service."""
    client = run_v2.ServicesAsyncClient()
    svc_name = _service_name(user_id)
    name = f"projects/{PROJECT}/locations/{REGION}/services/{svc_name}"

    logger.info(f"[CLOUD] Tearing down {svc_name}...")
    operation = await client.delete_service(name=name)
    await operation.result()
    logger.info(f"[CLOUD] Deleted {svc_name}")
