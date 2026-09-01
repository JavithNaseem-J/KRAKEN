from __future__ import annotations

import re
from pathlib import Path

from src.utils.config import DEFAULT_LLM_FALLBACK_MODEL, DEFAULT_LLM_MODEL, Settings

ROOT = Path(__file__).resolve().parents[2]


def _env_value(text: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}=(.+)$", text, re.MULTILINE)
    assert match, f"Missing {key}"
    return match.group(1).strip()


def _render_value(text: str, key: str) -> str:
    match = re.search(
        rf"- key: {re.escape(key)}\s+value: ([^\s]+)",
        text,
        re.MULTILINE,
    )
    assert match, f"Missing Render value for {key}"
    return match.group(1).strip()


def test_llm_defaults_are_consistent_across_repository_configuration() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    render_blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")

    assert Settings.model_fields["llm_model"].default == DEFAULT_LLM_MODEL
    assert Settings.model_fields["llm_fallback_model"].default == DEFAULT_LLM_FALLBACK_MODEL
    assert _env_value(env_example, "LLM_MODEL") == DEFAULT_LLM_MODEL
    assert _env_value(env_example, "LLM_FALLBACK_MODEL") == DEFAULT_LLM_FALLBACK_MODEL
    assert _render_value(render_blueprint, "LLM_MODEL") == DEFAULT_LLM_MODEL
    assert _render_value(render_blueprint, "LLM_FALLBACK_MODEL") == DEFAULT_LLM_FALLBACK_MODEL


def test_readme_uses_only_tracked_local_workflows_and_links() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "make " not in readme.lower()
    assert "docker compose" not in readme.lower()
    assert not (ROOT / "docker-compose.prod.yml").exists()

    local_links = [
        target.split("#", 1)[0]
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", readme)
        if target and not target.startswith(("http://", "https://", "#"))
    ]
    missing = [target for target in local_links if not (ROOT / target).exists()]
    assert missing == []

    for required_path in (
        "main.py",
        "scripts/acceptance.py",
        "tests/evals/eval_harness.py",
        "frontend-react/package.json",
        "Dockerfile",
    ):
        assert (ROOT / required_path).exists()


def test_deployment_uses_one_exact_ci_revision() -> None:
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "github.event.workflow_run.head_sha || github.sha" in workflow
    assert 'SHA="$(git rev-parse HEAD)"' in workflow
    assert "kraken:sha-${{ steps.revision.outputs.sha }}" in workflow
    assert "DEPLOY_SHA: ${{ needs.dockerhub-push.outputs.deploy_sha }}" in workflow
    assert "ref=${DEPLOY_SHA}" in workflow
    assert "RENDER_DEPLOY_HOOK_URL is not configured" in workflow
    assert "Render deployment request failed" in workflow
    assert "autoDeploy: false" in blueprint
    assert "- key: GATEWAY_API_KEYS\n        sync: false" in blueprint


def test_retired_public_contracts_are_absent_from_active_repository() -> None:
    roots = (
        ROOT / "src",
        ROOT / "scripts",
        ROOT / "frontend-react/src",
        ROOT / "frontend-react/public",
        ROOT / "docs",
    )
    files = [
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".ts", ".tsx", ".md", ".txt"}
    ]
    files.extend((ROOT / name) for name in ("README.md", ".env.example", "render.yaml"))
    retired = ("/v1/demo", "demo_session", "demo mode", "demo_*", "simulated")
    violations: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for term in retired:
            if term in text:
                violations.append(f"{path.relative_to(ROOT)}: {term}")
    assert violations == []
