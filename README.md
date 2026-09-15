# Check Point Provider-1 Ansible Playbooks

Ansible playbooks for querying a Check Point Provider-1 (MDS) environment via the Management API.

---

## Prerequisites

### 1. Install Ansible

If Ansible is not already installed, the easiest way on macOS is via pip:

```bash
pip3 install ansible
```

Or via Homebrew:

```bash
brew install ansible
```

Verify the install:

```bash
ansible --version
```

---

## Setup

### 2. Configure Your Credentials

Open `vars/credentials.yml` and replace the placeholder values with your MDS IP and API read-only key:

```bash
nano vars/credentials.yml
```

The file should look like this when filled in:

```yaml
---
mds_ip: "192.168.1.100"
api_key: "your-api-key-here"
```

Save and close the file.

---

### 3. Encrypt the Credentials File (Recommended)

Ansible Vault encrypts the credentials file at rest so your API key is never stored in plain text.

```bash
ansible-vault encrypt vars/credentials.yml
```

You will be prompted to create a vault password. **Remember this password** — you will need it every time you run the playbooks.

To verify the file is encrypted:

```bash
cat vars/credentials.yml
```

The contents should now appear as an encrypted block starting with `$ANSIBLE_VAULT;`.

To edit the file later if you need to update your credentials:

```bash
ansible-vault edit vars/credentials.yml
```

---

## Running the Playbooks

### Playbook 1 — List All Domains

Connects to the MDS and prints the names of all domains.

**Without vault encryption:**

```bash
ansible-playbook get_domains.yml
```

**With vault encryption:**

```bash
ansible-playbook get_domains.yml --ask-vault-pass
```

Enter your vault password when prompted.

---

### Playbook 2 — List Firewalls Across All Domains

Iterates through every domain and prints each firewall's name, management IP, version, comments, and SIC status. Gateways that are not communicating are flagged inline.

**Without vault encryption:**

```bash
ansible-playbook get_firewalls.yml
```

**With vault encryption:**

```bash
ansible-playbook get_firewalls.yml --ask-vault-pass
```

#### Optional flags

**Query a single domain** — pass `filter_domain` to limit the run to one domain:

```bash
ansible-playbook get_firewalls.yml --ask-vault-pass -e "filter_domain=CustomerA"
```

If the name does not match any domain, the playbook stops and lists the available domain names.

**Export results** — pass `export_format` to write the full inventory to a file in addition to the terminal output. Supported values are `json` and `csv`:

```bash
# JSON export
ansible-playbook get_firewalls.yml --ask-vault-pass -e "export_format=json"

# CSV export
ansible-playbook get_firewalls.yml --ask-vault-pass -e "export_format=csv"
```

The file is written to `firewall_export.json` or `firewall_export.csv` in the directory you run the playbook from.

**Combining flags** — flags can be combined freely:

```bash
ansible-playbook get_firewalls.yml --ask-vault-pass -e "filter_domain=CustomerA export_format=json"
```

---

## Understanding the Output

### Domain list (Playbook 1)

```
ok: [localhost] => {
    "msg": "Domain [1/3]: CustomerA"
}
ok: [localhost] => {
    "msg": "Domain [2/3]: CustomerB"
}
```

### Firewall inventory (Playbook 2)

A healthy gateway looks like this:

```
============================================================
DOMAIN: CustomerA  |  Gateways: 2
============================================================
--- Gateway 1 ---
Name        : fw-prod-01
Mgmt IP     : 10.0.1.1
Version     : R82
Comments    : Production edge firewall
SIC Status  : communicating

--- Gateway 2 ---
Name        : fw-prod-02
Mgmt IP     : 10.0.1.2
Version     : R82
Comments    :
SIC Status  : communicating
```

A gateway with an issue will be flagged:

```
SIC Status  : uninitialized  <-- NOT COMMUNICATING
```

A domain that could not be queried will show an error line rather than stopping the playbook:

```
ERROR - Could not login to domain (HTTP 403: ...)
```

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `SSL: CERTIFICATE_VERIFY_FAILED` | Should not occur — cert validation is disabled. Check your MDS IP is correct. |
| `Connection refused` or timeout | MDS is unreachable. Verify the IP in `credentials.yml` and that port 443 is open. |
| `HTTP 401` on login | API key is incorrect or has been revoked. |
| `HTTP 403` on a domain | The API key does not have read access to that domain. |
| `SIC Status: uninitialized` | SIC has not been established between the management server and the gateway. |
| `SIC Status: blocked` | SIC is blocked — check the gateway firewall rules or re-initialize SIC from SmartConsole. |

---

## File Structure

```
checkpoint/
├── README.md
├── ansible.cfg              # Sets yaml stdout callback for clean terminal output
├── get_domains.yml          # Playbook 1 — list domains
├── get_firewalls.yml        # Playbook 2 — list firewalls per domain
├── tasks/
│   └── query_domain.yml     # Helper tasks (called by get_firewalls.yml)
└── vars/
    └── credentials.yml      # MDS IP and API key (encrypt with Vault)
```
