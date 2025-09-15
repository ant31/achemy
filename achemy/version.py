import os
import platform
import subprocess
from functools import cache
from typing import Any

from achemy import __version__


@cache
def get_git_sha():
    if os.path.exists("GIT_HEAD"):
        with open("GIT_HEAD", encoding="utf-8") as openf:
            return openf.read()
    else:
        try:
            return subprocess.check_output(["git", "rev-parse", "HEAD"]).strip()[0:8].decode()
        except (OSError, subprocess.CalledProcessError):
            pass
    return "unknown"


class Version:
    _version: str = __version__

    def __init__(self):
        pass

    def __str__(self) -> str:
        return self.text()

    @classmethod
    def set_version(cls, version: str) -> None:
        cls._version = version

    @property
    def version(self) -> dict[str, Any]:
        return {
            "version": self._version,
            "python": {
                "version": platform.python_version(),
                "implementation": platform.python_implementation(),
            },
            "system": platform.system(),
            "sha": get_git_sha(),
        }

    @property
    def app_version(self) -> str:
        return self.version["version"]

    def to_dict(self) -> dict[str, Any]:
        return self.version

    def text(self) -> str:
        return ", ".join(
            [
                f"Running {self.version['version']}",
                f"with {self.version['python']['implementation']} {self.version['python']['version']}",
                f"on {self.version['system']}",
            ]
        )


VERSION = Version()
