from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class UpScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.tmpdir.name) / "project"
        self.scripts_dir = self.project_dir / "scripts"
        self.fake_bin = Path(self.tmpdir.name) / "bin"

        self.scripts_dir.mkdir(parents=True)
        self.fake_bin.mkdir()

        shutil.copy2(ROOT_DIR / "scripts" / "up.py", self.scripts_dir / "up.py")
        shutil.copy2(ROOT_DIR / "scripts" / "up.sh", self.scripts_dir / "up.sh")
        shutil.copy2(ROOT_DIR / "scripts" / "deploy_lib.py", self.scripts_dir / "deploy_lib.py")

        self.write_file(
            self.project_dir / ".env.example",
            """
            NAPCAT_UID=11111
            NAPCAT_GID=22222
            ASTRBOT_IMAGE=default-image
            """,
        )
        self.write_file(
            self.project_dir / ".env.domestic.example",
            """
            NAPCAT_UID=11111
            NAPCAT_GID=22222
            ASTRBOT_IMAGE=domestic-image
            """,
        )
        self.write_file(self.project_dir / "compose.yaml", "services: {}\n")
        self.write_file(
            self.fake_bin / "docker",
            """
            #!/usr/bin/env bash
            set -euo pipefail
            printf '%s\n' "$@" > "${FAKE_DOCKER_LOG:?}"
            """,
        )
        os.chmod(self.fake_bin / "docker", 0o755)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")

    def run_script(self, *args: str, expect_success: bool = True, path_override: str | None = None) -> subprocess.CompletedProcess[str]:
        docker_log = self.project_dir / "docker.log"
        env = os.environ.copy()
        if path_override is None:
            env["PATH"] = f"{self.fake_bin}:{env['PATH']}"
        else:
            env["PATH"] = path_override
        env["FAKE_DOCKER_LOG"] = str(docker_log)
        result = subprocess.run(
            [sys.executable, str(self.project_dir / "scripts" / "up.py"), *args],
            cwd=self.project_dir,
            env=env,
            text=True,
            capture_output=True,
        )
        if expect_success and result.returncode != 0:
            self.fail(f"script failed: {result.stderr}")
        return result

    def test_initializes_env_and_runs_compose(self) -> None:
        result = self.run_script()

        env_text = (self.project_dir / ".env").read_text(encoding="utf-8")
        docker_text = (self.project_dir / "docker.log").read_text(encoding="utf-8")

        self.assertIn("NAPCAT_UID=", env_text)
        self.assertIn("NAPCAT_GID=", env_text)
        self.assertIn(f"NAPCAT_UID={os.getuid()}", env_text)
        self.assertIn(f"NAPCAT_GID={os.getgid()}", env_text)
        self.assertNotIn("NAPCAT_UID=11111", env_text)
        self.assertNotIn("NAPCAT_GID=22222", env_text)
        self.assertIn("ASTRBOT_IMAGE=default-image", env_text)
        self.assertEqual(docker_text, "compose\nup\n-d\n")
        self.assertTrue((self.project_dir / "data").is_dir())
        self.assertTrue((self.project_dir / "napcat" / "config").is_dir())
        self.assertTrue((self.project_dir / "napcat" / "qq").is_dir())
        self.assertIn("服务已启动。", result.stdout)

    def test_uses_domestic_template_when_requested(self) -> None:
        result = self.run_script("--domestic")

        env_text = (self.project_dir / ".env").read_text(encoding="utf-8")

        self.assertIn("ASTRBOT_IMAGE=domestic-image", env_text)
        self.assertIn("服务已启动。", result.stdout)

    def test_preserves_existing_env_file(self) -> None:
        self.write_file(
            self.project_dir / ".env",
            """
            NAPCAT_UID=42
            NAPCAT_GID=84
            CUSTOM=keep-me
            """,
        )

        self.run_script()

        env_text = (self.project_dir / ".env").read_text(encoding="utf-8")
        self.assertIn("NAPCAT_UID=42", env_text)
        self.assertIn("NAPCAT_GID=84", env_text)
        self.assertIn("CUSTOM=keep-me", env_text)

    def test_fails_when_docker_is_missing(self) -> None:
        empty_bin = Path(self.tmpdir.name) / "empty-bin"
        empty_bin.mkdir()

        result = self.run_script(expect_success=False, path_override=str(empty_bin))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("缺少依赖命令：docker", result.stderr)


if __name__ == "__main__":
    unittest.main()
