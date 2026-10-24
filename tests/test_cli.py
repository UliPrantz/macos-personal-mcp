import sys
from pathlib import Path

import pytest
from mcp_types import Tool

from macos_personal_mcp.cli import main


@pytest.mark.parametrize("read_only", [True, False])
@pytest.mark.parametrize("legacy", [True, False])
def test_legacy_cli_flag_only_changes_explicit_search_exposure(
    read_only: bool,
    legacy: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = tmp_path / "permissions.toml"
    config.write_text('[approval]\ndefault="native"\n')
    config.chmod(0o600)
    args = [
        "macos-personal-mcp",
        "schemas",
        "--config",
        str(config),
        "--read-only" if read_only else "--enable-writes",
    ]
    if legacy:
        args.append("--enable-legacy-mail-search")
    monkeypatch.setattr(sys, "argv", args)
    main()
    captured = capsys.readouterr()
    assert captured.err == ""
    tools = [Tool.model_validate_json(line) for line in captured.out.splitlines()]
    names = {tool.name for tool in tools}
    assert len(names) == (16 if read_only else 19) + int(legacy)
    assert "mail_search" in names and "mail_search_native" not in names
    assert ("mail_search_legacy" in names) is legacy
    assert ("mail_send" in names) is not read_only
    assert ("calendar_create_event" in names) is not read_only
