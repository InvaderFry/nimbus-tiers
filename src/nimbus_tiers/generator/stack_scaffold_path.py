"""Shared scaffold for all setup paths.

Every path (Cloud-Only, Light Local, Full Hybrid) copies the same project
skeleton and stack starter files; they differ only in the Aider executor
config (``paths/<name>/.aider.conf.yml``) and any path-specific extra docs.
Subclasses set ``name`` and, if needed, override ``extra_docs()``.
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


class StackScaffoldPath(SetupPath):
    """Base scaffold shared by all setup paths. Not registered as a path itself."""

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
            ("PHASE1_SPEC.md", "PHASE1_SPEC.md"),
            ("phase2.sh", "phase2.sh"),
            ("phase2-lib.sh", "phase2-lib.sh"),
            (f"paths/{self.name}/.aider.conf.yml", ".aider.conf.yml"),
            (".aiderignore", ".aiderignore"),
            (".gitignore", ".gitignore"),
            ("plans/README.md", "plans/README.md"),
            ("logs/ai-routing.csv", "logs/ai-routing.csv"),
            ("docs/architecture.md", "docs/architecture.md"),
        ]
        return (
            [TemplateSpec(Path(src), Path(dest)) for src, dest in common]
            + self.extra_docs()
            + self._stack_template_files()
            + [
                TemplateSpec(
                    Path(f"stacks/{self.stack}/PHASE1_VERIFY.md"),
                    Path("PHASE1_VERIFY_HELPER.md"),
                )
            ]
        )

    def extra_docs(self) -> list[TemplateSpec]:
        """Path-specific documentation beyond the shared skeleton. Default: none."""
        return []

    def _stack_template_files(self) -> list[TemplateSpec]:
        stack = self.stack
        pkg = self.package_name

        if stack in ("java-maven", "java-gradle"):
            main_pkg = f"src/main/java/com/example/{pkg}"
            test_pkg = f"src/test/java/com/example/{pkg}"
            cls = self.class_name
            java_common = [
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
                return java_common + [
                    TemplateSpec(Path("stacks/java-maven/pom.xml"), Path("pom.xml")),
                    TemplateSpec(Path("stacks/java-maven/mvnw"), Path("mvnw")),
                    TemplateSpec(
                        Path(
                            "stacks/java-maven/mockito-extensions/org.mockito.plugins.MockMaker"
                        ),
                        Path(
                            "src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker"
                        ),
                    ),
                ]
            else:
                return java_common + [
                    TemplateSpec(Path("stacks/java-gradle/build.gradle"), Path("build.gradle")),
                    TemplateSpec(Path("stacks/java-gradle/settings.gradle"), Path("settings.gradle")),
                    TemplateSpec(Path("stacks/java-gradle/gradlew"), Path("gradlew")),
                    TemplateSpec(
                        Path(
                            "stacks/java-gradle/mockito-extensions/org.mockito.plugins.MockMaker"
                        ),
                        Path(
                            "src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker"
                        ),
                    ),
                ]

        if stack == "python":
            return [
                TemplateSpec(Path("stacks/python/main.py"), Path("main.py")),
                TemplateSpec(Path("stacks/python/requirements.txt"), Path("requirements.txt")),
                TemplateSpec(Path("stacks/python/test_main.py"), Path("tests/test_main.py")),
            ]

        if stack == "node":
            return [
                TemplateSpec(Path("stacks/node/package.json"), Path("package.json")),
                TemplateSpec(Path("stacks/node/index.js"), Path("index.js")),
                TemplateSpec(Path("stacks/node/index.test.js"), Path("index.test.js")),
            ]

        raise ValueError(
            f"Unsupported stack: {stack!r}. Supported stacks: {sorted(_SUPPORTED_STACKS)}"
        )

    def post_copy_hooks(self, project_root: Path) -> None:
        for script_name in _EXECUTABLE_SCRIPTS.get(self.stack, []):
            script = project_root / script_name
            if script.exists():
                script.chmod(script.stat().st_mode | 0o755)


__all__ = ["StackScaffoldPath"]
