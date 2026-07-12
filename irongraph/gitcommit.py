"""Create and verify the workout commit.

The philosophy: the human performed the workout, so the human is the
author. GitHub Actions is only the mechanism. This module:

1. configures git user.name / user.email from config/irongraph.yml
   (Ashish Kurse <ashishkurse@gmail.com> by default),
2. stages exactly the pipeline-owned paths,
3. creates ONE atomic commit (data + records + achievements + charts +
   README + graph) with the provided subject/body,
4. re-reads the commit metadata with `git log` and HARD-FAILS if the
   author is not the configured human — a bot-attributed workout commit
   must never survive.

All arguments go through subprocess argv lists — no shell interpolation,
so untrusted issue text in the message body is inert.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from . import paths
from .config import load_config

PIPELINE_PATHS = ["data", "generated", "README.md"]


def run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=paths.repo_root(), capture_output=True, text=True, **kw)


def commit_workout(subject: str, body: str) -> str:
    cfg = load_config()
    name, email = cfg.git_author.name, cfg.git_author.email

    for k, v in (("user.name", name), ("user.email", email)):
        r = run(["git", "config", k, v])
        if r.returncode != 0:
            sys.exit(f"git config {k} failed: {r.stderr}")

    run(["git", "add", "--"] + PIPELINE_PATHS)
    staged = run(["git", "diff", "--cached", "--name-only"]).stdout.strip()
    if not staged:
        print("Nothing staged — no changes produced by ingestion. Aborting commit.")
        sys.exit(4)

    message = subject + "\n\n" + body
    r = run(["git", "commit", "--author", f"{name} <{email}>", "-m", message])
    if r.returncode != 0:
        sys.exit(f"git commit failed: {r.stderr or r.stdout}")

    # ---- verify metadata (never assume) -----------------------------------
    meta = run(["git", "log", "-1",
                "--format=Author: %an <%ae>%nCommitter: %cn <%ce>%nSubject: %s"]).stdout
    print(meta)
    author_line = meta.splitlines()[0] if meta else ""
    expected = f"Author: {name} <{email}>"
    if author_line != expected:
        # remove the mis-attributed commit so it can never be pushed
        run(["git", "reset", "--soft", "HEAD~1"])
        sys.exit(f"FATAL: commit author mismatch.\n  expected: {expected}\n  actual:   {author_line}\n"
                 "Commit rolled back; refusing to publish a mis-attributed workout.")
    sha = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    print(f"Verified workout commit {sha[:10]} authored by {name} <{email}>")
    return sha


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject-file", required=True)
    ap.add_argument("--body-file", required=True)
    a = ap.parse_args()
    subject = open(a.subject_file, encoding="utf-8").read().strip()
    body = open(a.body_file, encoding="utf-8").read()
    commit_workout(subject, body)


if __name__ == "__main__":
    main()
