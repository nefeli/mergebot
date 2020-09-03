#!/usr/bin/env python3

import os
import subprocess
import sys

import requests

from github import Github

LABEL = "bug"

ERROR_COMMENT = """<h2><p align="center">:construction: :construction_worker: :fire: Giving up on autorebase, please investigate: :fire: :construction_worker: :construction:</p>

    <p align="center">:rotating_light: {} :rotating_light:</p></h2>

"""


def give_up(pr, err):
    print(f"giving up...writing comment on PR: {err}")
    pr.create_issue_comment(ERROR_COMMENT.format(err))
    print(f"removing {LABEL} label on PR")
    try:
        pr.remove_from_labels(LABEL)
    except:  # pylint: disable=bare-except
        print("label was already removed?")
    sys.exit(-1)


def run(cmd):
    subprocess.check_call(cmd, shell=True)


def mergebot():
    print(f"env: {os.environ}")
    pr_num = int(os.environ["GITHUB_REF"].split("pull/")[1].split("/")[0])
    print(f"pr num: {pr_num}")

    g = Github(os.environ["INPUT_GITHUB_TOKEN"])
    repo = g.get_repo(os.environ["GITHUB_REPOSITORY"])
    pr = repo.get_pull(pr_num)
    print(f"pr title: {pr.title}")

    # check if PR is unlabeled or closed
    print(f"labels: {pr.labels}")
    if not [l for l in pr.labels if l.name == LABEL] or pr.closed_at:
        return

    print(f"mergeable state: {pr.mergeable_state}")

    # check if branch is out-of-date and has conflicting files
    if pr.mergeable_state == "dirty":
        give_up(pr, "Conflicting files")

    # check if branch is out-of-date, if so rebase
    if pr.mergeable_state == "behind":
        try:
            pr.remove_from_labels(LABEL)
            run(f'git clone git@github.com:{os.environ["GITHUB_REPOSITORY"]}')
            run(f'cd {os.environ["GITHUB_REPOSITORY"].split("/")[1]}')
            run(f"git checkout {pr.head.ref}")
            run(f"git rebase {pr.base.ref} --autosquash")
            run(f"git push --force")
            pr.add_to_labels(LABEL)
        except Exception as e:  # pylint: disable=broad-except
            print(f"rebase failed: {e}")
            give_up(pr, "Rebase failed, check logs")

    if pr.mergeable_state == "blocked":
        # check if mergestate is blocked by failed status checks
        status = repo.get_commit(pr.head.sha).get_combined_status()
        print(f"status_checks: {status}")
        if status.state == "failure":
            give_up(pr, "Blocked by jenkins")
        elif status.state == "pending":
            print("jenkins still pending... letting jenkins finish")
            return

        # check if mergestate is blocked by review (need at least 1 passing
        # review + no failing reviews)
        reviews = pr.get_reviews()
        print(f"reviews: {reviews}")
        if reviews.totalCount == 0 or not [r for r in reviews if r.state == "APPROVED"]:
            give_up(pr, "Wait for reviews")

        if [r for r in reviews if r.state == "CHANGES_REQUESTED"]:
            give_up(pr, "Address reviewer comments")

    # check if branch is mergeable, if so merge
    if not pr.mergeable:
        give_up(pr, "Unknown error when trying to merge, check log")

    pr.merge()

    # DOGS
    pup = requests.get("https://dog.ceo/api/breeds/image/random").json()["message"]
    pr.create_issue_comment(f'<p align="center"><img src="{pup}"></p>')


if __name__ == "__main__":
    mergebot()
