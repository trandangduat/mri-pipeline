from app_backend.capabilities import runtime_capabilities


def test_runtime_capabilities_reports_every_missing_dependency() -> None:
    def import_module(name: str) -> object:
        if name in {"paramiko", "yaml"}:
            raise ImportError(name)
        return object()

    result = runtime_capabilities(import_module)

    assert result["ok"] is False
    assert result["state"] == "attention"
    failed = [item for item in result["components"] if not item["ok"]]
    assert [item["id"] for item in failed] == ["paramiko", "yaml"]
    assert result["ssh"] == {
        "ok": False,
        "reason": "Paramiko is unavailable in the application backend.",
    }


def test_runtime_capabilities_keeps_diagnostics_out_of_failure_reasons() -> None:
    result = runtime_capabilities(lambda _name: object())

    assert result["ok"] is True
    assert all("python" not in str(item["reason"]).lower() for item in result["components"])
    assert set(result["diagnostics"]) == {"python_executable", "runtime_source"}
