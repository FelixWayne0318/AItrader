import os

def test_branch_env_presence():
    branch = os.getenv("GIT_BRANCH") or os.getenv("BRANCH_NAME")
    assert branch is None or branch.strip()
