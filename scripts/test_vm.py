#!/usr/bin/env python3
"""Boot real GRUB in a disposable VM, save screenshots and exercise the keyboard."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from PIL import Image

BASE = Path(__file__).resolve().parents[1]


def run(args):
    work = BASE / "build" / f"{args.firmware}-{args.resolution}" / ("autoboot" if args.autoboot else "keyboard")
    work.mkdir(parents=True, exist_ok=True)
    iso_root = work / "iso"
    theme = iso_root / "boot/grub/themes/rezero-lavender"
    shutil.copytree(BASE / "theme", theme, dirs_exist_ok=True)
    shutil.copyfile(theme / f"theme-{args.profile}.txt", theme / "theme.txt")
    fonts = "\n".join(f"loadfont /boot/grub/themes/rezero-lavender/{p.name}" for p in theme.glob("*.pf2"))
    children = "\n".join(f"  menuentry 'Linux kernel {i:02d} (recovery mode)' {{ echo REZERO_ADVANCED_{i}_OK; sleep 2; }}" for i in range(14))
    config = f'''serial --unit=0 --speed=115200
set default=0
set timeout_style=menu
set timeout={5 if args.autoboot else 90}
insmod all_video
insmod gfxterm
insmod gfxmenu
insmod png
{fonts}
set gfxmode={args.resolution}
set gfxterm_font="DejaVu Serif Regular 16"
terminal_output gfxterm serial
set theme=/boot/grub/themes/rezero-lavender/theme.txt
export theme
echo REZERO_THEME_READY
menuentry 'Arch Linux' {{ echo REZERO_DEFAULT_ENTRY_OK; sleep 10; }}
submenu 'Advanced options for Arch Linux' {{
{children}
}}
menuentry 'Windows Boot Manager' {{ echo REZERO_WINDOWS_ENTRY_OK; sleep 2; }}
menuentry 'UEFI Firmware Settings' {{ echo REZERO_FIRMWARE_ENTRY_OK; sleep 2; }}
'''
    cfg_path = iso_root / "boot/grub/grub.cfg"
    cfg_path.write_text(config)
    subprocess.run(["grub-script-check", str(cfg_path)], check=True)
    env = os.environ.copy()
    if args.tools:
        env["LD_LIBRARY_PATH"] = str(args.tools / "lib") + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    def binary(name):
        return str(args.tools / "bin" / name) if args.tools else name
    iso = work / "preview.iso"
    module_dir = args.modules / ("x86_64-efi" if args.firmware == "uefi" else "i386-pc")
    build = subprocess.run(["grub-mkrescue", "-d", str(module_dir), f"--xorriso={binary('xorriso')}",
                            "-o", str(iso), str(iso_root)], env=env, capture_output=True, text=True)
    (work / "iso-build.log").write_text(build.stdout + build.stderr)
    build.check_returncode()
    # Short sockets avoid AF_UNIX's 108-byte path limit for long checkout paths.
    with tempfile.TemporaryDirectory(prefix="rz-qmp-") as sockdir:
        qmp_path = Path(sockdir) / "qmp.sock"
        serial = work / "serial.log"
        serial.write_text("")
        command = [binary("qemu-system-x86_64"), "-machine", "q35", "-accel", args.accel,
                   "-m", "256", "-vga", "std", "-display", "none", "-nic", "none", "-no-reboot",
                   "-boot", "order=d", "-drive", f"file={iso},media=cdrom,readonly=on",
                   "-serial", f"file:{serial}", "-qmp", f"unix:{qmp_path},server=on,wait=off"]
        if args.tools:
            command.extend(["-L", str(args.tools / "share/qemu")])
        if args.firmware == "uefi":
            firmware = args.ovmf
            if not firmware and args.tools:
                firmware = args.tools / "share/edk2/x64/OVMF.4m.fd"
            if not firmware:
                for path in ("/usr/share/OVMF/OVMF_CODE_4M.fd", "/usr/share/edk2/x64/OVMF.4m.fd"):
                    if Path(path).is_file():
                        firmware = Path(path)
                        break
            if not firmware:
                raise RuntimeError("OVMF not found; pass --ovmf /path/to/firmware.fd")
            # Distribution CODE files omit the variable-store region. Assemble
            # the standard complete ROM for this disposable, stateless VM.
            if "CODE" in firmware.name:
                variables = firmware.with_name(firmware.name.replace("CODE", "VARS"))
                if not variables.is_file():
                    raise RuntimeError(f"OVMF variable store not found: {variables}")
                complete_rom = work / "OVMF.fd"
                complete_rom.write_bytes(variables.read_bytes() + firmware.read_bytes())
                firmware = complete_rom
            command.extend(["-bios", str(firmware)])
        with (work / "qemu.log").open("w") as log:
            vm = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=log)
            try:
                deadline = time.monotonic() + 45
                with socket.socket(socket.AF_UNIX) as sock:
                    sock.settimeout(15)
                    while True:
                        if vm.poll() is not None:
                            raise RuntimeError((work / "qemu.log").read_text())
                        try:
                            sock.connect(str(qmp_path))
                            break
                        except (FileNotFoundError, ConnectionRefusedError):
                            if time.monotonic() > deadline:
                                raise RuntimeError("QEMU did not open its control socket")
                            time.sleep(.1)
                    stream = sock.makefile("rwb", buffering=0)
                    stream.readline()
                    def qmp(name, arguments=None):
                        request = {"execute": name}
                        if arguments:
                            request["arguments"] = arguments
                        stream.write(json.dumps(request).encode() + b"\n")
                        while True:
                            response = json.loads(stream.readline())
                            if "error" in response:
                                raise RuntimeError(response)
                            if "return" in response:
                                return response["return"]
                    qmp("qmp_capabilities")
                    def wait_for(marker, timeout=45):
                        limit = time.monotonic() + timeout
                        while marker not in serial.read_text(errors="replace"):
                            if time.monotonic() > limit:
                                raise RuntimeError(f"GRUB did not report {marker}: {serial.read_text(errors='replace')[-1000:]}")
                            time.sleep(.2)
                    def capture(name, highlight=False, terminal=False):
                        ppm = work / f"{name}.ppm"
                        qmp("screendump", {"filename": str(ppm)})
                        with Image.open(ppm) as im:
                            im.save(work / f"{name}.png")
                            assert im.size == tuple(map(int, args.resolution.split("x"))), im.size
                            if highlight or terminal:
                                count = dict((color, count) for count, color in im.convert("RGB").getcolors(im.width * im.height)).get((115, 87, 178), 0)
                                if highlight:
                                    assert count > 5000, f"GRUB theme/selection did not render ({count} highlight pixels)"
                                if terminal:
                                    assert count < 5000, "Menu stayed visible instead of opening the terminal/editor"
                        ppm.unlink()
                    def key(name):
                        qmp("send-key", {"keys": [{"type": "qcode", "data": name}]})
                        time.sleep(.4)
                    wait_for("REZERO_THEME_READY")
                    if args.autoboot:
                        wait_for("REZERO_DEFAULT_ENTRY_OK")
                        capture("automatic-entry")
                    else:
                        time.sleep(1.5)
                        key("up")  # cancel the countdown before screenshots
                        key("home")
                        capture("menu", True)
                        key("down")
                        capture("selection", True)
                        key("ret")
                        capture("submenu", True)
                        key("end")
                        capture("scroll", True)
                        key("ret")
                        wait_for("REZERO_ADVANCED_13_OK", 10)
                        time.sleep(2.5)
                        key("esc")
                        key("c")
                        capture("console", terminal=True)
                        key("esc")
                        key("home")
                        key("e")
                        capture("editor", terminal=True)
                        key("esc")
                        key("home")
                        key("down")
                        key("down")
                        key("ret")
                        wait_for("REZERO_WINDOWS_ENTRY_OK", 10)
                    logtext = serial.read_text(errors="replace")
                    if "error:" in logtext.lower():
                        raise RuntimeError(logtext[-3000:])
                    qmp("quit")
                    vm.wait(timeout=10)
            finally:
                if vm.poll() is None:
                    vm.terminate()
                    vm.wait(timeout=10)
    result = {"firmware": args.firmware, "resolution": args.resolution, "profile": args.profile,
              "mode": "automatic entry" if args.autoboot else "selection, scrolling, submenu, console, editor, entry execution",
              "status": "passed"}
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    print(f"Screenshots and logs: {work}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolution", default="1920x1080")
    parser.add_argument("--profile", choices=["1080p", "1440p", "compact"], default="1080p")
    parser.add_argument("--firmware", choices=["uefi", "bios"], default="uefi")
    parser.add_argument("--tools", type=Path, help="Optional isolated tool prefix containing bin, lib and share")
    parser.add_argument("--modules", type=Path, default=Path("/usr/lib/grub"))
    parser.add_argument("--ovmf", type=Path)
    parser.add_argument("--accel", choices=["tcg", "kvm"], default="tcg")
    parser.add_argument("--autoboot", action="store_true")
    run(parser.parse_args())
