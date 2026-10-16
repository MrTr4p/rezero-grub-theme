"""Exercise the shipped install/uninstall entry points in disposable roots."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("manage", BASE / "scripts/manage.py")
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.defaults = self.root / "etc/default/grub"
        self.defaults.parent.mkdir(parents=True)
        self.original = b'# Existing settings\nGRUB_DEFAULT=saved\nGRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\nGRUB_TERMINAL=console\nGRUB_THEME="/old/theme.txt"'
        self.defaults.write_bytes(self.original)
        self.defaults.chmod(0o640)
        self.config = self.root / "boot/grub/grub.cfg"
        self.config.parent.mkdir(parents=True)
        self.config.write_text("# Existing generated config\nmenuentry 'Arch Linux' { true; }\n")
        self.target = self.config.parent / "themes/rezero-lavender"

    def command(self, script, *args, success=True):
        result = subprocess.run([str(BASE / script), "--root", str(self.root), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_install_uninstall_preserves_exact_original_and_boot_entries(self):
        config_before = self.config.read_bytes()
        self.command("install.sh")
        self.assertTrue((self.target / "background.png").is_file())
        self.assertIn('GRUB_TERMINAL_OUTPUT=gfxterm', self.defaults.read_text())
        self.assertEqual(self.defaults.stat().st_mode & 0o777, 0o640)
        self.assertEqual(config_before, self.config.read_bytes())
        self.command("uninstall.sh")
        self.assertEqual(self.original, self.defaults.read_bytes())
        self.assertFalse(self.target.exists())
        self.assertEqual(config_before, self.config.read_bytes())

    def test_repeat_install_and_profile_change_keep_one_block(self):
        self.command("install.sh")
        self.command("install.sh", "--profile", "compact", "--timeout", "15")
        self.assertEqual(self.defaults.read_text().count(manage.BEGIN), 1)
        self.assertIn("GRUB_TIMEOUT=15", self.defaults.read_text())
        self.assertIn("Regular 17", (self.target / "theme.txt").read_text())
        self.command("uninstall.sh")
        self.assertEqual(self.original, self.defaults.read_bytes())

    def test_user_edits_survive_uninstall_and_reinstall(self):
        self.command("install.sh")
        self.defaults.write_text(self.defaults.read_text() + '\nGRUB_DISABLE_OS_PROBER=false\n')
        self.command("install.sh", "--profile", "1440p")
        self.command("uninstall.sh")
        self.assertIn("GRUB_DISABLE_OS_PROBER=false", self.defaults.read_text())
        self.assertNotIn(manage.BEGIN, self.defaults.read_text())

    def test_dry_run_writes_nothing(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.command("install.sh", "--dry-run")
        after = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_rejects_non_grub_system_and_bad_timeout(self):
        self.command("install.sh", "--timeout", "0", success=False)
        self.config.unlink()
        self.command("install.sh", success=False)
        self.assertEqual(self.original, self.defaults.read_bytes())

    def test_existing_theme_without_record_is_preserved(self):
        self.target.mkdir(parents=True)
        (self.target / "keep.txt").write_text("original")
        self.command("install.sh", success=False)
        self.assertEqual((self.target / "keep.txt").read_text(), "original")

    def test_symlinked_grub_config_is_preserved(self):
        actual = self.config.with_name("custom.cfg")
        self.config.rename(actual)
        self.config.symlink_to(actual)
        self.command("install.sh", success=False)
        self.assertTrue(self.config.is_symlink())
        self.assertIn("Arch Linux", actual.read_text())

    def test_partial_failure_rolls_back_files_and_theme(self):
        write = manage.atomic_write
        def fail_manifest(path, data, *args):
            if path.name == "installation.json":
                raise OSError("simulated full disk")
            return write(path, data, *args)
        with patch.object(manage, "atomic_write", side_effect=fail_manifest):
            with self.assertRaises(OSError):
                manage.main(["install", "--root", str(self.root)])
        self.assertEqual(self.original, self.defaults.read_bytes())
        self.assertFalse(self.target.exists())
        self.assertIn("Arch Linux", self.config.read_text())

    def test_preexisting_candidate_is_not_deleted(self):
        candidate = self.config.with_name("grub.cfg.rezero-new")
        candidate.write_text("keep this")
        self.command("install.sh", success=False)
        self.assertEqual(candidate.read_text(), "keep this")
        self.assertEqual(self.original, self.defaults.read_bytes())


if __name__ == "__main__":
    unittest.main()
