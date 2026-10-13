"""Installation plans must preserve the chosen Torch build."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import setup


@pytest.mark.parametrize("options,backend", [([], "cpu"), (["--gpu"], "cu126")])
def test_setup_keeps_selected_torch_build(monkeypatch, options, backend):
    commands = []
    monkeypatch.setattr(setup.sys, "argv", ["setup.py", *options])
    monkeypatch.setattr(setup, "run", lambda arguments: commands.append(list(map(str, arguments))))
    monkeypatch.setattr(setup.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    setup.main()
    installs = [command for command in commands if "install" in command]
    torch_command = next(command for command in installs if any(arg.startswith("torch==") for arg in command))
    assert f"torch==2.8.0+{backend}" in torch_command
    assert f"https://download.pytorch.org/whl/{backend}" in torch_command
    for command in installs:
        if "-r" in command:
            requirements = Path(command[command.index("-r") + 1]).read_text(encoding="utf-8").splitlines()
            assert not any(line.strip().lower().startswith(("torch==", "torch>=", "torch<=", "torch[")) for line in requirements)
