#!/usr/bin/env python3

import json
import os
import subprocess

import requests

from github import Github

LABEL = "merge-it"

ERROR_COMMENT = ":rotating_light: <b>Giving up on autorebase:</b> {}"


def give_up(pr, err):
    print(f"giving up...writing comment on PR {pr.number}: {err}")
    pr.create_issue_comment(ERROR_COMMENT.format(err))
    print(f"removing {LABEL} label on PR {pr.number}")
    try:
        pr.remove_from_labels(LABEL)
    except:  # pylint: disable=bare-except
        print(f"label was already removed on pr {pr.number}?")


def run(cmd):
    print(f"running: {cmd}")
    print(subprocess.check_output(cmd, shell=True))


def labeled_and_open(pr):
    return LABEL in [l.name for l in pr.labels] and not pr.closed_at


def rebase(pr):
    run(
        'git config --global user.email "nefeli-mergebot[bot]@users.noreply.github.com"'
    )
    run('git config --global user.name "nefeli-mergebot[bot]"')
    try:
        print(f"rebasing pr {pr.number}")
        repo = os.environ["GITHUB_REPOSITORY"]
        d = repo.split("/")[1]
        if not os.path.isdir(d):
            run(
                f'git clone https://x-access-token:{os.environ["INPUT_GITHUB_TOKEN"]}@github.com/{repo}.git'
            )
        run(f"cd {d} && git checkout {pr.base.ref}")
        run(f"cd {d} && git checkout {pr.head.ref}")
        run(f"cd {d} && git rebase {pr.base.ref} --autosquash")
        run(f"cd {d} && git push --force")
        print(f"new CI run should have been kicked off for pr {pr.number}")
    except Exception as e:  # pylint: disable=broad-except
        print(f"rebase failed: {e}")
        give_up(pr, "Rebase failed, check logs")


def mergebot():
    print(f"env: {os.environ}")

    with open(os.environ["GITHUB_EVENT_PATH"]) as f:
        event = json.loads(f.read())
    print(f"event: {event}")

    g = Github(os.environ["INPUT_GITHUB_TOKEN"])
    repo = g.get_repo(os.environ["GITHUB_REPOSITORY"])

    # get PR number
    if "number" in event:
        pr_num = event["number"]
    elif (
        "workflow_run" in event
        and "pull_requests" in event["workflow_run"]
        and event["workflow_run"]["pull_requests"]
    ):
        pr_num = event["workflow_run"]["pull_requests"][0]["number"]
    elif "branches" in event and event["branches"]:
        branch_name = event["branches"][0]["name"]
        pr = repo.get_pulls(
            head=f"{os.environ['GITHUB_REPOSITORY_OWNER']}:{branch_name}"
        )
        if pr.totalCount == 0:
            print("no pull requests in this event...")
            return
        pr_num = pr[0].number
    else:
        print("no pull requests in this event...")
        return
    print(f"pr num: {pr_num}")

    # get PR from github REST API
    pr = repo.get_pull(pr_num)
    print(f"pr title: {pr.title}")

    # My PR was just closed/merged, this could make other PRs dirty, update them
    # if they are in the autorebase queue.
    if "action" in event and event["action"] == "closed":
        print(
            f"pr {pr.number} was closed/merged. looking for others sharing this base {pr.base.ref}"
        )
        for p in repo.get_pulls(base=pr.base.ref):
            print(f"found pr: {p.number}, {labeled_and_open(p)}, {p.mergeable_state}")
            if not labeled_and_open(p):
                continue
            p.create_issue_comment(f"PR #{pr_num} was just merged/closed. Rebasing...")
            rebase(p)
        return

    # check if PR is unlabeled or closed
    print(f"labels: {pr.labels}")
    if not labeled_and_open(pr):
        print(f"pr {pr.number} is not labeled with {LABEL} or perhaps not open")
        return

    # At this point, we're an open PR with the label, and the action that
    # started this run was either a labeling of the correct label, a check_run
    # completed, a review submitted, or a status change.

    print(f"mergeable state: {pr.mergeable_state}")

    # check if branch is out-of-date and has conflicting files
    if pr.mergeable_state == "dirty":
        give_up(pr, "Conflicting files")
        return

    # check if branch is out-of-date, if so rebase
    if pr.mergeable_state == "behind":
        rebase(pr)
        return

    # check if PR is blocked for some reason (e.g., behind CI or reviews)
    if pr.mergeable_state == "blocked":
        # check if mergestate is blocked by failed status checks (CI)
        status = repo.get_commit(pr.head.sha).get_combined_status()
        print(f"status_checks: {status}")
        if status.state == "failure":
            give_up(pr, "Blocked by CI")
            return
        if status.state == "pending":
            print("CI still pending... letting CI finish")
            return

        # check if mergestate is blocked by review (need at least 1 passing
        # review + no failing reviews)
        reviews = pr.get_reviews()
        print(f"reviews: {reviews}")
        if not [r for r in reviews if r.state == "APPROVED"]:
            give_up(pr, "Wait for reviews")
            return

        if [r for r in reviews if r.state == "CHANGES_REQUESTED"]:
            give_up(pr, "Address reviewer comments")
            return

    # check if branch is mergeable, if so merge
    if not pr.mergeable:
        print("Unknown error when trying to merge, check log")
        return

    print(f"Merging PR {pr.number}")
    pr.merge(merge_method="rebase")

    # DOGS
    pup = requests.get("https://dog.ceo/api/breeds/image/random").json()["message"]
    pr.create_issue_comment(f'<p align="center"><img src="{pup}"></p>')


if __name__ == "__main__":
    mergebot()
