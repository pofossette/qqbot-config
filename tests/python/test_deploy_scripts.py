from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


class DeployScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.tmpdir.name) / "project"
        self.scripts_dir = self.project_dir / "scripts"
        self.fake_bin = Path(self.tmpdir.name) / "bin"
        self.scripts_dir.mkdir(parents=True)
        self.fake_bin.mkdir()

        for path in ("backup.py", "restore.py", "logs.py", "down.py", "manage.py", "deploy_lib.py", "up.py"):
            shutil.copy2(ROOT_DIR / "scripts" / path, self.scripts_dir / path)
        shutil.copy2(ROOT_DIR / "manage.py", self.project_dir / "manage.py")

        self.write_file(self.project_dir / ".env", "EXAMPLE=1\n")
        self.write_file(self.project_dir / "compose.yaml", "services: {}\n")
        self.write_file(self.project_dir / "data" / "demo.txt", "demo\n")
        self.write_file(
            self.fake_bin / "docker",
            """
            #!/usr/bin/env bash
            set -euo pipefail

            if [[ "${1:-}" != "compose" ]]; then
              exit 1
            fi
            shift

            printf '%s\n' "$@" >> "${FAKE_DOCKER_LOG:?}"

            case "${1:-}" in
              ps)
                if [[ "${DOCKER_PS_FAIL:-0}" == "1" ]]; then
                  echo "permission denied" >&2
                  exit 1
                fi
                if [[ "${DOCKER_RUNNING:-0}" == "1" ]]; then
                  printf 'astrbot\nnapcat\n'
                fi
                ;;
              version)
                echo "fake-compose"
                ;;
              logs)
                echo "fake logs"
                ;;
              up|down)
                ;;
            esac
            """,
        )
        os.chmod(self.fake_bin / "docker", 0o755)
        self.write_file(
            self.fake_bin / "tar",
            """
            #!/usr/bin/env bash
            exec /usr/bin/tar "$@"
            """,
        )
        os.chmod(self.fake_bin / "tar", 0o755)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")

    def run_python(self, script: Path, *args: str, stdin: str = "", env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.fake_bin}:{env['PATH']}"
        env["FAKE_DOCKER_LOG"] = str(self.project_dir / "docker.log")
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=self.project_dir,
            env=env,
            text=True,
            input=stdin,
            capture_output=True,
        )

    def test_backup_restore_and_logs_use_python_entries(self) -> None:
        backup_path = self.project_dir / "backup.tar.gz"
        result = self.run_python(self.scripts_dir / "backup.py", str(backup_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("备份已创建", result.stdout)

        with tarfile.open(backup_path, "r:gz") as archive:
            manifest = archive.extractfile("manifest.txt")
            self.assertIsNotNone(manifest)
            manifest_text = manifest.read().decode("utf-8")
        self.assertIn("included_paths=compose.yaml .env data", manifest_text)
        self.assertIn("backup_mode=offline", manifest_text)

        (self.project_dir / "data" / "demo.txt").write_text("changed\n", encoding="utf-8")
        restore_result = self.run_python(
            self.scripts_dir / "restore.py",
            str(backup_path),
            "--force",
            "--only",
            "data",
            "--only",
            "config-files",
        )
        self.assertEqual(restore_result.returncode, 0, restore_result.stderr)
        self.assertIn("备份已恢复", restore_result.stdout)
        self.assertEqual((self.project_dir / "data" / "demo.txt").read_text(encoding="utf-8"), "demo\n")

        logs_result = self.run_python(self.scripts_dir / "logs.py", "--no-follow", "--tail", "10")
        self.assertEqual(logs_result.returncode, 0, logs_result.stderr)
        self.assertIn("正在查看全部服务日志", logs_result.stdout)

    def test_down_and_manage_root_entry(self) -> None:
        down_result = self.run_python(self.scripts_dir / "down.py")
        self.assertEqual(down_result.returncode, 0, down_result.stderr)
        self.assertIn("容器服务已停止。", down_result.stdout)

        manage_result = self.run_python(self.project_dir / "manage.py", stdin="0\n")
        self.assertEqual(manage_result.returncode, 0, manage_result.stderr)
        self.assertIn("QQBot 管理菜单", manage_result.stdout)

    def test_backup_rejects_running_services_without_allow_live(self) -> None:
        result = self.run_python(
            self.scripts_dir / "backup.py",
            str(self.project_dir / "live.tar.gz"),
            env_overrides={"DOCKER_RUNNING": "1"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("检测到以下容器仍在运行", result.stderr)

    def test_restore_requires_manifest(self) -> None:
        bad_archive = self.project_dir / "bad.tar.gz"
        with tarfile.open(bad_archive, "w:gz") as archive:
            archive.add(self.project_dir / "compose.yaml", arcname="compose.yaml")
        result = self.run_python(self.scripts_dir / "restore.py", str(bad_archive), "--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("缺少 manifest.txt", result.stderr)


if __name__ == "__main__":
    unittest.main()
