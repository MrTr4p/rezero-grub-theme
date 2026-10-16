# Test report

Validated on 2026-10-16 using Arch Linux, GRUB 2.14 and QEMU 11.1.1.
The screenshots below are captured from actual GRUB; no web recreation is used.

## Results

| Check | Result |
| --- | --- |
| UEFI, 1920×1080, `1080p` | Passed |
| Legacy BIOS, 1920×1080, `1080p` | Passed |
| UEFI, 2560×1440, `1440p` | Passed |
| UEFI, 1024×768, `compact` | Passed |
| UEFI countdown executes the default entry | Passed |
| 9 installer/restoration unit tests | Passed |
| Real Arch config generation in a filesystem sandbox | Passed |
| Actual generator failure restores prior settings/config/theme | Passed |
| Conflicting drop-in settings refused | Passed |
| Shell and Python syntax | Passed |

Each keyboard VM test checks that the themed selection renders, moves through
entries, opens a submenu, scrolls a 14-entry list, executes the final submenu
entry, returns to the parent, opens the console and editor, and executes another
selected entry. The countdown test waits for the default entry's serial marker.
Tests fail on GRUB errors, missing markers, wrong display dimensions or a missing
selection highlight. Console/editor checks confirm that the menu has closed.

## Installer tests

`python3 -m unittest discover -s tests -v` exercises the actual install/uninstall
entry points using disposable `--root` directories. It covers exact restoration,
mode preservation, existing kernel settings, repeated installation, profile
changes, edits made by the user, dry runs, invalid timeouts, missing GRUB,
preexisting unmanaged themes, symlinked generated configs, write-failure rollback,
and preservation of an existing temporary candidate file.

`python3 scripts/test_arch_install.py` exercises the production root-only path in
a Bubblewrap user namespace with Arch's real `grub-mkconfig`, `00_header`,
`10_linux` and `grub-script-check`. The host root is read-only; only disposable
boot files, defaults and state are writable. It uses a readable Linux kernel and
a dummy initramfs for configuration generation. `grub-probe` returns a fixture
disk topology because physical disks are not exposed to the sandbox. It checks
theme/font discovery, generated Linux entries, drop-in refusal, rollback after an
induced generator error, and uninstall with regenerated Linux entries. Host
defaults/config fingerprints remain unchanged.

To reproduce that Arch-specific test:

```bash
sudo pacman -S --needed bubblewrap
python3 scripts/test_arch_install.py
```

It requires the standard Arch boot files `/boot/vmlinuz-linux` and
`/boot/grub/fonts/unicode.pf2` to be readable. It does not need sudo.

## Screenshots and machine-readable results

- [1080p menu](preview.png)
- [Moved selection](selection.png)
- [Submenu after scrolling to the bottom](scroll.png)
- [1024×768 compact menu](compact.png)
- [1440p menu](1440p.png)
- [Legacy BIOS menu](bios.png)
- [Editor](editor.png)
- [VM result records](test-results/vm-results.json)
- [Arch installation/rollback log](test-results/arch-install.log)

The GitHub Actions [workflow](../.github/workflows/test.yml) repeats the unit
tests and five VM configurations on Ubuntu, with screenshots/logs uploaded as
workflow artifacts. The local tests used KVM; CI uses software emulation.

## Scope

The VM tests verify GRUB theme loading and execution of test menu-entry scripts.
They do not boot a complete Linux or Windows guest. The Arch sandbox verifies
configuration generation and file restoration, using simulated device probing.
The friend's physical hardware, existing dual-boot setup and firmware graphics
modes still determine the real boot experience. No theme was installed on the
author's host, and no host boot configuration was changed for these tests.
