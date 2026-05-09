# GitHub Traffic Intelligence

Local-first GitHub repository traffic archival, promotion tracking, and traffic intelligence.

GitHub Traffic Intelligence persistently collects and structures GitHub repository traffic data into a local SQLite database, generating a static dashboard and historical intelligence layer over time.

Unlike GitHub’s built-in traffic graphs, this system preserves historical data indefinitely and allows traffic correlation against real-world actions such as:

- Reddit posts
- Facebook posts
- Release announcements
- README rewrites
- Demo videos
- Benchmark publications
- Documentation pushes
- Social media campaigns

This project treats GitHub traffic as an intelligence surface rather than merely a statistics panel.

---

![Dashboard Overview](docs/images/dashboard-overview.png)

---

# Why This Exists

GitHub only exposes a limited rolling traffic window.

Without local archival:

- older traffic disappears
- campaign history is lost
- growth trends become invisible
- promotion impact becomes difficult to measure
- repository evolution becomes hard to analyze

This project solves that problem by continuously collecting:

- repository views
- repository clones
- popular paths
- referrers

and preserving them locally forever.

But this is not just archival.

GitHub Traffic Intelligence also introduces:

- promotion event overlays
- campaign trail windows
- framework grouping
- traffic correlation
- historical repository intelligence
- local-first ownership of analytics

---

# Features

## Historical Traffic Archival

Persist GitHub traffic history indefinitely into SQLite.

Tracks:

- Views
- Unique viewers
- Clones
- Unique cloners
- Popular paths
- Popular referrers

---

## Promotion / Action Event Intelligence

Attach real-world actions to traffic spikes.

Examples:

- Posted on `/r/git`
- Facebook launch
- Release announcement
- Benchmark publication
- New screenshots
- README overhaul
- Demo video release

Each event supports:

- editable metadata
- framework grouping
- retroactive correction
- adjustable trail windows
- event overlays on charts

---

## Static Dashboard

No external web server required.

Generates a local static HTML dashboard with:

- repository overview
- traffic charts
- event overlays
- referrer tables
- inventory/ranking views
- promotion timelines

---

## Optional Localhost API

Optional localhost-only API for:

- adding events
- editing events
- deleting events
- regenerating dashboards

Security model:

- localhost only
- no public exposure
- no arbitrary shell execution
- structured JSON actions only

---

## Automatic Daily Collection

Supports:

- cron automation
- systemd user services
- fully local-first workflows

---

## SQLite Persistence

Everything is stored locally:

- raw API responses
- normalized traffic tables
- event metadata
- repository inventory
- collection runs

---

# Quick Start

## 1. Clone Repository

    git clone https://github.com/TorMatzAndren/github-traffic.git
    cd github-traffic

---

## 2. Install Dependencies

Debian / Ubuntu:

    sudo apt install python3 sqlite3

---

## 3. Create GitHub Token

Create a GitHub personal access token with repository traffic access.

Recommended:

- Fine-grained token
- Read-only repository permissions

GitHub:

- Settings
- Developer settings
- Personal access tokens

---

## 4. Install Token Securely

    sudo install -d -m 0750 /etc/tokens
    sudo install -m 0640 -o root -g $USER /dev/null /etc/tokens/github.token

    nano /etc/tokens/github.token

Paste token into:

    /etc/tokens/github.token

---

## 5. Run Setup

    ./setup_github_traffic.sh

This automatically:

- installs local API systemd service
- enables service
- creates local config
- creates dashboard directories
- installs daily cron job
- generates first dashboard

---

## 6. Run First Collection

    ./github_traffic_daily.sh

This:

- collects traffic
- stores SQLite history
- regenerates dashboard

---

## 7. Open Dashboard

    ./open_dashboard.sh

---

# Dashboard Overview

The dashboard provides:

- repository overview cards
- historical traffic graphs
- event overlays
- referrer intelligence
- popular path tracking
- repository ranking surfaces

Top repositories are dynamically ranked by traffic activity and velocity.

---

# Promotion Event System

Promotion events are the core intelligence layer.

Example:

    Posted ChronoGit on Reddit
    → /r/git
    → framework: reddit_launch
    → trail_days: 7

Traffic changes can then be correlated against real-world actions.

---

# Example Workflows

## Reddit Launch

1. Post project to Reddit
2. Add event
3. Watch traffic spike appear
4. Compare against future campaigns

---

## Release Push

1. Publish release
2. Add release event
3. Observe clone/view impact

---

## README Rewrite

1. Improve repository presentation
2. Add documentation event
3. Compare conversion changes

---

# Architecture

## Collector

    github_traffic_collect.py

Collects GitHub traffic API endpoints.

---

## Query Layer

    github_traffic_query.py

Produces structured JSON intelligence surfaces.

---

## Event Layer

    github_traffic_event.py

Handles:

- event insertion
- editing
- deletion
- framework metadata

---

## Dashboard Generator

    generate_static_dashboard.py

Produces static HTML + JSON dashboard.

---

## Local API

    github_traffic_local_api.py

Optional localhost-only structured API.

---

## Automation

    github_traffic_daily.sh
    setup_github_traffic.sh

---

# Security Model

## Token Handling

Tokens are stored outside the repository:

    /etc/tokens/github.token

Never committed.

Never printed.

---

## Localhost API Restrictions

The API:

- binds only to `127.0.0.1`
- does not expose arbitrary shell execution
- accepts structured actions only
- regenerates dashboards safely

---

## Static Dashboard

Dashboard is static HTML.

No external SaaS dependency.

No external telemetry.

No cloud analytics.

---

# Public vs Jarri Branches

## main

Portable public version.

Features:

- static dashboard
- localhost helper API
- SQLite persistence
- event intelligence

No Jarri dependency.

---

## jarri-workspace-panel

Experimental Jarri integration branch.

Future goals:

- Jarri Workspace panel
- jarri_cmd_api.py routing
- integrated audit surfaces
- Workspace-native visualization

---

# Database Design

Primary tables:

- collection_runs
- repositories
- traffic_views_daily
- traffic_clones_daily
- popular_paths_snapshot
- popular_referrers_snapshot
- raw_api_responses
- promotion_events

Both raw and normalized data are preserved.

---

# Automation

## Cron

Daily collection:

    15 9 * * * /home/USER/projects/github-traffic/github_traffic_daily.sh

---

## systemd User Service

Local API:

    systemctl --user status github-traffic-api.service

---

# Philosophy

This project is intentionally:

- local-first
- inspectable
- archival
- deterministic
- portable
- SaaS-independent

The goal is not merely analytics.

The goal is long-term repository intelligence ownership.

---

# Roadmap

Planned future work:

- traffic velocity scoring
- campaign grouping
- anomaly detection
- repository ranking engine
- event impact scoring
- comparative repository analytics
- timeline overlays
- traffic attribution systems
- Jarri Workspace integration
- advanced intelligence layers

---

# License

MIT

---

# Author

Tor Matz Andren
https://jarri.systems
