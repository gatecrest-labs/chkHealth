# Feature Reference

## Dashboard

The Dashboard is the landing page for users with dashboard access. It shows:

- **Summary bar** — total managed gateways and total access rules across the entire managed environment (environment-wide totals, not filtered by user access). Domain-restricted viewers see the same environment-wide totals as admin users. A background job recalculates these figures every 60 minutes; values are also refreshed immediately on app startup.
- **30-day trend chart** — gateway count history stored in `metrics.db` (SQLite). One data point per day.
- **Infrastructure health cards** — live status, hostname, version, and HA role for the MDS primary and secondary servers, plus reachability for up to two log servers (MLS). Polled every 15 minutes; refreshed on startup.

### Background Jobs

| Job | Interval | Triggered on startup? |
|---|---|---|
| Summary (gateway + rule count) | 60 minutes | Yes |
| Infrastructure health | 15 minutes | Yes |
| Domain cache | 30 minutes | Yes |
| Device version cache | 60 minutes | Yes (after domain cache) |

The Dashboard shows spinners while startup jobs are still running.

---

## Firewalls

Browse all gateways and clusters managed by the MDS.

1. The page loads a list of domains visible to your account.
2. Select a domain — the gateway/cluster table loads.
3. Click a gateway or cluster row to see full details: interfaces, policy version, HA members (for clusters), and all Check Point object fields returned by the API.

Domain visibility is controlled by group membership (see [authentication.md](authentication.md)). Admins see all domains.

---

## Rule Review

View access rulebases and look up objects, interfaces, and NAT rules. All access is read-only.

### Access Rulebase

1. Select a **domain** and **policy package** — the full rulebase loads (up to 2,000 rules).
2. Each rule row shows: rule number, name, source, destination, service, action, track, enabled status, and comments.
3. Use the search box to filter rules client-side.

### Object Lookup

Enter a network object or group name to retrieve its definition. Returns all matching objects in the selected domain.

### Interface Lookup

Enter one or more IP addresses (comma-separated). Returns the gateway name, interface name, subnet, and mask for any interface in the domain that matches.

### NAT Lookup

Enter an IP address. Returns all NAT rules across all policy packages in the domain where that IP appears as the original or translated source/destination.

---

## Device Review

View Check Point gateway and cluster versions across all domains, with per-domain device details and software blade status.

### All-Domains Summary

The top of the page shows a version distribution bar chart aggregated across every domain the app can reach. This gives a quick picture of how many devices are on each version across the entire environment.

- **Total devices** and **domain count** shown in the header.
- Version bars are sorted by device count, with percentage labels.
- The cache is built in the background (60-minute interval, also triggered on startup). A "Last updated" timestamp and a manual **Refresh** button are provided.

### Per-Domain Device Table

Select a domain from the dropdown and click **Load** to retrieve that domain's devices live from the API.

Each row shows:

| Column | Content |
|---|---|
| Name | Gateway or cluster name |
| Type | `Gateway` or `Cluster` (with member count for clusters) |
| Version | Gaia / CPUSE version string |
| OS | OS name (`Gaia`, etc.) |
| Hardware | Hardware model (e.g., `5000 Appliances`) |
| Active Software Blades | List of enabled blades (Firewall, VPN, IPS, etc.) |
| Comments | Object comments from the management server |

The table can be filtered by name/version/OS or by device type using the **All Types** selector.

---

## Admin

Admin-only tab. Accessible only to users with the `admin` role.

### User Management

- List all local users.
- Add users via the Admin page or the `manage_users.py` CLI.
- Users have a `role`: `admin` or `viewer`.

### Group Management

Groups control what viewer-role users can access.

| Group field | Type | Meaning |
|---|---|---|
| `members` | list of usernames | Who is in the group |
| `allowed_tabs` | list of tab keys | Which tabs members can see |
| `domain_restrict` | bool | If `true`, restrict to `allowed_domains`; if `false`, allow all domains |
| `allowed_domains` | list of domain names | Effective only when `domain_restrict` is `true` |

A user's effective tab access is the union of `allowed_tabs` across all groups they belong to. Domain access works the same way — if any group has `domain_restrict: false`, the user sees all domains.

Users with no group membership cannot access any tab.

### Application Logs

View, filter, and clear in-memory application logs. Log level can be changed live (TRACE / DEBUG / INFO / WARN / ERROR). Logs are in-memory only — they reset on restart.

### Settings

Key/value store for application settings, backed by `app_settings.json`. Currently empty defaults; keys written by the Admin UI persist across restarts.
