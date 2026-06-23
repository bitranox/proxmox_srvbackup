"""SSH command execution adapter.

Provides functions for running commands on remote hosts via SSH and
streaming remote command output to local files.
"""

from __future__ import annotations

from .commands import local_pipe_to_file, local_run, ssh_pipe_to_file, ssh_run

__all__ = [
    "local_pipe_to_file",
    "local_run",
    "ssh_pipe_to_file",
    "ssh_run",
]
