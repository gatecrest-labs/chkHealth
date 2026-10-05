# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Project foundation: Flask app factory, local bcrypt auth, group-based access control
- Admin tab: user management, group management, application log viewer, settings
- Firewall gateway detail page (`/firewalls/gateway`) with four tabs: Overview, Interfaces, Routing Table, and Routing Protocols
- Gaia API integration via management server proxy — no per-gateway credentials required; uses existing CP API key
- Live interface display (physical, VLAN, bond, loopback) with link state, speed, MAC address (R80.20+; VLAN/bond requires R81.20+)
- Routing table with text search, protocol filter (Static/OSPF/BGP/Connected), sortable columns, and 100-row pagination (R81.20+)
- BGP peer summary (state, uptime, prefixes received/active) on the Routing Protocols tab (R82+)
- Version gate banners — each tab displays a clear minimum-version message when the gateway does not meet the requirement
- `GAIA_TIMEOUT` config variable (default 15 seconds) for controlling Gaia API call timeout
