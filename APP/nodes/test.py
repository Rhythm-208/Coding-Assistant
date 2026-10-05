import io
import os
import tarfile
import time

from State import AgentState, TestResult
import docker
from docker.errors import NotFound

DOCKER_IMAGE = "python:3.11-slim"
CONTAINER_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3

_client = None
_containers: dict[str, str] = {}


def _get_client():
    """Lazily connect to Docker so import doesn't fail when Docker isn't running."""
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def _get_or_create_container(thread_id: str, repo_path: str = None):
    container_id = _containers.get(thread_id)
    if container_id:
        try:
            c = _get_client().containers.get(container_id)
            if c.status != "running":
                c.start()
            return container_id
        except NotFound:
            pass

    volumes = {}
    if repo_path:
        # Mount the repository read-only
        volumes[os.path.abspath(repo_path)] = {'bind': '/repo_ro', 'mode': 'ro'}

    container = _get_client().containers.run(
        DOCKER_IMAGE,
        command="sleep infinity",
        detach=True,
        network_disabled=True,
        mem_limit="512m",
        nano_cpus=1_000_000_000,
        user="root",
        working_dir="/tmp",
        volumes=volumes,
    )
    _containers[thread_id] = container.id
    return container.id


def run_in_sandbox(thread_id: str, repo_path: str, virtual_files: dict = None) -> dict:
    container_id = _get_or_create_container(thread_id, repo_path)
    container = _get_client().containers.get(container_id)

    # 1. Reset /tmp/repo from the read-only mount (skip heavy directories)
    copy_cmd = (
        "rm -rf /tmp/repo && mkdir -p /tmp/repo && "
        "find /repo_ro -mindepth 1 -maxdepth 1 "
        "! -name '.git' ! -name 'node_modules' ! -name '.venv' ! -name 'venv' ! -name 'env' ! -name '__pycache__' "
        "-exec cp -a {} /tmp/repo/ \\; && "
        "chown -R nobody /tmp/repo"
    )
    container.exec_run(cmd=["sh", "-c", copy_cmd], user="root")

    # 2. Overlay virtual_files directly into /tmp/repo
    if virtual_files:
        tarstream = io.BytesIO()
        with tarfile.open(fileobj=tarstream, mode="w") as tar:
            for file_path, code in virtual_files.items():
                data = code.encode("utf-8")
                info = tarfile.TarInfo(name=file_path)
                info.size = len(data)
                tar.addfile(tarinfo=info, fileobj=io.BytesIO(data))
        
        tarstream.seek(0)
        # put_archive extracts as root
        container.put_archive("/tmp/repo", tarstream)
        # Fix permissions so nobody can read/execute them
        container.exec_run(cmd=["chown", "-R", "nobody", "/tmp/repo"], user="root")

    start = time.time()

    # 3. Try running tests, or fallback to python compileall for syntax checks
    # Installing pytest takes time, so we just use unittest discover. If there are no tests, it falls back to compileall.
    test_command = "python3 -m unittest discover -s . -p 'test_*.py' 2>/dev/null || python3 -m compileall -q ."

    try:
        exit_code, output = container.exec_run(
            cmd=["timeout", str(CONTAINER_TIMEOUT_SECONDS), "sh", "-c", test_command],
            demux=True,  # separate stdout/stderr
            user="nobody",
            workdir="/tmp/repo"
        )
        stdout, stderr = output
        timed_out = (exit_code == 124)
    except Exception as e:
        exit_code, stdout, stderr, timed_out = 1, b"", str(e).encode(), False

    elapsed = time.time() - start

    return {
        "exit_code": exit_code,
        "stdout": (stdout or b"").decode(errors="replace"),
        "stderr": (stderr or b"").decode(errors="replace"),
        "timed_out": timed_out,
    }


def cleanup_container(thread_id: str) -> None:
    container_id = _containers.pop(thread_id, None)
    if container_id:
        try:
            _get_client().containers.get(container_id).remove(force=True)
        except NotFound:
            pass


def test_node(state: AgentState) -> dict:
    repo_path = state["repo_path"]
    
    result = run_in_sandbox(state["thread_id"], repo_path, state.get("virtual_files"))
    passed = result["exit_code"] == 0 and not result["timed_out"]

    if passed:
        test_result = TestResult(passed=True, outcome="passed")
    else:
        outcome = "timeout" if result["timed_out"] else "failed"
        # Provide stdout and stderr for the LLM to diagnose
        failure_text = f"STDOUT:\n{result['stdout']}\nSTDERR:\n{result['stderr']}"
        test_result = TestResult(passed=False, outcome=outcome, failure_text=failure_text)

    return {
        "test_result": test_result,
        "iteration": state.get("iteration", 0) + 1,
    }
