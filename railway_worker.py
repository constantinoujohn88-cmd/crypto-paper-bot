"""
Persistent scheduler for an always-on host (Railway or similar) - replaces
the GitHub Actions cron workflows with a real internal clock, since
GitHub's scheduled triggers are best-effort and can be delayed under load
(confirmed repeatedly in this project: missed crossovers, buying at spikes,
trailing-stop slippage all traced back to checks not happening on time).

Runs all three bots in ONE process on their own intervals, and commits +
pushes each bot's updated ledger/history to git after every check - same
repo, same files, same GitHub Pages dashboard, just triggered by this loop
instead of cron. Only one process ever pushes at a time (this one), so
there's no concurrent-push race the way there was across separate
GitHub Actions workflows.

Requires:
  - git available on PATH - NOT included in Railway's default Python
    buildpack image, whether it picks Nixpacks or its newer Railpack
    builder (confirmed: two separate crashes, FileNotFoundError: 'git',
    one under each builder - a nixpacks.toml fix had no effect once
    Railway had already switched to Railpack for this project). The
    Dockerfile in this repo installs git explicitly and sidesteps
    guessing at whichever buildpack-specific config format is current -
    keep it if you fork/move this.
  - GIT_AUTH_TOKEN environment variable: a GitHub personal access token
    with permission to push to this repo. Set as a Railway secret, never
    committed.
  - GIT_REPO_URL environment variable: e.g. "github.com/<owner>/<repo>.git"
    (no https:// or token - those get added from GIT_AUTH_TOKEN)

Deliberately clones its OWN fresh working copy into a temp directory at
startup rather than assuming Railway's build checkout still has a usable
.git directory in the deployed container (build processes sometimes strip
it to shrink the image) - this way git operations always work regardless
of how Railway packaged the deployment. All file I/O (ledger/history
files, git commands) happens inside that clone; the already-imported
Python modules' *code* still comes from wherever Railway put it, which is
fine since it's the same repo.

Also serves the dashboard (index.html + the live ledger/history files)
directly over HTTP from this same process, on Railway's PORT - reading
straight from the working copy this process just wrote to, rather than
the dashboard depending on git push + GitHub Pages rebuild finishing
first. GitHub Pages keeps working too (this doesn't replace it, both read
from the same underlying data - Pages from the repo, this from the live
clone).

Run with: python railway_worker.py
"""
import functools
import http.server
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone

import config
import ledger as ledger_module
import main as bot_main

# How often each bot actually checks, running for real on this clock.
# "5m-hybrid" shares the "5m" bot's cadence (same interval_minutes in
# config.BOTS) since it's a strategy comparison at the same speed, not a
# cadence comparison - see config.py's BOTS comment.
CHECK_INTERVAL_SECONDS = {
    "5m": 300,
    "1h": 900,
    "1d": 3600,
    "5m-hybrid": 300,
}

POLL_SECONDS = 15  # how often the scheduler wakes up to check what's due


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def git_setup() -> str:
    """Clones a fresh working copy into a temp dir and returns its path.
    See module docstring for why this doesn't reuse Railway's own build
    checkout."""
    token = os.environ.get("GIT_AUTH_TOKEN")
    repo = os.environ.get("GIT_REPO_URL")
    if not token or not repo:
        print("GIT_AUTH_TOKEN and GIT_REPO_URL must be set - see this file's docstring.",
              file=sys.stderr)
        sys.exit(1)

    run("git", "config", "--global", "user.name", "paper-trading-bot")
    run("git", "config", "--global", "user.email", "actions@users.noreply.github.com")

    # Full clone, not shallow - the repo is tiny, and a shallow history
    # can complicate the rebase-on-pull this script does every cycle.
    workdir = tempfile.mkdtemp(prefix="paper-trade-repo-")
    clone_url = f"https://x-access-token:{token}@{repo}"
    run("git", "clone", clone_url, workdir)
    return workdir


def commit_and_push(bot_key: str) -> None:
    files = config.bot_files(bot_key)
    subprocess.run(["git", "add", files["ledger"], files["history"]], check=False)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if staged.returncode == 0:
        return  # nothing changed - no-op check (e.g. a "hold" with no new history row is still a row, so this is rare)
    run("git", "commit", "-m", f"{bot_key} bot check: {datetime.now(timezone.utc).isoformat()}")
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], check=True)
    run("git", "push")


def check_one_bot(bot_key: str) -> None:
    bot_cfg = config.BOTS[bot_key]
    files = config.bot_files(bot_key)
    bot_main.setup_logging(files["log"])
    ledger = ledger_module.load_ledger(files["ledger"], config.STARTING_BALANCE_GBP)
    bot_main.run_once(ledger, bot_cfg, files)
    commit_and_push(bot_key)


def start_dashboard_server(directory: str) -> None:
    """Serves `directory` (the live working copy - index.html plus the
    per-bot ledger/history files) over HTTP in a background thread, on
    Railway's assigned PORT (falls back to 8080 for local testing)."""
    port = int(os.environ.get("PORT", 8080))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Dashboard serving on 0.0.0.0:{port} from {directory}")


def main():
    workdir = git_setup()
    os.chdir(workdir)
    print(f"Cloned into {workdir}, running from there.")
    start_dashboard_server(workdir)
    print("Railway worker started. Checking each bot on its own interval:")
    for bot_key, interval in CHECK_INTERVAL_SECONDS.items():
        print(f"  {bot_key}: every {interval}s")

    last_run = {bot_key: 0.0 for bot_key in CHECK_INTERVAL_SECONDS}

    while True:
        now = time.time()
        for bot_key, interval in CHECK_INTERVAL_SECONDS.items():
            if now - last_run[bot_key] >= interval:
                last_run[bot_key] = now
                try:
                    check_one_bot(bot_key)
                except Exception as e:
                    print(f"[{bot_key}] error during check: {e}", file=sys.stderr)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
