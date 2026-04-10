# v0.4.0 Release Plan

## Status: In Progress

---

## Remaining Steps

### Step 1 — Fix Upload Modal Bug (BLOCKING)
An agent is actively fixing an issue in the frontend upload modal. Wait for that fix to land before proceeding.

### Step 2 — Rebuild & Push Backend Image
After the upload modal fix is committed:
```bash
cd /mnt/nvm/repos/transcribe-app
USE_REMOTE_BUILDER=true SKIP_SECURITY_SCAN=true ./scripts/docker-build-push.sh backend
```
> Only rebuild frontend if frontend files changed. Otherwise backend only.

### Step 3 — Fresh One-Liner Install Test (task #42)
Delete the test directory and run the setup script as a brand-new user:
```bash
rm -rf ~/OT_TEST
curl -fsSL https://raw.githubusercontent.com/davidamacey/OpenTranscribe/master/setup-opentranscribe.sh | bash
```
Verify:
- [ ] Setup completes without errors
- [ ] Auto-start prompt appears at end
- [ ] `cd` into project directory works (no "No such file or directory")
- [ ] Upload modal works correctly
- [ ] Diarization uses `speaker-diarization-community-1` (not 3.1)
- [ ] No false-negative PyAnnote validation warnings
- [ ] SSL cert reminder shown when HTTPS configured

### Step 4 — Publish GitHub Release (task #24, needs approval)
```bash
gh release create v0.4.0 \
  --title "v0.4.0: Enterprise Authentication, Neural Search & Native Transcription Pipeline" \
  --notes-file RELEASE_NOTES.md \
  --latest
```

### Step 5 — Post-Publish Security Scan (task #27)
Run after release is live (can run overnight, non-blocking):
```bash
USE_REMOTE_BUILDER=true ./scripts/docker-build-push.sh backend   # with security scan (no SKIP_SECURITY_SCAN)
```
Or run standalone:
```bash
./scripts/security-scan.sh davidamacey/opentranscribe-backend:v0.4.0
./scripts/security-scan.sh davidamacey/opentranscribe-frontend:v0.4.0
```

### Step 6 — GitHub Release Notification (task #40)
GitHub's native release notification emails all watchers automatically when `gh release create --latest` runs. No manual action needed.

### Step 7 — Triage Dependabot PRs for 0.4.1 (task #39)
Review open Dependabot PRs and decide which to merge for the 0.4.1 patch cycle.
```bash
gh pr list --label dependencies
```

---

## Contributors to Credit in Release

### Code Contributors

| GitHub | Name | Contribution |
|--------|------|-------------|
| [@vfilon](https://github.com/vfilon) | Vitali Filon | Full LDAP/AD auth implementation — 9 commits (PR #117): auth engine, username mapping, auth_type handling, password restrictions, settings UI, docs, migration detection |
| [@imorrish](https://github.com/imorrish) | Ian Morrish | Submitted PR #117; Postgres password reset guide in troubleshooting docs (PR #1) |

### Issue Reports Implemented in v0.4.0

| GitHub | Issues | Features Delivered |
|--------|--------|--------------------|
| [@imorrish](https://github.com/imorrish) | #129, #138, #145, #146 | Scrollable speaker dropdown; filename in AI summary; collection/tag at upload; per-collection AI prompt |
| [@it-service-gemag](https://github.com/it-service-gemag) | #151, #152, #153 | Disable diarization per upload; disable AI summary per upload; per-transcription model selection |
| [@Politiezone-MIDOW](https://github.com/Politiezone-MIDOW) | #134 | File retention / auto-deletion system |
| [@coltrall](https://github.com/coltrall) | #137 | Docker daemon detection fix in install script |
| [@SQLServerIO](https://github.com/SQLServerIO) | #109 | Pagination for large transcripts (file detail page hang) |

> All contributors credited in `CHANGELOG.md` (Contributors section under v0.4.0) and `docs-site/blog/2026-02-07-v0.4.0-release.md`.

---

## Build Commands Reference

```bash
# Multi-arch build + push (ALWAYS use remote builder)
USE_REMOTE_BUILDER=true ./scripts/docker-build-push.sh backend
USE_REMOTE_BUILDER=true ./scripts/docker-build-push.sh frontend
USE_REMOTE_BUILDER=true ./scripts/docker-build-push.sh          # both

# Quick iteration (skip security scan)
USE_REMOTE_BUILDER=true SKIP_SECURITY_SCAN=true ./scripts/docker-build-push.sh backend

# Single-platform local test only
PLATFORMS=linux/amd64 ./scripts/docker-build-push.sh backend
```

---

## Issues & PRs Included in v0.4.0

| # | Title | Contributor |
|---|-------|-------------|
| #5 | Stop/cancel support for reindex | Internal |
| #10 | TUS 1.0.0 resumable uploads | Internal |
| #59 | Native 256-dim speaker centroids (v4) | Internal |
| #80 | Native 256-dim speaker centroids (v4) | Internal |
| #119 | LDAP/Active Directory authentication | Internal (built on @vfilon PR #117) |
| #122 | URL download quality settings | Internal |
| #125 | Keycloak federated logout | Internal |
| #127 | Super admin PKI + local password fallback | Internal |
| #129 | Scrollable speaker dropdown | Internal |
| #134 | File retention / auto-deletion | Internal |
| #137 | Docker permission error detection | Internal |
| #138 | Filename in summary response | Internal |
| #140 | AI auto-labeling (tags + collections) | Internal |
| #141 | Speaker metadata parsing + attributes | Internal |
| #142 | Organization context for LLM summaries | Internal |
| #143 | Selective pipeline reprocessing | Internal |
| #144 | Speaker pre-clustering | Internal |
| #145 | Collection + tag selection at upload | Internal |
| #146 | Per-collection AI summarization prompts | Internal |
| #147 | Jump-to-timestamp links in speaker editor | Internal |
| #148 | User groups + collection sharing | Internal |
| #150 | Multi-provider cloud ASR (8 providers) | Internal |
| #151 | Disable speaker diarization per upload | Internal |
| #152 | Disable AI summary per upload | Internal |
| #153 | Per-transcription model selection | Internal |
| #155 | Progressive Web App + mobile overhaul | Internal |
