# chkHealth — Terraform Infrastructure

Internal-only cloud deployment of chkHealth. No service is internet-accessible.
Corporate WAN access is via Site-to-Site VPN / Direct Connect (AWS) or Cloud VPN /
Cloud Interconnect (GCP).

| Folder | Platform | Runtime |
|---|---|---|
| `aws/` | AWS | ECS Fargate + internal ALB + EFS |
| `gcp/` | GCP | Cloud Run + Regional Internal LB + Filestore |

Both platforms provision:
- A **static egress IP** (NAT Gateway EIP on AWS; Cloud NAT reserved IP on GCP) —
  hand this to your network team for allowlisting on CP MDS, SMTP, RADIUS, and SNMP targets.
- A **stable internal ingress IP/DNS** (internal ALB DNS on AWS; reserved internal IP on GCP) —
  hand this to your DNS team for the internal A/CNAME record.

See the README in each subfolder for step-by-step deployment instructions.
