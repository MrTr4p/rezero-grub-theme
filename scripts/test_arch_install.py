#!/usr/bin/env python3
"""Test privileged installer branches with real Arch GRUB tools in a user namespace.

The root filesystem is read-only. Only a disposable /boot, /etc/default,
/etc/grub.d and /var/lib/rezero-grub-theme are writable. Device probing is
stubbed because the sandbox deliberately has no physical disks.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

BASE = Path(__file__).resolve().parents[1]
WORK = BASE / "build/arch-install"


def main():
    if not shutil.which("bwrap") or not Path("/usr/bin/grub-mkconfig").exists():
        raise RuntimeError("Run on Arch with grub and bubblewrap installed")
    if WORK.exists():
        shutil.rmtree(WORK)
    for folder in ("boot/grub/fonts", "defaults", "grub.d", "state"):
        (WORK / folder).mkdir(parents=True)
    defaults = WORK / "defaults/grub"
    original = '# Test Arch setup\nGRUB_DEFAULT=0\nGRUB_TIMEOUT=5\nGRUB_DISTRIBUTOR="Arch"\nGRUB_CMDLINE_LINUX_DEFAULT="quiet"\n'
    defaults.write_text(original)
    config = WORK / "boot/grub/grub.cfg"
    config.write_text("menuentry 'Original fixture' { true; }\n")
    original_config = config.read_bytes()
    for name in ("00_header", "10_linux"):
        shutil.copy2(Path("/etc/grub.d") / name, WORK / "grub.d" / name)
    shutil.copy2("/boot/grub/fonts/unicode.pf2", WORK / "boot/grub/fonts/unicode.pf2")
    shutil.copy2("/boot/vmlinuz-linux", WORK / "boot/vmlinuz-linux")
    # An initramfs placeholder is only used by config generation; no OS is booted.
    (WORK / "boot/initramfs-linux.img").write_bytes(b"fixture")
    probe = WORK / "grub-probe"
    probe.write_text('''#!/usr/bin/env python3
import sys
args = sys.argv[1:]
target = None
for i, arg in enumerate(args):
    if arg.startswith('--target='): target = arg.split('=', 1)[1]
    if arg in ('-t', '--target'): target = args[i+1]
values = {'device': '/dev/sda1', 'fs': 'ext2', 'fs_uuid': '11111111-2222-3333-4444-555555555555',
          'partuuid': '11111111-2222-3333-4444-555555555555', 'drive': '(hd0,gpt1)',
          'partmap': 'gpt', 'abstraction': '', 'compatibility_hint': 'hd0,gpt1',
          'hints_string': '--hint-bios=hd0,gpt1 --hint-efi=hd0,gpt1', 'cryptodisk_uuid': ''}
if target not in values: raise SystemExit('Unhandled test probe: ' + str(args))
print(values[target])
''')
    probe.chmod(0o755)
    # These fingerprints ensure the test cannot silently change the host setup.
    host_files = [Path("/etc/default/grub"), Path("/boot/grub/grub.cfg")]
    def fingerprint(p):
        st = p.stat()
        return (st.st_ino, st.st_size, st.st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest() if os.access(p, os.R_OK) else None)
    before = {str(p): fingerprint(p) for p in host_files}
    sandbox = ["bwrap", "--unshare-all", "--die-with-parent", "--uid", "0", "--gid", "0",
               "--ro-bind", "/", "/", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
               "--bind", str(WORK / "boot"), "/boot",
               "--bind", str(WORK / "defaults"), "/etc/default",
               "--bind", str(WORK / "grub.d"), "/etc/grub.d",
               "--tmpfs", "/var/lib", "--bind", str(WORK / "state"), "/var/lib/rezero-grub-theme",
               "--ro-bind", str(probe), "/usr/bin/grub-probe"]
    def invoke(script, *args, success=True):
        result = subprocess.run([*sandbox, str(BASE / script), *args], capture_output=True, text=True)
        with (WORK / "test.log").open("a") as log:
            log.write(result.stdout + result.stderr)
        assert (result.returncode == 0) == success, result.stdout + result.stderr
    invoke("install.sh")
    installed = config.read_text()
    assert "themes/rezero-lavender/theme.txt" in installed
    assert "menuentry 'Arch" in installed
    assert "linux" in installed and "initrd" in installed
    assert len(list((WORK / "boot/grub/themes/rezero-lavender").glob("*.pf2"))) > 5
    subprocess.run(["grub-script-check", str(config)], check=True)
    shutil.copy2(config, WORK / "installed-grub.cfg")
    # Refuse a late drop-in that would override the theme.
    (WORK / "defaults/grub.d").mkdir()
    conflict = WORK / "defaults/grub.d/90-conflict.cfg"
    conflict.write_text('GRUB_THEME="/other/theme.txt"\n')
    invoke("install.sh", success=False)
    assert config.read_text() == installed
    conflict.unlink()
    # Force the actual grub-mkconfig to fail after settings/assets are changed.
    broken = WORK / "grub.d/09-simulated-failure"
    broken.write_text("#!/bin/sh\nexit 42\n")
    broken.chmod(0o755)
    saved_defaults = defaults.read_bytes()
    saved_theme = (WORK / "boot/grub/themes/rezero-lavender/theme.txt").read_bytes()
    invoke("install.sh", "--profile", "compact", success=False)
    assert defaults.read_bytes() == saved_defaults
    assert config.read_text() == installed
    assert (WORK / "boot/grub/themes/rezero-lavender/theme.txt").read_bytes() == saved_theme
    broken.unlink()
    invoke("uninstall.sh")
    assert defaults.read_text() == original
    assert "themes/rezero-lavender/theme.txt" not in config.read_text()
    assert "menuentry 'Arch" in config.read_text()
    assert not (WORK / "boot/grub/themes/rezero-lavender").exists()
    assert config.read_bytes() != original_config  # regenerated with real Arch entries
    after = {str(p): fingerprint(p) for p in host_files}
    assert after == before, "Host GRUB files changed"
    print("PASS: real Arch grub-mkconfig + grub-script-check, install, override refusal, failure rollback, uninstall; host files unchanged")
    print(f"Logs and generated config: {WORK}")


if __name__ == "__main__":
    main()
