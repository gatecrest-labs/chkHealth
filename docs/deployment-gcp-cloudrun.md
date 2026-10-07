# GCP Cloud Run Deployment Guide

Deploy chkHealth on Google Cloud Run with:
- **Filestore** for persistent data (users, groups, settings, metrics)
- **Cloud Run built-in HTTPS** — no separate load balancer required
- **Secret Manager** for `SECRET_KEY` and `CP_API_KEY`
- **Artifact Registry** as the container registry

> **Single-replica constraint.** chkHealth uses SQLite for metrics and
> startup coordination. Set `--max-instances=1` on the Cloud Run service —
> do not allow it to scale to more than one instance.

> **Filestore cost note.** Filestore Basic HDD starts at 1 TB minimum
> (~$100 USD/month at us-central1 rates). The actual data stored is only
> a few kilobytes; you are paying for the NFS endpoint, not the storage.
> This is the correct tool for SQLite-over-NFS on Cloud Run; cheaper
> alternatives (Cloud Storage FUSE) do not support SQLite's file locking.

## Prerequisites

- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Billing enabled on the project
- APIs enabled:
  ```bash
  gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    file.googleapis.com \
    secretmanager.googleapis.com \
    vpcaccess.googleapis.com
  ```
- A VPC network (Filestore requires VPC access from Cloud Run)
- Docker installed locally

Set these shell variables once; they are reused throughout this guide:

```bash
export PROJECT_ID=$(gcloud config get-value project)
export REGION=us-central1          # change to your preferred region
export APP=chkhealth
export VPC_NETWORK=default         # your VPC network name
```

---

## Phase 1 — Artifact Registry + Image Build

```bash
# Create the registry repository
gcloud artifacts repositories create $APP \
  --repository-format=docker \
  --location=$REGION \
  --description="chkhealth container images"

# Authenticate Docker to Artifact Registry
gcloud auth configure-docker $REGION-docker.pkg.dev

# Build and push the initial image
docker build --platform linux/amd64 -t $APP .
docker tag $APP:latest \
  $REGION-docker.pkg.dev/$PROJECT_ID/$APP/$APP:latest
docker push \
  $REGION-docker.pkg.dev/$PROJECT_ID/$APP/$APP:latest
```

---

## Phase 2 — Filestore Persistent Volume

### 2a. Create the Filestore instance

```bash
gcloud filestore instances create $APP \
  --zone=${REGION}-a \
  --tier=BASIC_HDD \
  --file-share=name=data,capacity=1TB \
  --network=name=$VPC_NETWORK

# Capture the IP address for use in later phases
FILESTORE_IP=$(gcloud filestore instances describe $APP \
  --zone=${REGION}-a \
  --format="value(networks[0].ipAddresses[0])")
echo "FILESTORE_IP=$FILESTORE_IP"
```

The NFS export path is `/data`. Cloud Run mounts it at `/app/data`.

### 2b. Serverless VPC Access connector

Cloud Run needs a VPC connector to reach Filestore over NFS:

```bash
gcloud compute networks vpc-access connectors create $APP \
  --region=$REGION \
  --network=$VPC_NETWORK \
  --range=10.8.0.0/28    # a /28 not already in use on your VPC

VPC_CONNECTOR=$(gcloud compute networks vpc-access connectors describe $APP \
  --region=$REGION --format="value(name)")
echo "VPC_CONNECTOR=$VPC_CONNECTOR"
```

---

## Phase 3 — Secret Manager

Generate a `SECRET_KEY` locally (requires the app dependencies installed):

```bash
uv run python manage_users.py secret
```

Store the secrets:

```bash
echo -n "PASTE_GENERATED_KEY_HERE" \
  | gcloud secrets create $APP-SECRET_KEY --data-file=-

echo -n "PASTE_YOUR_CP_API_KEY_HERE" \
  | gcloud secrets create $APP-CP_API_KEY --data-file=-
```

---

## Phase 4 — IAM Service Account

```bash
# Create a dedicated service account for the Cloud Run service
gcloud iam service-accounts create $APP \
  --display-name="chkhealth Cloud Run"

SA_EMAIL=$APP@$PROJECT_ID.iam.gserviceaccount.com

# Allow it to read the two secrets
gcloud secrets add-iam-policy-binding $APP-SECRET_KEY \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding $APP-CP_API_KEY \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor"
```

---

## Phase 5 — Deploy the Cloud Run Service

```bash
gcloud run deploy $APP \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/$APP/$APP:latest \
  --region=$REGION \
  --service-account=$SA_EMAIL \
  --port=8080 \
  --min-instances=1 \
  --max-instances=1 \
  --memory=512Mi \
  --cpu=1 \
  --timeout=120 \
  --vpc-connector=$VPC_CONNECTOR \
  --vpc-egress=private-ranges-only \
  --add-volume=name=data,type=nfs,location=$FILESTORE_IP:/data \
  --add-volume-mount=volume=data,mount-path=/app/data \
  --set-secrets=SECRET_KEY=$APP-SECRET_KEY:latest \
  --set-secrets=CP_API_KEY=$APP-CP_API_KEY:latest \
  --set-env-vars=COOKIE_SECURE=true \
  --set-env-vars=CP_MDS_PRIMARY=10.x.x.x \
  --set-env-vars=CP_MDS_PRIMARY_LABEL="HQ MDS (Provider-1)" \
  --set-env-vars=CP_VERIFY_SSL=false \
  --set-env-vars=CP_TIMEOUT=30 \
  --set-env-vars=GAIA_TIMEOUT=15 \
  --no-allow-unauthenticated
```

Fill in your actual `CP_MDS_PRIMARY` and other optional appliance
addresses (see `.env.example` for all supported variables) in the
`--set-env-vars` flags before deploying.

> **`COOKIE_SECURE=true` is required.** Cloud Run terminates TLS before
> the container; without this flag Flask will not set the `Secure`
> attribute on session cookies.

> **`--no-allow-unauthenticated`** locks the service to IAM-authenticated
> callers by default. To open it to your organisation's users, grant them
> `roles/run.invoker` on the service, or set `--allow-unauthenticated`
> if the service is on a private network only.

The service URL is printed on deploy. Cloud Run issues a `*.run.app`
certificate automatically — HTTPS is available immediately.

---

## Phase 6 — Custom Domain (optional)

To serve on your own domain instead of `*.run.app`:

```bash
gcloud run domain-mappings create \
  --service=$APP \
  --domain=chkhealth.yourdomain.com \
  --region=$REGION
```

Add the CNAME or A record shown in the output to your DNS provider.
Google manages the TLS certificate automatically.

---

## Phase 7 — Create the First Admin User

Cloud Run has no shell exec. Use a one-off Cloud Run Job that mounts the
same Filestore volume and passes `--password` to skip the interactive prompt:

```bash
# Create the job
gcloud run jobs create create-admin \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/$APP/$APP:latest \
  --region=$REGION \
  --service-account=$SA_EMAIL \
  --vpc-connector=$VPC_CONNECTOR \
  --vpc-egress=private-ranges-only \
  --add-volume=name=data,type=nfs,location=$FILESTORE_IP:/data \
  --add-volume-mount=volume=data,mount-path=/app/data \
  --set-secrets=SECRET_KEY=$APP-SECRET_KEY:latest \
  --set-secrets=CP_API_KEY=$APP-CP_API_KEY:latest \
  --args="run,python,manage_users.py,add,admin,--role,admin,--password,REPLACE_WITH_STRONG_PASSWORD" \
  --command=uv

# Run it once
gcloud run jobs execute create-admin --region=$REGION --wait

# Remove the job (it contains the password in --args)
gcloud run jobs delete create-admin --region=$REGION --quiet
```

Replace `REPLACE_WITH_STRONG_PASSWORD` with a strong password. The job
definition is deleted immediately after so the password does not persist
in the Cloud Run console.

After the job completes, open the service URL in a browser and log in.

---

## Phase 8 — Deploying Updates

```bash
# Re-authenticate to Artifact Registry if needed
gcloud auth configure-docker $REGION-docker.pkg.dev

# Build and push the new image
docker build --platform linux/amd64 -t $APP .
docker tag $APP:latest \
  $REGION-docker.pkg.dev/$PROJECT_ID/$APP/$APP:latest
docker push \
  $REGION-docker.pkg.dev/$PROJECT_ID/$APP/$APP:latest

# Deploy the new revision
gcloud run deploy $APP \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/$APP/$APP:latest \
  --region=$REGION
```

Cloud Run performs a zero-downtime rolling deploy: the new revision
receives traffic once its `/healthz` check passes, then the old revision
is drained. Because `--max-instances=1` is already set on the service,
only one instance of the new revision starts before the old one is stopped.

To monitor the rollout:

```bash
gcloud run revisions list --service=$APP --region=$REGION
```

---

## Troubleshooting

### Service fails to start / keeps restarting

View logs:

```bash
gcloud run services logs read $APP --region=$REGION --limit=50
```

Common causes:
- `SECRET_KEY is not set or is the insecure default` — the Secret Manager
  binding or the secret name in `--set-secrets` is wrong; confirm the
  service account has `secretmanager.secretAccessor` on both secrets.
- `Permission denied` writing to `/app/data` — the Filestore NFS export
  (`/data`) is not accessible; verify the VPC connector is in the same
  region and VPC as the Filestore instance.
- Gunicorn exits immediately — a Python import error; the full traceback
  is in the logs.

### Session cookies not being marked Secure

Verify `COOKIE_SECURE=true` is present in the service's environment
variables (`gcloud run services describe $APP --region=$REGION`). Without
it, Flask does not set the `Secure` attribute on cookies even though Cloud
Run terminates HTTPS. Re-deploy with `--set-env-vars=COOKIE_SECURE=true`.

### Filestore mount fails silently (data files not found)

The NFS volume is mounted at `/app/data`. If the service starts but
reports missing users, verify:
1. The VPC connector is `READY` (`gcloud compute networks vpc-access connectors list`).
2. The Filestore IP and share path (`/data`) in `--add-volume` are correct.
3. The service's VPC egress is set to `private-ranges-only` or `all-traffic`.

### Cannot access the service URL

If `--no-allow-unauthenticated` was set, unauthenticated browsers receive
a 403. Either grant `roles/run.invoker` to `allUsers` (public) or to your
Google Workspace domain:

```bash
gcloud run services add-iam-policy-binding $APP \
  --region=$REGION \
  --member="domain:yourdomain.com" \
  --role="roles/run.invoker"
```
