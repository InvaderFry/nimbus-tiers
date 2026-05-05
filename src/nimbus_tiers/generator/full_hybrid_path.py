"""Path C: Full Hybrid setup (Ollama + TabbyAPI/ExLlamaV3 + cloud subscriptions).

This is the only fully-implemented setup path in the current iteration. The file
list mirrors the architecture doc's "What gets copied into the new project"
section.
"""

from __future__ import annotations

import os
from pathlib import Path

from nimbus_tiers.generator.setup_path import SetupPath, TemplateSpec


class FullHybridPath(SetupPath):
    name = "full-hybrid"

    def __init__(
        self,
        stack: str = "java-maven",
        package_name: str = "app",
        class_name: str = "App",
    ) -> None:
        self.stack = stack
        self.package_name = package_name
        self.class_name = class_name

    def template_files(self) -> list[TemplateSpec]:
        common: list[tuple[str, str]] = [
            ("CONTEXT.md", "CONTEXT.md"),
            ("VERIFY.md", "VERIFY.md"),
            ("CLAUDE.md", "CLAUDE.md"),
            ("NIMBUS_GUIDE.md", "NIMBUS_GUIDE.md"),
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
        )

    def _stack_template_files(self) -> list[TemplateSpec]:
        s = self.stack
        pkg = self.package_name

        if s in ("java-maven", "java-gradle"):
            main_pkg = f"src/main/java/com/example/{pkg}"
            test_pkg = f"src/test/java/com/example/{pkg}"
            java_common = [
                TemplateSpec(
                    Path(f"stacks/{s}/Application.java"),
                    Path(f"{main_pkg}/Application.java"),
                ),
                TemplateSpec(
                    Path(f"stacks/{s}/ApplicationTest.java"),
                    Path(f"{test_pkg}/ApplicationTest.java"),
                ),
                TemplateSpec(
                    Path(f"stacks/{s}/application.properties"),
                    Path("src/main/resources/application.properties"),
                ),
            ]
            if s == "java-maven":
                return java_common + [
                    TemplateSpec(Path("stacks/java-maven/pom.xml"), Path("pom.xml")),
                    TemplateSpec(Path("stacks/java-maven/mvnw"), Path("mvnw")),
                ]
            else:
                return java_common + [
                    TemplateSpec(Path("stacks/java-gradle/build.gradle"), Path("build.gradle")),
                    TemplateSpec(Path("stacks/java-gradle/settings.gradle"), Path("settings.gradle")),
                    TemplateSpec(Path("stacks/java-gradle/gradlew"), Path("gradlew")),
                ]

        if s == "python":
            return [
                TemplateSpec(Path("stacks/python/main.py"), Path("main.py")),
                TemplateSpec(Path("stacks/python/requirements.txt"), Path("requirements.txt")),
                TemplateSpec(Path("stacks/python/test_main.py"), Path("tests/test_main.py")),
            ]

        if s == "node":
            return [
                TemplateSpec(Path("stacks/node/package.json"), Path("package.json")),
                TemplateSpec(Path("stacks/node/index.js"), Path("index.js")),
                TemplateSpec(Path("stacks/node/index.test.js"), Path("index.test.js")),
            ]

        return []

    def post_copy_hooks(self, project_root: Path) -> None:
        executables = {
            "java-maven": ["mvnw"],
            "java-gradle": ["gradlew"],
        }
        for name in executables.get(self.stack, []):
            script = project_root / name
            if script.exists():
                script.chmod(script.stat().st_mode | 0o755)


__all__ = ["FullHybridPath"]
