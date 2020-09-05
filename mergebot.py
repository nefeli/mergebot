#!/usr/bin/env python3

import json
import os
import subprocess

import requests

from github import Github

LABEL = "bug"

ERROR_COMMENT = """<h2><p align="center">:construction: :construction_worker: :fire: Giving up on autorebase, please investigate: :fire: :construction_worker: :construction:</p>

    <p align="center">:rotating_light: {} :rotating_light:</p></h2>

"""


def give_up(pr, err):
    print(f"giving up...writing comment on PR {pr.number}: {err}")
    pr.create_issue_comment(ERROR_COMMENT.format(err))
    print(f"removing {LABEL} label on PR {pr.number}")
    try:
        pr.remove_from_labels(LABEL)
    except:  # pylint: disable=bare-except
        print(f"label was already removed on pr {pr.number}?")


def run(cmd):
    subprocess.check_call(cmd, shell=True)


def labeled_and_open(pr):
    return [l for l in pr.labels if l.name == LABEL] and not pr.closed_at


def mergebot():
    print(f"env: {os.environ}")

    with open(os.environ["GITHUB_EVENT_PATH"]) as f:
        event = json.loads(f.read())
    print(f"event: {event}")

    pr_num = event["number"]
    print(f"pr num: {pr_num}")

    g = Github(os.environ["INPUT_GITHUB_TOKEN"])
    repo = g.get_repo(os.environ["GITHUB_REPOSITORY"])
    pr = repo.get_pull(pr_num)
    print(f"pr title: {pr.title}")

    # My PR was just closed/merged, this could make other PRs dirty, update them
    # if they are in the autorebase queue.
    if event["action"] == "closed":
        for p in repo.get_pulls(base=pr.base.ref):
            if not labeled_and_open(p) or p.mergeable_state != "behind":
                continue
            # Just remove and re-add the label. This will kick off an mergebot
            # run against the PR.
            p.remove_from_labels(LABEL)
            p.add_to_labels(LABEL)
        return

    # Not labeled with the label we care about
    if event["action"] == "labeled" and event["label"]["name"] != LABEL:
        return

    # check if PR is unlabeled or closed
    print(f"labels: {pr.labels}")
    if not labeled_and_open(pr):
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
        try:
            pr.remove_from_labels(LABEL)
            run(f'git clone git@github.com:{os.environ["GITHUB_REPOSITORY"]}')
            run(f'cd {os.environ["GITHUB_REPOSITORY"].split("/")[1]}')
            run(f"git checkout {pr.head.ref}")
            run(f"git rebase {pr.base.ref} --autosquash")
            run(f"git push --force")
            pr.add_to_labels(LABEL)  # this will kick off a new run
        except Exception as e:  # pylint: disable=broad-except
            print(f"rebase failed: {e}")
            give_up(pr, "Rebase failed, check logs")
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
        if reviews.totalCount == 0 or not [r for r in reviews if r.state == "APPROVED"]:
            give_up(pr, "Wait for reviews")
            return

        if [r for r in reviews if r.state == "CHANGES_REQUESTED"]:
            give_up(pr, "Address reviewer comments")
            return

    # check if branch is mergeable, if so merge
    if not pr.mergeable:
        give_up(pr, "Unknown error when trying to merge, check log")
        return

    pr.merge()

    # DOGS
    pup = requests.get("https://dog.ceo/api/breeds/image/random").json()["message"]
    pr.create_issue_comment(f'<p align="center"><img src="{pup}"></p>')


if __name__ == "__main__":
    mergebot()
