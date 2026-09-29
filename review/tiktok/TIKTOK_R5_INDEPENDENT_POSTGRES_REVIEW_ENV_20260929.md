# TikTok R5 — Dedicated Independent PostgreSQL Review Environment

Date: 2026-09-29
Scope: TikTok only

A dedicated PostgreSQL instance has been provisioned solely to remove the reviewer's infrastructure limitation.

Render resource:
- name: `trendradar-tiktok-r5-independent-retest-pg`
- ID: `dpg-datttgflk1mc73cuvk30-a`
- region: Frankfurt
- PostgreSQL: 16
- plan: `basic_256mb`
- disk: 1 GB
- status: available
- database: `trendradar_tiktok_r5_independent_retest`

Isolation rules:
- TikTok review only;
- no production data;
- no credentials/secrets copied from existing TikTok runtime;
- no resource, database, or secret from any other channel/project;
- not a production cutover target;
- old runtime/resource remains preserved.

Purpose:
enable a reviewer to execute PG-02, PG-03, PG-04 and PG-05 fresh on a real PostgreSQL instance.

The reviewer must use reviewer-generated synthetic encryption keys/tokens/markers and must independently run the required adversarial probes.

Connection credentials/DSN are intentionally not committed to Git, packages, logs, or documentation.

This resource does not itself provide independent evidence. Only reviewer-executed probes can close the remaining gates.
