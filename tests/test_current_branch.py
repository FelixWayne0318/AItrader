import subprocess

def test_current_branch_is_available():
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    branch = result.stdout.strip()
    assert branch
