from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, Gtk  # noqa: E402

from .ui import CSS, SoundboardWindow


class SoundboardApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.vengeance.Soundboard", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self) -> None:
        window = self.get_active_window()
        if not window:
            window = SoundboardWindow(self)
        window.present()


def main() -> int:
    return SoundboardApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
