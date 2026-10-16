# Recovery

From a working Linux session, run `sudo ./uninstall.sh` from the cloned repo.
The installer never changes the EFI/MBR bootloader or firmware boot entries.

If a graphics issue prevents you reaching Linux, use an Arch live USB and the
usual mount + `arch-chroot` procedure for your installation. Mount any separate
`/boot` partition too. Within the installed system:

1. Locate the backup that predates the change:

   ```bash
   ls -lt /var/lib/rezero-grub-theme/
   ```

2. Set `backup` to the exact directory you selected. Replace the example suffix
   with an actual name from the listing:

   ```bash
   backup=/var/lib/rezero-grub-theme/backup-YYYYMMDDTHHMMSS-ffffffZ
   ls "$backup/grub.defaults" "$backup/grub.cfg"
   ```

3. Restore its defaults and generated configuration:

   ```bash
   cp -a "$backup/grub.defaults" /etc/default/grub
   cp -a "$backup/grub.cfg" /boot/grub/grub.cfg
   grub-script-check /boot/grub/grub.cfg
   ```

   If this backup still uses Re:Zero because it came from a later reinstall,
   choose the earliest backup from before the first installation instead.

4. Exit the chroot, unmount normally and reboot. The restored configuration is
   the one that existed before that attempt. Keep backups until the system has
   booted successfully.

This guide assumes the standard Arch `/boot/grub` layout. For `/boot/grub2`, use
that path and the distribution's `grub2-script-check` command instead.
