"""Path C: Full Hybrid setup (Ollama + TabbyAPI/ExLlamaV3 + cloud subscriptions).

This is the only fully-implemented setup path in the current iteration. The file
list mirrors the architecture doc's "What gets copied into the new project"
section.
"""

from __future__ import annotations

from pathlib import Path

from nimbus_tiers.generator.setup_path import SetupPath, TemplateSpec

_SUPPORTED_STACKS = frozenset({"java-maven", "java-gradle", "python", "node"})

_EXECUTABLE_SCRIPTS: dict[str, list[str]] = {
    "java-maven": ["mvnw", "phase2.sh"],
    "java-gradle": ["gradlew", "phase2.sh"],
    "python": ["phase2.sh"],
    "node": ["phase2.sh"],
}

# Simple stacks: files that need no per-project name substitution in paths.
_SIMPLE_STACK_SPECS: dict[str, list[tuple[str, str]]] = {
    "python": [
        ("stacks/python/main.py", "main.py"),
        ("stacks/python/requirements.txt", "requirements.txt"),
        ("stacks/python/test_main.py", "tests/test_main.py"),
    ],
    "node": [
        ("stacks/node/package.json", "package.json"),
        ("stacks/node/index.js", "index.js"),
        ("stacks/node/index.test.js", "index.test.js"),
    ],
}


class FullHybridPath(SetupPath):
    name = "full-hybrid"

    def __init__(
        self,
        stack: str = "java-maven",
        package_name: str = "app",
        class_name: str = "App",
    ) -> None:
        if stack not in _SUPPORTED_STACKS:
            raise ValueError(
                f"Unsupported stack: {stack!r}. Supported stacks: {sorted(_SUPPORTED_STACKS)}"
            )
        self.stack = stack
        self.package_name = package_name
        self.class_name = class_name

    def template_files(self) -> list[TemplateSpec]:
        common: list[tuple[str, str]] = [
            ("CONTEXT.md", "CONTEXT.md"),
            ("VERIFY.md", "VERIFY.md"),
            ("CLAUDE.md", "CLAUDE.md"),
            ("NIMBUS_GUIDE.md", "NIMBUS_GUIDE.md"),
            ("PHASE1_SPEC.md", "PHASE1_SPEC.md"),
            ("phase2.sh", "phase2.sh"),
            (".aider.conf.yml", ".aider.conf.yml"),
            (".aiderignore", ".aiderignore"),
            (".gitignore", ".gitignore"),
            ("plans/README.md", "plans/README.md"),
            ("logs/ai-routing.csv", "logs/ai-routing.csv"),
            ("docs/architecture.md", "docs/architecture.md"),
        ]
        return (
            [TemplateSpec(Path(src), Path(dest)) for src, dest in common]
            + self._stack_template_files()
            + [
                TemplateSpec(
                    Path(f"stacks/{self.stack}/PHASE1_VERIFY.md"),
                    Path("PHASE1_VERIFY_HELPER.md"),
                )
            ]
        )

    def _stack_template_files(self) -> list[TemplateSpec]:
        if self.stack in ("java-maven", "java-gradle"):
            return self._java_specs()
        specs = _SIMPLE_STACK_SPECS[self.stack]
        return [TemplateSpec(Path(s), Path(d)) for s, d in specs]

    def _java_specs(self) -> list[TemplateSpec]:
        stack = self.stack
        pkg = self.package_name
        cls = self.class_name
        main_pkg = f"src/main/java/com/example/{pkg}"
        test_pkg = f"src/test/java/com/example/{pkg}"
        common = [
            TemplateSpec(
                Path(f"stacks/{stack}/Application.java"),
                Path(f"{main_pkg}/{cls}Application.java"),
            ),
            TemplateSpec(
                Path(f"stacks/{stack}/ApplicationTest.java"),
                Path(f"{test_pkg}/{cls}ApplicationTest.java"),
            ),
            TemplateSpec(
                Path(f"stacks/{stack}/application.properties"),
                Path("src/main/resources/application.properties"),
            ),
        ]
        if stack == "java-maven":
            return common + [
                TemplateSpec(Path("stacks/java-maven/pom.xml"), Path("pom.xml")),
                TemplateSpec(Path("stacks/java-maven/mvnw"), Path("mvnw")),
            ]
        return common + [
            TemplateSpec(Path("stacks/java-gradle/build.gradle"), Path("build.gradle")),
            TemplateSpec(Path("stacks/java-gradle/settings.gradle"), Path("settings.gradle")),
            TemplateSpec(Path("stacks/java-gradle/gradlew"), Path("gradlew")),
        ]

    def post_copy_hooks(self, project_root: Path) -> None:
        for script_name in _EXECUTABLE_SCRIPTS.get(self.stack, []):
            script = project_root / script_name
            if script.exists():
                script.chmod(script.stat().st_mode | 0o755)


__all__ = ["FullHybridPath"]
