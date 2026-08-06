import io
import os
import tarfile
import time
import uuid
from typing import Annotated, TypedDict , Optional

import docker
from docker.errors import NotFound

from langchain_core.tools import tool
from langchain_core.messages import AnyMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from win32inetcon import MAX_GOPHER_ATTRIBUTE_NAME

DOCKER_IMAGE = "python:3.11-slim"
CONTAINER_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3

_client = docker.from_env()
_containers :dict[str, str] = {}


def _get_or_create_container(thread_id:str):
    container_id = _containers.get(thread_id)
    #Maybe we can remove thread_id check for it
    if container_id:
        try:
            c = _client.containers.get(container_id)
            if c.status != "running":
                c.start()
            return container_id

        except NotFound:
            pass

    container = _client.containers.run(
        DOCKER_IMAGE,
        command = "sleep infinity",
        detach = True,
        network_disabled = True,
        mem_limit = "256m",
        nano_cpus = 1_000_000_000,
        user = "nobody",
        working_dir = "/tmp",
        tmpfs= {"/tmp":"size=64m"},
    )
    _containers[thread_id] = container.id
    return container.id

def _write_file_to_container(container,path:str,content:str)->None:
    """Write content to path inside the container via a tar stream"""
    data = content.encode("utf-8")
    tarstream = io.BytesIO()

    with tarfile.open(fileobj=tarstream, mode="w") as tar:
        info = tarfile.TarInfo(name=path.lstrip("/"))
        #Underdtand Tar file and its function
        info.size = len(data)
        tar.addfile(tarinfo=info, fileobj=io.BytesIO(data))

    tarstream.seek(0)
    container.put_archive("/tmp", tarstream)


def run_in_sandbox(thread_id:str,file_path:str)->dict:

    with open(file_path,"r") as f:
        code =f.read()

    container_id = _get_or_create_container(thread_id)
    container = _client.containers.get(container_id)

    container_path = f"tmp/{os.path.basename(file_path)}"
    _write_file_to_container(container,container_path,code)

    start = time.time()

    try:
        exit_code, output = container.exec_run(
            cmd=["python3", f"/{container_path}"],
            demux=True,  # separate stdout/stderr
            user="nobody",
        )
        stdout, stderr = output
        timed_out = False
    except Exception as e:
        exit_code, stdout, stderr, timed_out = 1, b"", str(e).encode(), False

    elapsed = time.time() - start
    if elapsed > CONTAINER_TIMEOUT_SECONDS:
        timed_out = True  # exec_run has no native timeout; enforce your own
        # In production: run exec_run in a thread and kill it past the limit,
        # or use container.exec_run with a wrapper like `timeout 15 python3 ...`

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
            _client.containers.get(container_id).remove(force=True)
        except NotFound:
            pass







