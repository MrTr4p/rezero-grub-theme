#!/usr/bin/env python3
"""Install/remove the theme with backups and rollback. Never installs GRUB itself."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parents[1]
BEGIN = "# BEGIN REZERO LAVENDER (managed by rezero-grub-theme)"
END = "# END REZERO LAVENDER"
BLOCK = re.compile(r"(?m)^" + re.escape(BEGIN) + r"\n.*?^" + re.escape(END) + r"\n?", re.S)
RESOLUTIONS = {"1080p": "1920x1080,1600x900,1366x768,1024x768,auto",
               "1440p": "2560x1440,1920x1080,auto", "compact": "1366x768,1280x720,1024x768,auto"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".rezero-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def settings(profile, timeout, boot_dir):
    return f'''{BEGIN}
# Previous settings above are retained for uninstall.
GRUB_THEME="{boot_dir}/themes/rezero-lavender/theme.txt"
GRUB_GFXMODE="{RESOLUTIONS[profile]}"
GRUB_TIMEOUT_STYLE=menu
GRUB_TIMEOUT={timeout}
# GRUB_TERMINAL overrides GRUB_TERMINAL_OUTPUT when nonempty.
GRUB_TERMINAL=""
GRUB_TERMINAL_OUTPUT=gfxterm
{END}
'''


def remove_block(text):
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise RuntimeError("Managed settings were edited or duplicated; inspect /etc/default/grub first.")
    return BLOCK.sub("", text)


def check_assets():
    required = ["theme.txt", "background.png", "select_c.png", "select_w.png", "select_e.png"]
    for name in required:
        if not (BASE / "theme" / name).is_file():
            raise RuntimeError(f"Missing theme asset: {name}. Download the complete repository.")
    if not list((BASE / "theme").glob("*.pf2")):
        raise RuntimeError("Bundled GRUB fonts are missing.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "uninstall"])
    parser.add_argument("--profile", choices=RESOLUTIONS, default="1080p")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true", help="Print the exact changes without writing files")
    parser.add_argument("--root", type=Path, default=Path("/"), help="Offline staging root; never regenerates host GRUB")
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 300:
        parser.error("--timeout must be between 1 and 300 seconds")
    root = args.root.resolve()
    staging = root != Path("/")
    defaults = root / "etc/default/grub"
    state = root / "var/lib/rezero-grub-theme"
    manifest = state / "installation.json"
    if not defaults.is_file():
        raise RuntimeError(f"{defaults} is missing. This installer requires an existing GRUB setup.")
    if defaults.is_symlink():
        raise RuntimeError("/etc/default/grub is a symlink; install the theme manually using the README.")
    if (root / "boot/grub/grub.cfg").is_file():
        boot_dir = "/boot/grub"
    elif (root / "boot/grub2/grub.cfg").is_file():
        boot_dir = "/boot/grub2"
    else:
        raise RuntimeError("No existing /boot/grub/grub.cfg or /boot/grub2/grub.cfg. Do not use this on systemd-boot.")
    config = root / boot_dir.lstrip("/") / "grub.cfg"
    if config.is_symlink():
        raise RuntimeError("grub.cfg is a symlink; install the theme manually using the README.")
    target = config.parent / "themes/rezero-lavender"
    if target.is_symlink():
        raise RuntimeError("Theme directory is a symlink; refusing to replace it.")
    current = defaults.read_text()
    clean = remove_block(current)
    restore_text = clean
    if manifest.exists():
        previous = json.loads(manifest.read_text())
        if digest(defaults) == previous.get("defaults_hash"):
            restore_text = (state / previous["backup"] / "grub.restore").read_text()
    if args.action == "install":
        check_assets()
        if target.exists() and not manifest.exists():
            raise RuntimeError(f"{target} already exists without an installation record. Move it aside first.")
        planned = restore_text + ("" if restore_text.endswith("\n") else "\n") + settings(args.profile, args.timeout, boot_dir)
    else:
        if not manifest.exists():
            raise RuntimeError("No installation record found. Nothing was removed.")
        # Restore the exact original bytes when the user hasn't edited settings.
        planned = restore_text
    if args.dry_run:
        print(f"{args.action.upper()} {target}\nSettings: {defaults}\nGRUB config: {config}")
        print(f"Profile: {args.profile}; timeout: {args.timeout}s" if args.action == "install" else "Restore previous settings")
        if args.action == "install":
            print(settings(args.profile, args.timeout, boot_dir))
        print("No files changed. " + ("Offline staging; host commands disabled." if staging else "A real run validates a new grub.cfg before replacing it."))
        return
    if not staging and os.geteuid() != 0:
        raise RuntimeError("Run with sudo, or use --dry-run to inspect without root.")
    generator = None
    if not staging:
        generator = shutil.which("grub-mkconfig") or shutil.which("grub2-mkconfig")
        checker = shutil.which("grub-script-check") or shutil.which("grub2-script-check")
        if not generator or not checker:
            raise RuntimeError("Install your distribution's GRUB tools first (Arch: sudo pacman -S grub).")
        # A later drop-in could undo the managed settings. Do not silently claim success.
        for file in (root / "etc/default/grub.d").glob("*.cfg"):
            if re.search(r"(?m)^\s*(?:export\s+)?GRUB_(?:THEME|GFXMODE|TIMEOUT(?:_STYLE)?|TERMINAL(?:_OUTPUT)?)=", file.read_text()):
                raise RuntimeError(f"Conflicting settings in {file}. Remove those overrides or follow the manual installation steps.")
    candidate = config.with_name("grub.cfg.rezero-new")
    if candidate.exists():
        raise RuntimeError(f"{candidate} exists; move it aside and retry.")
    state.mkdir(parents=True, exist_ok=True)
    with (state / "lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = datetime.now(timezone.utc).strftime("backup-%Y%m%dT%H%M%S-%fZ")
        backup = state / stamp
        backup.mkdir()
        shutil.copy2(defaults, backup / "grub.defaults")
        (backup / "grub.restore").write_text(restore_text)
        shutil.copy2(config, backup / "grub.cfg")
        old_record = manifest.read_bytes() if manifest.exists() else None
        if target.exists():
            shutil.copytree(target, backup / "theme")
        if old_record:
            (backup / "installation.json").write_bytes(old_record)
        mode = defaults.stat().st_mode & 0o777
        try:
            if args.action == "install":
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(BASE / "theme", target)
                shutil.copyfile(target / f"theme-{args.profile}.txt", target / "theme.txt")
            atomic_write(defaults, planned.encode(), mode)
            if not staging:
                subprocess.run([generator, "-o", str(candidate)], check=True)
                subprocess.run([checker, str(candidate)], check=True)
                generated = candidate.read_text()
                if args.action == "install" and f"{boot_dir}/themes/rezero-lavender/theme.txt" not in generated and "/themes/rezero-lavender/theme.txt" not in generated:
                    raise RuntimeError("Generated config did not load the theme. Existing config has been kept.")
                if "menuentry " not in generated:
                    raise RuntimeError("Generated config has no menu entries. Existing config has been kept.")
                os.chmod(candidate, config.stat().st_mode & 0o777)
                os.replace(candidate, config)
            if args.action == "install":
                atomic_write(manifest, json.dumps({"backup": stamp,
                             "defaults_hash": digest(defaults), "profile": args.profile}, indent=2).encode())
            else:
                if target.exists():
                    shutil.rmtree(target)
                manifest.unlink()
        except BaseException:
            shutil.copy2(backup / "grub.defaults", defaults)
            shutil.copy2(backup / "grub.cfg", config)
            if target.exists():
                shutil.rmtree(target)
            if (backup / "theme").exists():
                shutil.copytree(backup / "theme", target)
            if old_record:
                atomic_write(manifest, old_record)
            else:
                manifest.unlink(missing_ok=True)
            raise
        finally:
            candidate.unlink(missing_ok=True)
        print(f"{args.action.capitalize()} complete. Backup: {backup}")
        if staging:
            print("Offline staging only; host boot files and boot commands were not touched.")
        else:
            print("GRUB configuration validated and updated. Reboot when ready.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
