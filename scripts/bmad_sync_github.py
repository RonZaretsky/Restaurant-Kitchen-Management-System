#!/usr/bin/env python3
"""Sync _bmad-output/planning-artifacts/epics.md to GitHub Milestones + Issues.

Dry-run by default (prints what would be created). Pass --apply to actually
call `gh`. Requires the gh CLI to be authenticated for this repo.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EPICS_MD = REPO_ROOT / "_bmad-output" / "planning-artifacts" / "epics.md"

EPIC_HEADER_RE = re.compile(r"^## Epic (\d+): (.+)$", re.MULTILINE)
STORY_HEADER_RE = re.compile(r"^### Story (\d+)\.(\d+): (.+)$", re.MULTILINE)


def run_gh(args, input_text=None):
    result = subprocess.run(
        ["gh"] + args,
        cwd=REPO_ROOT,
        input=input_text,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout.strip()


def get_repo_slug():
    out = run_gh(["repo", "view", "--json", "nameWithOwner"])
    return json.loads(out)["nameWithOwner"]


def parse_epics(text):
    """Split the Epic sections (after '## Epic List') into structured epics with stories."""
    body_start = text.index("\n## Epic 1:")
    body = text[body_start:]

    epic_matches = list(EPIC_HEADER_RE.finditer(body))
    epics = []
    for i, m in enumerate(epic_matches):
        epic_num = m.group(1)
        epic_title = m.group(2).strip()
        section_end = epic_matches[i + 1].start() if i + 1 < len(epic_matches) else len(body)
        section = body[m.end():section_end]

        story_matches = list(STORY_HEADER_RE.finditer(section))
        goal_end = story_matches[0].start() if story_matches else len(section)
        goal = section[:goal_end].strip()

        stories = []
        for j, sm in enumerate(story_matches):
            story_title = sm.group(3).strip()
            s_end = story_matches[j + 1].start() if j + 1 < len(story_matches) else len(section)
            story_body = section[sm.end():s_end].strip()
            stories.append({
                "num": f"{sm.group(1)}.{sm.group(2)}",
                "title": story_title,
                "body": story_body,
            })

        epics.append({
            "num": epic_num,
            "title": epic_title,
            "goal": goal,
            "stories": stories,
        })
    return epics


def ensure_label(name, color, description, apply):
    if not apply:
        print(f"  [dry-run] would ensure label '{name}' exists")
        return
    subprocess.run(
        ["gh", "label", "create", name, "--color", color, "--description", description, "--force"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )


def get_existing_milestones(repo_slug):
    """Map milestone title -> number, across open and closed milestones."""
    out = run_gh(["api", f"repos/{repo_slug}/milestones", "--method", "GET", "-f", "state=all", "-f", "per_page=100"])
    return {m["title"]: m["number"] for m in json.loads(out)}


def get_existing_issues():
    """Map issue title -> number, across open and closed issues (BMad-synced issues only, via type:story label)."""
    out = run_gh(["issue", "list", "--state", "all", "--label", "type:story", "--limit", "500", "--json", "number,title"])
    return {i["title"]: i["number"] for i in json.loads(out)}


def upsert_milestone(repo_slug, title, description, existing, apply):
    if title in existing:
        number = existing[title]
        if apply:
            run_gh([
                "api", f"repos/{repo_slug}/milestones/{number}", "-X", "PATCH",
                "-f", f"description={description}",
            ])
            print(f"  updated milestone #{number}: {title}")
        else:
            print(f"  [dry-run] would update existing milestone #{number}: {title}")
        return number

    if not apply:
        print(f"  [dry-run] would create milestone: {title}")
        return None
    out = run_gh([
        "api", f"repos/{repo_slug}/milestones",
        "-f", f"title={title}",
        "-f", f"description={description}",
    ])
    number = json.loads(out)["number"]
    print(f"  created milestone #{number}: {title}")
    return number


def upsert_issue(title, body, milestone_title, labels, existing, apply):
    if title in existing:
        number = existing[title]
        if apply:
            run_gh(["issue", "edit", str(number), "--body", body, "--milestone", milestone_title])
            print(f"  updated issue #{number}: {title}")
        else:
            print(f"  [dry-run] would update existing issue #{number}: {title}")
        return number

    if not apply:
        print(f"  [dry-run] would create issue: {title} (milestone: {milestone_title}, labels: {labels})")
        return None
    args = ["issue", "create", "--title", title, "--body", body, "--milestone", milestone_title]
    for label in labels:
        args += ["--label", label]
    url = run_gh(args)
    print(f"  created issue: {title} ({url})")
    return url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually create milestones/issues (default: dry-run)")
    args = parser.parse_args()

    if not EPICS_MD.exists():
        print(f"epics.md not found at {EPICS_MD}", file=sys.stderr)
        sys.exit(1)

    text = EPICS_MD.read_text(encoding="utf-8")
    epics = parse_epics(text)

    if not epics:
        print("No epics found in epics.md — nothing to sync.", file=sys.stderr)
        sys.exit(1)

    repo_slug = get_repo_slug()
    print(f"Repo: {repo_slug}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN (pass --apply to create)'}\n")

    print("Ensuring labels exist: type:epic, type:story")
    ensure_label("type:epic", "5319e7", "BMad epic tracking", args.apply)
    ensure_label("type:story", "0e8a16", "BMad story", args.apply)
    print()

    existing_milestones = get_existing_milestones(repo_slug)
    existing_issues = get_existing_issues()

    total_stories = 0
    for epic in epics:
        milestone_title = f"Epic {epic['num']}: {epic['title']}"
        print(f"=== {milestone_title} ===")
        print(f"  {len(epic['stories'])} stories")

        upsert_milestone(repo_slug, milestone_title, epic["goal"], existing_milestones, args.apply)

        for story in epic["stories"]:
            issue_title = f"Story {story['num']}: {story['title']}"
            upsert_issue(issue_title, story["body"], milestone_title, ["type:story"], existing_issues, args.apply)
            total_stories += 1
        print()

    print(f"Done. {len(epics)} epics -> milestones, {total_stories} stories -> issues.")
    if not args.apply:
        print("This was a dry run. Re-run with --apply to actually create/update them.")
    print(
        "Note: matching is by exact title string. Renaming an Epic/Story title in epics.md "
        "will create a new milestone/issue instead of updating the old one."
    )


if __name__ == "__main__":
    main()
