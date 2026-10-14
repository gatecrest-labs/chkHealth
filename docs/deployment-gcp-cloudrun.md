# GCP Cloud Run Deployment Guide

Deploys chkHealth on GCP Cloud Run — **internal-only**, accessible via Cloud VPN or Cloud
Interconnect. No resource has a public URL or internet-facing IP.

> **Single-replica constraint.** chkHealth uses SQLite for metrics and startup coordination.
> The Cloud Run service is set to `max-instances=1` — do not allow it to scale beyond one instance.

> **Filestore cost note.** Filestore Basic HDD starts at 1 TB minimum (~$100 USD/month at
> us-central1 rates). The actual data stored is only a few kilobytes; you are paying for the NFS
> endpoint, not the storage. This is the correct tool for SQLite-over-NFS on Cloud Run — cheaper
> alternatives (Cloud Storage FUSE) do not support SQLite's file locking.

---

## Overview

This guide uses the Terraform module in `terraform/gcp/`. It provisions:

| Resource | Purpose |
|---|---|
| VPC + application subnet | Network isolation |
| Proxy-only subnet | Required by the Regional Internal Application LB |
| Serverless VPC Access connector | Cloud Run → Filestore NFS path |
| Regional Internal Application LB | Static private ingress — WAN-only, no public IP |
| Cloud Run service (`max-instances=1`) | Single-replica container runtime |
| Filestore Basic HDD (1 TB) | Persistent data (`/app/data`) |
| Artifact Registry | Container image storage |
| Secret Manager | `SECRET_KEY` and `CP_API_KEY` |
| Cloud KMS | Envelope encryption for secrets |
| Service account | Least-privilege AR/Secret Manager access |

## Prerequisites

- Terraform ≥ 1.6
- `gcloud` CLI authenticated (`gcloud auth application-default login`)
- Docker installed locally
- APIs enabled (run once):
  ```bash
  gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    file.googleapis.com \
    secretmanager.googleapis.com \
    vpcaccess.googleapis.com \
    cloudkms.googleapis.com \
    compute.googleapis.com
  ```
- Cloud VPN or Cloud Interconnect already configured in the project

---

## Phase 1 — Infrastructure

```bash
cd terraform/gcp
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` — at minimum set:
- `project_id` — your GCP project ID
- `wan_cidr_blocks` — your corporate WAN CIDRs that can reach the LB (e.g. `["10.0.0.0/8"]`)
- `cp_mds_primary` — IP of the Check Point MDS appliance
- `cp_mds_primary_label` — display label shown in the UI

```bash
terraform init
terraform apply
```

Outputs to note:
- `artifact_registry_repo` — used in Phase 3
- `ingress_static_ip` — hand to your DNS team for Phase 6
- `secret_key_id` / `cp_api_key_id` — used in Phase 2

---

## Phase 2 — Secrets

```bash
# Generate SECRET_KEY (run from the chkHealth repo root)
uv run python manage_users.py secret

cd terraform/gcp

echo -n "PASTE_GENERATED_KEY" \
  | gcloud secrets versions add "$(terraform output -raw secret_key_id)" --data-file=-

echo -n "YOUR_CP_API_KEY" \
  | gcloud secrets versions add "$(terraform output -raw cp_api_key_id)" --data-file=-
```

---

## Phase 3 — TLS Certificate

Generate a certificate from your internal PKI, or create a self-signed cert for testing:

```bash
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 3650 \
  -subj "/CN=chkhealth.corp.example.com"
```

Add the cert and key to `terraform.tfvars`:

```hcl
ssl_certificate_pem = file("cert.pem")
ssl_private_key_pem = file("key.pem")
```

Re-apply to attach the certificate to the internal LB HTTPS listener:

```bash
terraform apply
```

---

## Phase 4 — Container Image + Cloud Run Service

```bash
cd terraform/gcp
REPO=$(terraform output -raw artifact_registry_repo)
GIT_SHA=$(git -C ../../ rev-parse --short HEAD)

gcloud auth configure-docker "$(echo $REPO | cut -d/ -f1)"

docker build --platform linux/amd64 -t $REPO/chkhealth:$GIT_SHA ../../
docker push $REPO/chkhealth:$GIT_SHA
```

Set `container_image` in `terraform.tfvars` to the full URI (e.g.
`"us-central1-docker.pkg.dev/my-project/chkhealth/chkhealth:abc1234"`) and re-apply.
The Cloud Run service is created at this step.

```bash
terraform apply
```

---

## Phase 5 — First Admin User

Cloud Run has no exec. Use a one-off Cloud Run Job that mounts the same Filestore volume:

```bash
cd terraform/gcp
REPO=$(terraform output -raw artifact_registry_repo)
PROJECT=$(gcloud config get-value project)

gcloud run jobs create create-admin \
  --image=$REPO/chkhealth:$GIT_SHA \
  --region=us-central1 \
  --service-account=chkhealth@$PROJECT.iam.gserviceaccount.com \
  --vpc-connector=chkhealth \
  --vpc-egress=private-ranges-only \
  --add-volume=name=data,type=nfs,location=$(terraform output -raw filestore_ip):/data \
  --add-volume-mount=volume=data,mount-path=/app/data \
  --set-secrets=SECRET_KEY=chkhealth-SECRET_KEY:latest \
  --set-secrets=CP_API_KEY=chkhealth-CP_API_KEY:latest \
  --args="run,python,manage_users.py,add,admin,--role,admin,--password,REPLACE_WITH_STRONG_PASSWORD" \
  --command=uv

gcloud run jobs execute create-admin --region=us-central1 --wait

# Remove the job — it contains the password in --args
gcloud run jobs delete create-admin --region=us-central1 --quiet
```

Replace `REPLACE_WITH_STRONG_PASSWORD` with a strong password before running.

---

## Phase 6 — DNS

In your internal DNS, create an A record:

```
chkhealth.corp.example.com  →  <ingress_static_ip from terraform output>
```

Verify from inside the VPN:

```bash
curl -sk https://chkhealth.corp.example.com/healthz
```

---

## Authentication Setup

### Local Users

The admin account created in Phase 5 is the bootstrap account. Use it to log in and manage
additional users through the Admin UI (`/admin`).

To manage users via CLI, run another one-off Cloud Run Job (same pattern as Phase 5):

```bash
gcloud run jobs create manage-users \
  --image=$REPO/chkhealth:$GIT_SHA \
  --region=us-central1 \
  --service-account=chkhealth@$PROJECT.iam.gserviceaccount.com \
  --vpc-connector=chkhealth \
  --vpc-egress=private-ranges-only \
  --add-volume=name=data,type=nfs,location=$(terraform output -raw filestore_ip):/data \
  --add-volume-mount=volume=data,mount-path=/app/data \
  --set-secrets=SECRET_KEY=chkhealth-SECRET_KEY:latest \
  --set-secrets=CP_API_KEY=chkhealth-CP_API_KEY:latest \
  --args="run,python,manage_users.py,list" \
  --command=uv

gcloud run jobs execute manage-users --region=us-central1 --wait
gcloud run jobs delete manage-users --region=us-central1 --quiet
```

Change `--args` to `"run,python,manage_users.py,add,alice,--role,viewer,--password,PASS"` to
add a user. See [authentication.md](authentication.md) for all `manage_users.py` subcommands.

> **Keep the local admin account.** It is your only recovery path if the remote auth
> provider is unreachable.

### RADIUS Groups

To delegate authentication to a RADIUS server, store the shared secret in Secret Manager and
add the RADIUS environment variables to the Cloud Run service.

**Step 1 — Store the RADIUS shared secret:**

```bash
PROJECT=$(gcloud config get-value project)
SA_EMAIL=chkhealth@$PROJECT.iam.gserviceaccount.com

echo -n "YOUR_RADIUS_SHARED_SECRET" \
  | gcloud secrets create chkhealth-RADIUS_SECRET --data-file=-

gcloud secrets add-iam-policy-binding chkhealth-RADIUS_SECRET \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor"
```

**Step 2 — Update the Cloud Run service with RADIUS variables:**

```bash
gcloud run services update chkhealth \
  --region=us-central1 \
  --set-secrets=RADIUS_SECRET=chkhealth-RADIUS_SECRET:latest \
  --set-env-vars=RADIUS_ENABLED=true \
  --set-env-vars=RADIUS_HOST=10.x.x.x \
  --set-env-vars=RADIUS_PORT=1812 \
  --set-env-vars=RADIUS_GROUP_ADMIN=network-admins \
  --set-env-vars=RADIUS_GROUP_VIEWER=network-viewers
```

**Step 3 — Smoke test** via a one-off Cloud Run Job:

```bash
gcloud run jobs create radius-test \
  --image=$REPO/chkhealth:$GIT_SHA \
  --region=us-central1 \
  --service-account=chkhealth@$PROJECT.iam.gserviceaccount.com \
  --vpc-connector=chkhealth \
  --vpc-egress=private-ranges-only \
  --set-secrets=SECRET_KEY=chkhealth-SECRET_KEY:latest \
  --set-secrets=RADIUS_SECRET=chkhealth-RADIUS_SECRET:latest \
  --set-env-vars=RADIUS_HOST=10.x.x.x \
  --args="run,python,-c,from app.radius_auth import authenticate; print(authenticate('testuser','testpass',host='10.x.x.x',port=1812,secret='YOUR_SECRET',timeout=5,group_admin='network-admins',group_viewer='network-viewers'))" \
  --command=uv

gcloud run jobs execute radius-test --region=us-central1 --wait
gcloud run jobs delete radius-test --region=us-central1 --quiet
```

**Role resolution:** the RADIUS server must return `Filter-Id` (attribute 11) or `Class`
(attribute 25) reply attributes containing the group name. Values are matched
case-insensitively (substring). See [authentication.md](authentication.md) for all RADIUS
variables and role resolution rules.

### Groups (RBAC)

After creating users, configure groups in the Admin UI (`/admin → Groups`) to control which
tabs and Check Point domains each user (or RADIUS group) can access.
See [authentication.md](authentication.md#groups) for the group model and an example
`groups.json`.

---

## Rotating the CP API Key

1. Generate a new read-only API key on the MDS CLI:
   ```bash
   mgmt_cli add api-key user-name <username> --format json
   ```
2. Add a new secret version:
   ```bash
   cd terraform/gcp
   echo -n "NEW_CP_API_KEY" \
     | gcloud secrets versions add "$(terraform output -raw cp_api_key_id)" --data-file=-
   ```
3. Deploy a new revision to pick up the updated secret:
   ```bash
   gcloud run services update chkhealth \
     --region=us-central1 \
     --set-secrets=CP_API_KEY=chkhealth-CP_API_KEY:latest
   ```

---

## Deploying Updates

```bash
cd terraform/gcp
REPO=$(terraform output -raw artifact_registry_repo)
NEW_GIT_SHA=$(git -C ../../ rev-parse --short HEAD)

gcloud auth configure-docker "$(echo $REPO | cut -d/ -f1)"

docker build --platform linux/amd64 -t $REPO/chkhealth:$NEW_GIT_SHA ../../
docker push $REPO/chkhealth:$NEW_GIT_SHA

gcloud run services update chkhealth \
  --image=$REPO/chkhealth:$NEW_GIT_SHA \
  --region=us-central1
```

Cloud Run performs a zero-downtime rolling deploy: the new revision receives traffic once its
`/healthz` check passes, then the old revision is drained. Because `max-instances=1` is set,
only one instance of the new revision starts before the old one is stopped.

Update `container_image` in `terraform.tfvars` to the new SHA to keep Terraform state consistent.

---

## Quick Reference

```bash
# View logs
gcloud run services logs read chkhealth --region=us-central1 --limit=50

# List revisions
gcloud run revisions list --service=chkhealth --region=us-central1

# Describe service (confirm env vars / secrets)
gcloud run services describe chkhealth --region=us-central1
```

---

## Troubleshooting

### Service fails to start or keeps restarting

```bash
gcloud run services logs read chkhealth --region=us-central1 --limit=50
```

Common causes:
- `SECRET_KEY is not set or is the insecure default` — the Secret Manager binding or the secret
  name in the Cloud Run service definition is wrong; confirm the service account has
  `secretmanager.secretAccessor` on both secrets.
- `Permission denied` writing to `/app/data` — verify the VPC connector is `READY`
  (`gcloud compute networks vpc-access connectors list`) and the Filestore IP and share path
  (`/data`) in the Cloud Run volume mount are correct.
- Gunicorn exits immediately — a Python import error; the full traceback is in the logs.

### Filestore mount fails silently (data files not found)

Verify:
1. VPC connector is `READY` (`gcloud compute networks vpc-access connectors list`)
2. `filestore_ip` from `terraform output` matches the IP in the Cloud Run volume configuration
3. The Cloud Run service's VPC egress is `private-ranges-only` or `all-traffic`

### Session cookies not marked Secure

Confirm `COOKIE_SECURE=true` is set in the service's environment variables:
```bash
gcloud run services describe chkhealth --region=us-central1 \
  --format="yaml(spec.template.spec.containers[0].env)"
```
Without it, Flask does not set the `Secure` attribute on session cookies even though the LB
terminates HTTPS.

### RADIUS authentication failing

Run the smoke test Cloud Run Job described in the RADIUS section above. Confirm the RADIUS
server is reachable from inside the VPC (outbound UDP 1812 from the Cloud Run connector's
`/28` range). Check that `Filter-Id` or `Class` attributes are returned by the RADIUS server.

### Cannot access the service URL

This deployment is internal-only. The Cloud Run service has `INGRESS_TRAFFIC_INTERNAL_AND_CLOUD_LOAD_BALANCING`
set — it has no public URL. Access must come through Cloud VPN or Cloud Interconnect, hitting
the static IP returned by `terraform output -raw ingress_static_ip`.
