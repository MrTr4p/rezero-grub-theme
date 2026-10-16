# Credits

The visual reference was provided by the requester: pale lavender Re:Zero artwork,
butterflies, fractured glass, Japanese lettering and a left-aligned GRUB menu.
The original artist/theme author was not identified in the supplied screenshot.

`assets/background.png` was derived from that reference using OpenAI's built-in
image generation tool to remove the sample menu overlay. The exact editing prompt
is saved in [assets/background-prompt.txt](assets/background-prompt.txt).
`theme/background.png` is the GRUB-compatible RGB export.
Re:Zero characters, logo and underlying artwork remain the property of their
respective rights holders; this is an unofficial fan theme. The code's MIT
license does not grant rights to that underlying artwork.

Bundled PF2 fonts are generated from DejaVu Serif. The font's notices and
redistribution terms are in [assets/FONT-LICENSE.txt](assets/FONT-LICENSE.txt),
also included in the installed theme directory.

Implementation references:

- [GNU GRUB theme format](https://www.gnu.org/software/grub/manual/grub/html_node/Theme-file-format.html)
- [GNU GRUB configuration variables](https://www.gnu.org/software/grub/manual/grub/html_node/Simple-configuration.html)
- Arch Linux's installed `grub-mkconfig` and `00_header` scripts, used to verify
  font loading, graphics terminal configuration and theme discovery.
