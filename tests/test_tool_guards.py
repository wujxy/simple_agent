import pytest

from simple_agent.tools.core.guards import check_read_after_write, check_repeated_read


@pytest.mark.asyncio
async def test_read_after_edit_file_is_blocked():
    obs = await check_read_after_write(
        "read_file",
        {"path": "app.py"},
        {
            "tool_name": "edit_file",
            "ok": True,
            "changed_paths": ["app.py"],
        },
    )

    assert obs is not None
    assert obs.status == "context_required"
    assert "just updated" in obs.summary


@pytest.mark.asyncio
async def test_immediate_repeated_full_read_is_blocked():
    obs = await check_repeated_read(
        "read_file",
        {"path": "app.py"},
        {
            "tool_name": "read_file",
            "ok": True,
            "data": {
                "path": "app.py",
                "truncated": False,
            },
        },
    )

    assert obs is not None
    assert obs.status == "context_required"
    assert "already fully read" in obs.summary


@pytest.mark.asyncio
async def test_repeated_read_allows_truncated_followup_ranges():
    obs = await check_repeated_read(
        "read_file",
        {"path": "app.py", "start_line": 101},
        {
            "tool_name": "read_file",
            "ok": True,
            "data": {
                "path": "app.py",
                "truncated": True,
            },
        },
    )

    assert obs is None
