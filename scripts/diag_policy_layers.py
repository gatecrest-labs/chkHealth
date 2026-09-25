#!/usr/bin/env python3
"""Diagnostic: show exactly what show-package and show-access-rulebase return
for a given policy package. Run from the repo root:

    uv run python scripts/diag_policy_layers.py <domain> <package>

    # List available domains:
    uv run python scripts/diag_policy_layers.py --list-domains

    # Find which domain owns a package (searches all domains):
    uv run python scripts/diag_policy_layers.py --find <package-substring>

    # Check all packages visible from the global context on each host:
    uv run python scripts/diag_policy_layers.py --global-packages <package-substring>

Example:
    uv run python scripts/diag_policy_layers.py OT-Prod cocom-fwpInt_policy
"""
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.config import Config
from app.cp_client import CPClient

HOSTS = [
    (Config.CP_MDS_PRIMARY,   Config.CP_MDS_PRIMARY_LABEL),
    (Config.CP_MDS_SECONDARY, Config.CP_MDS_SECONDARY_LABEL),
    (Config.CP_MDS_3,         Config.CP_MDS_3_LABEL),
    (Config.CP_MDS_4,         Config.CP_MDS_4_LABEL),
]


def _connect_global(host: str) -> CPClient:
    client = CPClient(host, Config.CP_API_KEY,
                      verify_ssl=Config.CP_VERIFY_SSL, timeout=Config.CP_TIMEOUT)
    client.login(domain=None)
    return client


def list_domains():
    for host, label in HOSTS:
        if not host:
            continue
        try:
            c = _connect_global(host)
            domains = c.get_domains()
            c.logout()
            print(f"{label} ({host}): {len(domains)} domains")
            for d in sorted(domains, key=lambda x: x.get("name", "")):
                print(f"  {d.get('name')!r}")
        except Exception as exc:
            print(f"{label} ({host}): FAILED — {exc}")


def global_packages(substring: str):
    """Try to reach packages from global context, or per-domain context."""
    for host, label in HOSTS:
        if not host:
            continue
        try:
            c = _connect_global(host)
            domains = [d.get("name") for d in c.get_domains()
                       if d.get("name", "").lower() != "global"]
            c.logout()
        except Exception as exc:
            print(f"{label}: global login failed — {exc}")
            continue

        print(f"\n{label} ({host}) — trying domain logins:")
        for domain in sorted(domains):
            try:
                dc = CPClient(host, Config.CP_API_KEY,
                              verify_ssl=Config.CP_VERIFY_SSL, timeout=Config.CP_TIMEOUT)
                dc.login(domain=domain)
                pkgs = dc.get_packages()
                dc.logout()
                matches = [p.get("name") for p in pkgs
                           if substring.lower() in p.get("name", "").lower()]
                if matches or not substring:
                    print(f"  {domain!r}: {[p.get('name') for p in pkgs] if not substring else matches}")
            except Exception as exc:
                print(f"  {domain!r}: login error — {exc}")
        break  # only try the first working host


def _count_entries(rulebase: list, depth: int = 0) -> dict:
    counts = {"access-rule": 0, "access-section": 0, "access-layer": 0, "other": 0}
    for entry in rulebase:
        t = entry.get("type", "unknown")
        if t in counts:
            counts[t] += 1
        else:
            counts["other"] += 1
        if t == "access-layer":
            nested = entry.get("rulebase", [])
            print(f"{'  ' * (depth+1)}inline access-layer: name={entry.get('name')!r}, "
                  f"nested entries={len(nested)}")
            sub = _count_entries(nested, depth + 1)
            for k, v in sub.items():
                counts[k] += v
    return counts


def diag_policy(domain: str, package: str):
    for host, label in HOSTS:
        if not host:
            continue
        try:
            client = CPClient(host, Config.CP_API_KEY,
                              verify_ssl=Config.CP_VERIFY_SSL, timeout=Config.CP_TIMEOUT)
            client.login(domain=domain)
            print(f"Connected to {label} ({host}) domain={domain!r}")
            break
        except Exception as exc:
            print(f"  {label}: failed — {exc}")
    else:
        raise SystemExit("Could not connect to any MDS host")

    try:
        print(f"\n--- show-package {package!r} ---")
        pkg_resp = client.call("show-package", {"name": package})
        layers = pkg_resp.get("access-layers", [])
        print(f"access-layers count: {len(layers)}")
        for i, layer in enumerate(layers):
            d = layer.get("domain") or {}
            print(f"  [{i}] name={layer.get('name')!r}  uid={layer.get('uid')!r}  "
                  f"domain={d.get('name')!r}  domain-type={d.get('domain-type')!r}")

        print()
        for layer in layers:
            lname = layer.get("name", "")
            print(f"--- show-access-rulebase {lname!r} (limit=500, offset=0) ---")
            try:
                rb_resp = client.call("show-access-rulebase", {
                    "name": lname,
                    "details-level": "standard",
                    "limit": 500,
                    "offset": 0,
                })
                total = rb_resp.get("total", "?")
                rb = rb_resp.get("rulebase", [])
                print(f"  total={total}  top-level entries returned={len(rb)}")
                counts = _count_entries(rb, depth=1)
                print(f"  type breakdown (including nested): {counts}")
            except Exception as exc:
                print(f"  ERROR: {exc}")
            print()
    finally:
        client.logout()


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--list-domains":
        list_domains()
        return
    if len(sys.argv) >= 3 and sys.argv[1] == "--find":
        global_packages(sys.argv[2])
        return
    if len(sys.argv) >= 2 and sys.argv[1] == "--global-packages":
        substring = sys.argv[2] if len(sys.argv) >= 3 else ""
        global_packages(substring)
        return
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    diag_policy(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
