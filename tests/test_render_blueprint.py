from pathlib import Path


def test_render_prompts_for_setup_key_and_three_github_values():
    blueprint = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(encoding="utf-8")
    prompted = []
    lines = blueprint.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "sync: false":
            previous = lines[index - 1].strip()
            assert previous.startswith("- key: ")
            prompted.append(previous.removeprefix("- key: "))
    assert prompted == ["VAULT_SETUP_KEY", "GITHUB_TOKEN", "GITHUB_OWNER", "GITHUB_REPO"]
    assert "generateValue: true" in blueprint
    assert "APP_PASSWORD" not in blueprint
    assert 'autoDeployTrigger: "off"' in blueprint
