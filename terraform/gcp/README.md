# chkHealth — GCP Terraform (Cloud Run)

Provisions a fully internal deployment of chkHealth on GCP Cloud Run. No resource is
internet-accessible — all inbound traffic arrives via Cloud VPN or Cloud Interconnect.

## What gets created

| Resource | Purpose |
|---|---|
| VPC + application subnet | Network isolation |
| Proxy-only subnet | Required by Regional Internal Application LB |
| Cloud NAT + reserved static IP | **Static egress IP** for CP MDS/SMTP/RADIUS allowlisting |
| Serverless VPC Access connector | Cloud Run → Filestore NFS path |
| Regional Internal Application LB | **Static private ingress IP** — WAN-only, not internet-facing |
| Cloud Run service (max-instances=1) | Single-replica container runtime |
| Filestore Basic HDD (1 TB) | NFS persistent data (`/app/data`) |
| Artifact Registry | Container image storage |
| Secret Manager | `SECRET_KEY` and `CP_API_KEY` |
| Cloud KMS | Envelope encryption for secrets |
| Service account | Least-privilege AR/Secret Manager access |

## Prerequisites

- Terraform >= 1.6
- `gcloud` CLI authenticated (`gcloud auth application-default login`)
- Docker (for building and pushing the image)
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

## Deployment

### Phase 1 — infrastructure

```bash
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: project_id, wan_cidr_blocks, cp_mds_primary at minimum

terraform init
terraform apply
```

Outputs include `artifact_registry_repo`, `nat_egress_ip`, `ingress_static_ip`.

**Give `nat_egress_ip` to your network team for allowlisting on CP MDS/SMTP/RADIUS.**
**Give `ingress_static_ip` to your DNS team for the internal A record.**

### Phase 2 — secrets

```bash
# Generate SECRET_KEY (run from the chkHealth repo root)
uv run python manage_users.py secret

echo -n "PASTE_GENERATED_KEY" \
  | gcloud secrets versions add "$(terraform output -raw secret_key_id)" --data-file=-

echo -n "YOUR_CP_API_KEY" \
  | gcloud secrets versions add "$(terraform output -raw cp_api_key_id)" --data-file=-
```

### Phase 3 — TLS certificate

Generate a cert from your internal PKI (or self-signed for testing):

```bash
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout key.pem -out cert.pem -days 3650 \
  -subj "/CN=chkhealth.corp.example.com"
```

Add to `terraform.tfvars`:
```hcl
ssl_certificate_pem = file("cert.pem")
ssl_private_key_pem = file("key.pem")
```

### Phase 4 — container image + Cloud Run service

```bash
REPO=$(terraform output -raw artifact_registry_repo)
GIT_SHA=$(git -C ../../ rev-parse --short HEAD)

gcloud auth configure-docker $(echo $REPO | cut -d/ -f1)

docker build --platform linux/amd64 -t $REPO/chkhealth:$GIT_SHA ../../
docker push $REPO/chkhealth:$GIT_SHA

# Set container_image in terraform.tfvars, then:
terraform apply
```

### Phase 5 — first admin user

Cloud Run has no exec. Use a one-off Cloud Run Job:

```bash
REPO=$(terraform output -raw artifact_registry_repo)

gcloud run jobs create create-admin \
  --image=$REPO/chkhealth:$GIT_SHA \
  --region=us-central1 \
  --service-account=chkhealth@$(gcloud config get-value project).iam.gserviceaccount.com \
  --vpc-connector=chkhealth \
  --vpc-egress=private-ranges-only \
  --add-volume=name=data,type=nfs,location=$(terraform output -raw ingress_static_ip):/data \
  --add-volume-mount=volume=data,mount-path=/app/data \
  --set-secrets=SECRET_KEY=chkhealth-SECRET_KEY:latest \
  --set-secrets=CP_API_KEY=chkhealth-CP_API_KEY:latest \
  --args="run,python,manage_users.py,add,admin,--role,admin,--password,REPLACE_WITH_STRONG_PASSWORD" \
  --command=uv

gcloud run jobs execute create-admin --region=us-central1 --wait
gcloud run jobs delete create-admin --region=us-central1 --quiet
```

## Updating the application

```bash
docker build --platform linux/amd64 -t $REPO/chkhealth:$NEW_GIT_SHA ../../
docker push $REPO/chkhealth:$NEW_GIT_SHA
gcloud run services update chkhealth --image=$REPO/chkhealth:$NEW_GIT_SHA --region=us-central1
```

Update `container_image` in `terraform.tfvars` to the new SHA for Terraform state consistency.

## Note on existing deployment docs

`docs/deployment-gcp-cloudrun.md` uses `--allow-unauthenticated` / `--no-allow-unauthenticated`
with the public Cloud Run URL. This Terraform deploys with `INGRESS_TRAFFIC_INTERNAL_AND_CLOUD_LOAD_BALANCING`
so the service has **no public URL** — all access is through the internal LB private IP.
