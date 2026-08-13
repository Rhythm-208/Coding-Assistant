import io
import os
import tarfile
import time

from State import AgentState,TestResult
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


def _get_or_create_container(thread_id:str):
    container_id = _containers.get(thread_id)
    #Maybe we can remove thread_id check for it
    if container_id:
        try:
            c = _get_client().containers.get(container_id)
            if c.status != "running":
                c.start()
            return container_id

        except NotFound:
            pass

    container = _get_client().containers.run(
        DOCKER_IMAGE,
        command = "sleep infinity",
        detach = True,
        network_disabled = True,
        mem_limit = "256m",
        nano_cpus = 1_000_000_000,
        user = "nobody",
        working_dir = "/tmp",
    )
    _containers[thread_id] = container.id
    return container.id

def _write_file_to_container(container,path:str,content:str)->None:
    """Write content to path inside the container via a tar stream"""
    data = content.encode("utf-8")
    tarstream = io.BytesIO()

    with tarfile.open(fileobj=tarstream, mode="w") as tar:
        info = tarfile.TarInfo(name=path.lstrip("/"))
        info.size = len(data)
        tar.addfile(tarinfo=info, fileobj=io.BytesIO(data))

    tarstream.seek(0)
    container.put_archive("/tmp", tarstream)


def run_in_sandbox(thread_id:str,file_path:str)->dict:

    with open(file_path,"r") as f:
        code =f.read()

    container_id = _get_or_create_container(thread_id)
    container = _get_client().containers.get(container_id)

    container_path = os.path.basename(file_path)
    _write_file_to_container(container,container_path,code)

    start = time.time()

    try:
        exit_code, output = container.exec_run(
            cmd=["timeout", str(CONTAINER_TIMEOUT_SECONDS), "python3", f"/tmp/{container_path}"],
            demux=True,  # separate stdout/stderr
            user="nobody",
        )
        stdout, stderr = output
        timed_out = (exit_code ==124)
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

#Creating Node->

def test_node(state: AgentState) -> dict:
    full_path = os.path.join(state["repo_path"],state["file_path"])
    result = run_in_sandbox(state["thread_id"],full_path)
    passed = result["exit_code"] == 0 and not result["timed_out"]

    if passed:
        test_result = TestResult(passed=True, outcome="passed")
    else:
        outcome = "timeout" if result["timed_out"] else "failed"
        test_result = TestResult(passed=False, outcome=outcome, failure_text=result["stderr"])

    return {
        "test_result": test_result,
        "iteration": state.get("iteration", 0) + 1,
    }




