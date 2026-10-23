from __future__ import annotations

import threading
import uuid
import webbrowser
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from .audio import EFFECTS, AudioEngine
from .catalog import CatalogError, FreesoundCatalog, THEME_QUERIES, download_sound
from .models import Macro, Sound
from .storage import Library


TABS = ["Populaires", "Réactions", "Gaming", "Cinéma", "Ambiance", "Favoris", "Perso", "Macros"]

CSS = b"""
window { background: #111318; color: #eef1f6; }
headerbar { background: #191c23; }
.hero { font-size: 24px; font-weight: 800; }
.muted { color: #9ba3b2; }
.sound-card { background: #1c2028; border: 1px solid #2c323e; border-radius: 14px; padding: 12px; }
.sound-card:hover { border-color: #7c5cff; background: #222631; }
.play-button { background: #7357f5; color: white; border-radius: 999px; min-width: 38px; min-height: 38px; }
.stop-button { background: #d84c62; color: white; }
.accent { background: #7357f5; color: white; }
.status-pill { background: #232833; border-radius: 999px; padding: 6px 12px; }
.compact { padding: 3px; min-height: 26px; min-width: 26px; }
notebook > header { background: #16191f; }
"""


def _idle(callback, *args):
    def run():
        callback(*args)
        return False

    GLib.idle_add(run)


class SoundboardWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application, title="Vengeance Soundboard")
        self.library = Library()
        self.audio = AudioEngine()
        self._macro_queue: list[Sound] = []
        self._macro_delay = 250
        self._build()
        self.set_default_size(self.library.settings.window_width, self.library.settings.window_height)
        self.connect("close-request", self._on_close)
        self.refresh_all()
        if self.library.settings.freesound_token:
            GLib.timeout_add(700, self._initial_catalog_refresh)

    def _initial_catalog_refresh(self) -> bool:
        self.refresh_online()
        return False

    def _build(self) -> None:
        header = Gtk.HeaderBar()
        title = Gtk.Label(label="VENGEANCE")
        title.add_css_class("hero")
        header.set_title_widget(title)

        add_button = Gtk.MenuButton(icon_name="list-add-symbolic", tooltip_text="Ajouter un son")
        menu = Gio.Menu()
        menu.append("Importer des fichiers…", "win.import-files")
        menu.append("Télécharger depuis une URL…", "win.import-url")
        add_button.set_menu_model(menu)
        header.pack_start(add_button)

        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Actualiser le catalogue")
        refresh.connect("clicked", lambda _button: self.refresh_online())
        header.pack_start(refresh)

        settings = Gtk.Button(icon_name="emblem-system-symbolic", tooltip_text="Réglages")
        settings.connect("clicked", lambda _button: self.show_settings())
        header.pack_end(settings)
        self.set_titlebar(header)

        self._install_action("import-files", self.import_files)
        self._install_action("import-url", self.import_url)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        toolbar.set_margin_top(12)
        toolbar.set_margin_bottom(12)
        toolbar.set_margin_start(16)
        toolbar.set_margin_end(16)

        search = Gtk.SearchEntry(placeholder_text="Rechercher un son…")
        search.set_hexpand(True)
        search.connect("search-changed", lambda entry: self.refresh_all(entry.get_text()))
        self.search = search
        toolbar.append(search)

        effect = Gtk.DropDown.new_from_strings(list(EFFECTS))
        effect.set_tooltip_text("Effet audio")
        selected = list(EFFECTS).index(self.library.settings.effect) if self.library.settings.effect in EFFECTS else 0
        effect.set_selected(selected)
        effect.connect("notify::selected", self._effect_changed)
        self.effect = effect
        toolbar.append(effect)

        volume_icon = Gtk.Image.new_from_icon_name("audio-volume-high-symbolic")
        toolbar.append(volume_icon)
        volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.5, 0.05)
        volume.set_value(self.library.settings.volume)
        volume.set_size_request(150, -1)
        volume.set_tooltip_text("Volume (jusqu'à 150 %)")
        volume.connect("value-changed", self._volume_changed)
        self.volume = volume
        toolbar.append(volume)

        stop = Gtk.Button(label="■ Stop")
        stop.add_css_class("stop-button")
        stop.connect("clicked", lambda _button: self.stop())
        toolbar.append(stop)
        root.append(toolbar)

        self.notebook = Gtk.Notebook()
        self.notebook.set_hexpand(True)
        self.notebook.set_vexpand(True)
        self.flows: dict[str, Gtk.FlowBox] = {}
        for tab_name in TABS:
            if tab_name == "Macros":
                page = self._macro_page()
            else:
                flow = Gtk.FlowBox()
                flow.set_selection_mode(Gtk.SelectionMode.NONE)
                flow.set_homogeneous(True)
                flow.set_min_children_per_line(1)
                flow.set_max_children_per_line(4)
                flow.set_column_spacing(12)
                flow.set_row_spacing(12)
                flow.set_margin_top(16)
                flow.set_margin_bottom(16)
                flow.set_margin_start(16)
                flow.set_margin_end(16)
                scroll = Gtk.ScrolledWindow()
                scroll.set_child(flow)
                page = scroll
                self.flows[tab_name] = flow
            self.notebook.append_page(page, Gtk.Label(label=tab_name))
        self.notebook.set_current_page(min(self.library.settings.last_tab, len(TABS) - 1))
        self.notebook.connect("switch-page", self._tab_changed)
        root.append(self.notebook)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bottom.set_margin_top(8)
        bottom.set_margin_bottom(8)
        bottom.set_margin_start(16)
        bottom.set_margin_end(16)
        self.status_dot = Gtk.Image.new_from_icon_name("media-playback-stop-symbolic")
        bottom.append(self.status_dot)
        self.status = Gtk.Label(label="Prêt", xalign=0)
        self.status.set_hexpand(True)
        bottom.append(self.status)
        self.route_status = Gtk.Label(label="PipeWire · auto" if self.library.settings.auto_route else "PipeWire · désactivé")
        self.route_status.add_css_class("status-pill")
        bottom.append(self.route_status)
        root.append(bottom)
        self.set_child(root)

        controller = Gtk.ShortcutController()
        for number in range(1, 10):
            shortcut = Gtk.Shortcut.new(
                Gtk.KeyvalTrigger.new(getattr(Gdk, f"KEY_{number}"), 0),
                Gtk.CallbackAction.new(lambda _widget, _args, n=number: self._play_nth(n - 1)),
            )
            controller.add_shortcut(shortcut)
        self.add_controller(controller)

    def _install_action(self, name: str, callback) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", lambda *_args: callback())
        self.add_action(action)

    def _macro_page(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label="Enchaînements", xalign=0)
        title.add_css_class("hero")
        title.set_hexpand(True)
        top.append(title)
        create = Gtk.Button(label="+ Nouvelle macro")
        create.add_css_class("accent")
        create.connect("clicked", lambda _button: self.create_macro())
        top.append(create)
        box.append(top)
        self.macro_list = Gtk.ListBox()
        self.macro_list.set_selection_mode(Gtk.SelectionMode.NONE)
        box.append(self.macro_list)
        return box

    def _clear(self, widget: Gtk.Widget) -> None:
        child = widget.get_first_child()
        while child:
            following = child.get_next_sibling()
            widget.remove(child)
            child = following

    def refresh_all(self, query: str = "") -> None:
        normalized = query.strip().casefold()
        for tab, flow in self.flows.items():
            self._clear(flow)
            if tab == "Favoris":
                sounds = [item for item in self.library.sounds if item.favorite]
            elif tab == "Perso":
                sounds = [item for item in self.library.sounds if item.theme == "Perso"]
            else:
                sounds = [item for item in self.library.sounds if item.theme == tab]
            if normalized:
                sounds = [item for item in sounds if normalized in f"{item.name} {item.author}".casefold()]
            sounds.sort(key=lambda item: (not item.favorite, -item.plays, item.name.casefold()))
            for index, sound in enumerate(sounds):
                flow.append(self._sound_card(sound, index))
            if not sounds:
                label = Gtk.Label(label="Aucun son ici — utilise + ou actualise le catalogue.")
                label.add_css_class("muted")
                label.set_margin_top(60)
                flow.append(label)
        self._refresh_macros()

    def _sound_card(self, sound: Sound, index: int) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("sound-card")
        card.set_size_request(230, 132)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        play = Gtk.Button(label="▶")
        play.add_css_class("play-button")
        play.connect("clicked", lambda _button: self.play_sound(sound))
        top.append(play)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        labels.set_hexpand(True)
        title = Gtk.Label(label=sound.name, xalign=0, ellipsize=3)
        title.set_tooltip_text(sound.name)
        labels.append(title)
        detail_parts = []
        if sound.author:
            detail_parts.append(sound.author)
        if sound.duration:
            detail_parts.append(f"{sound.duration:.1f} s")
        detail = Gtk.Label(label=" · ".join(detail_parts) or "Fichier local", xalign=0, ellipsize=3)
        detail.add_css_class("muted")
        labels.append(detail)
        top.append(labels)
        card.append(top)
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        shortcut = Gtk.Label(label=f"Touche {index + 1}" if index < 9 else "")
        shortcut.add_css_class("muted")
        shortcut.set_hexpand(True)
        shortcut.set_xalign(0)
        bottom.append(shortcut)
        favorite = Gtk.Button(icon_name="starred-symbolic" if sound.favorite else "non-starred-symbolic", tooltip_text="Favori")
        favorite.add_css_class("compact")
        favorite.connect("clicked", lambda _button: self.toggle_favorite(sound))
        bottom.append(favorite)
        if sound.preview_url and not sound.local_path:
            download = Gtk.Button(icon_name="folder-download-symbolic", tooltip_text="Télécharger localement")
            download.add_css_class("compact")
            download.connect("clicked", lambda _button: self.download(sound))
            bottom.append(download)
        if sound.source_url:
            source = Gtk.Button(icon_name="web-browser-symbolic", tooltip_text="Voir la source et la licence")
            source.add_css_class("compact")
            source.connect("clicked", lambda _button: webbrowser.open(sound.source_url))
            bottom.append(source)
        if sound.theme == "Perso":
            delete = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Supprimer")
            delete.add_css_class("compact")
            delete.connect("clicked", lambda _button: self.delete_sound(sound))
            bottom.append(delete)
        card.append(bottom)
        return card

    def _play_nth(self, index: int) -> bool:
        tab = TABS[self.notebook.get_current_page()]
        if tab not in self.flows:
            return False
        if tab == "Favoris":
            sounds = [item for item in self.library.sounds if item.favorite]
        elif tab == "Perso":
            sounds = [item for item in self.library.sounds if item.theme == "Perso"]
        else:
            sounds = [item for item in self.library.sounds if item.theme == tab]
        sounds.sort(key=lambda item: (not item.favorite, -item.plays, item.name.casefold()))
        if index < len(sounds):
            self.play_sound(sounds[index])
            return True
        return False

    def play_sound(self, sound: Sound, finished=None) -> None:
        if sound.local_path and Path(sound.local_path).is_file():
            self._start_playback(sound, finished)
            return
        if sound.preview_url:
            self.download(sound, play_after=True, finished=finished)
            return
        self.show_error("Fichier introuvable", "Réimporte ce son ou vérifie son chemin.")

    def _start_playback(self, sound: Sound, finished=None) -> None:
        sound.plays += 1
        self.library.save()
        self.status.set_text(f"Lecture · {sound.name}")
        self.status_dot.set_from_icon_name("media-playback-start-symbolic")

        def ended(error):
            if error:
                self.show_error("Erreur de lecture", error)
            self.status.set_text("Prêt")
            self.status_dot.set_from_icon_name("media-playback-stop-symbolic")
            if finished:
                finished(error)

        try:
            self.audio.play(
                Path(sound.local_path),
                self.library.settings.volume,
                self.library.settings.effect,
                self.library.settings.auto_route,
                self.library.settings.discord_pattern,
                ended,
            )
        except Exception as error:
            ended(str(error))

    def stop(self) -> None:
        self._macro_queue.clear()
        self.audio.stop()
        self.status.set_text("Arrêté")

    def download(self, sound: Sound, play_after: bool = False, finished=None) -> None:
        self.status.set_text(f"Téléchargement · {sound.name}")

        def worker():
            try:
                path = download_sound(sound, self.library.sounds_dir)
                _idle(done, path, None)
            except Exception as error:
                _idle(done, None, str(error))

        def done(path, error):
            if error:
                self.status.set_text("Échec du téléchargement")
                self.show_error("Téléchargement impossible", error)
                if finished:
                    finished(error)
                return
            sound.local_path = str(path)
            self.library.upsert(sound)
            self.status.set_text(f"Téléchargé · {sound.name}")
            self.refresh_all(self.search.get_text())
            if play_after:
                self._start_playback(sound, finished)

        threading.Thread(target=worker, daemon=True).start()

    def refresh_online(self) -> None:
        token = self.library.settings.freesound_token
        if not token:
            self.show_settings(first_run=True)
            return
        themes = list(THEME_QUERIES)
        self.status.set_text("Actualisation du catalogue populaire…")

        def worker():
            try:
                catalog = FreesoundCatalog(token)
                results = []
                for theme in themes:
                    results.extend(catalog.search(theme))
                _idle(done, results, None)
            except Exception as error:
                _idle(done, [], str(error))

        def done(results, error):
            if error:
                self.status.set_text("Catalogue indisponible")
                self.show_error("Catalogue Freesound", error)
                return
            for sound in results:
                self.library.upsert(sound)
            self.status.set_text(f"Catalogue actualisé · {len(results)} sons")
            self.refresh_all(self.search.get_text())

        threading.Thread(target=worker, daemon=True).start()

    def toggle_favorite(self, sound: Sound) -> None:
        sound.favorite = not sound.favorite
        self.library.save()
        self.refresh_all(self.search.get_text())

    def delete_sound(self, sound: Sound) -> None:
        dialog = Gtk.AlertDialog(message=f"Supprimer « {sound.name} » ?", detail="Le fichier local associé sera également supprimé.", buttons=["Annuler", "Supprimer"], cancel_button=0, default_button=0)

        def answered(source, result):
            try:
                if source.choose_finish(result) == 1:
                    self.library.remove(sound)
                    self.refresh_all(self.search.get_text())
            except GLib.Error:
                pass

        dialog.choose(self, None, answered)

    def import_files(self) -> None:
        dialog = Gtk.FileDialog(title="Importer des sons")
        audio = Gtk.FileFilter()
        audio.set_name("Fichiers audio")
        for mime in ("audio/mpeg", "audio/ogg", "audio/wav", "audio/flac", "audio/opus", "audio/mp4"):
            audio.add_mime_type(mime)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(audio)
        dialog.set_filters(filters)

        def selected(source, result):
            try:
                files = source.open_multiple_finish(result)
                imported = 0
                for index in range(files.get_n_items()):
                    path = files.get_item(index).get_path()
                    if path:
                        self.library.add_local(Path(path))
                        imported += 1
                self.status.set_text(f"{imported} son(s) importé(s)")
                self.refresh_all(self.search.get_text())
            except GLib.Error:
                pass

        dialog.open_multiple(self, None, selected)

    def import_url(self) -> None:
        dialog = Gtk.Dialog(title="Télécharger un son", transient_for=self, modal=True)
        dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
        dialog.add_button("Télécharger", Gtk.ResponseType.OK)
        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)
        name = Gtk.Entry(placeholder_text="Nom du son")
        url = Gtk.Entry(placeholder_text="https://…/son.mp3")
        content.append(Gtk.Label(label="Nom", xalign=0))
        content.append(name)
        content.append(Gtk.Label(label="URL directe du fichier audio", xalign=0))
        content.append(url)

        def response(source, response_id):
            if response_id == Gtk.ResponseType.OK and url.get_text().strip():
                sound = Sound(
                    id=f"url-{uuid.uuid4().hex}",
                    name=name.get_text().strip() or Path(url.get_text().split("?", 1)[0]).stem or "Son web",
                    theme="Perso",
                    preview_url=url.get_text().strip(),
                    source_url=url.get_text().strip(),
                )
                self.library.upsert(sound)
                self.download(sound)
            source.destroy()

        dialog.connect("response", response)
        dialog.present()

    def create_macro(self) -> None:
        candidates = [item for item in self.library.sounds if item.local_path or item.preview_url]
        if not candidates:
            self.show_error("Aucun son", "Ajoute au moins un son avant de créer une macro.")
            return
        dialog = Gtk.Dialog(title="Nouvelle macro", transient_for=self, modal=True)
        dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
        dialog.add_button("Créer", Gtk.ResponseType.OK)
        area = dialog.get_content_area()
        area.set_spacing(8)
        area.set_margin_top(16)
        area.set_margin_bottom(16)
        area.set_margin_start(16)
        area.set_margin_end(16)
        name = Gtk.Entry(placeholder_text="Nom de la macro")
        area.append(name)
        delay = Gtk.SpinButton.new_with_range(0, 5000, 50)
        delay.set_value(250)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(Gtk.Label(label="Pause entre les sons (ms)", xalign=0))
        row.append(delay)
        area.append(row)
        checks = []
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for sound in candidates:
            check = Gtk.CheckButton(label=sound.name)
            checks.append((check, sound))
            list_box.append(check)
        scroll = Gtk.ScrolledWindow(min_content_height=280)
        scroll.set_child(list_box)
        area.append(scroll)

        def response(source, response_id):
            selected = [sound.id for check, sound in checks if check.get_active()]
            if response_id == Gtk.ResponseType.OK and selected:
                self.library.macros.append(Macro(uuid.uuid4().hex, name.get_text().strip() or "Nouvelle macro", selected, delay.get_value_as_int()))
                self.library.save()
                self._refresh_macros()
            source.destroy()

        dialog.connect("response", response)
        dialog.present()

    def _refresh_macros(self) -> None:
        self._clear(self.macro_list)
        for macro in self.library.macros:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_top(8)
            row.set_margin_bottom(8)
            play = Gtk.Button(label="▶")
            play.add_css_class("play-button")
            play.connect("clicked", lambda _button, item=macro: self.play_macro(item))
            row.append(play)
            count = len([sid for sid in macro.sound_ids if self.library.by_id(sid)])
            label = Gtk.Label(label=f"{macro.name}\n{count} sons · pause {macro.delay_ms} ms", xalign=0)
            label.set_hexpand(True)
            row.append(label)
            delete = Gtk.Button(icon_name="user-trash-symbolic")
            delete.connect("clicked", lambda _button, item=macro: self.delete_macro(item))
            row.append(delete)
            self.macro_list.append(row)

    def play_macro(self, macro: Macro) -> None:
        self._macro_queue = [sound for sound_id in macro.sound_ids if (sound := self.library.by_id(sound_id))]
        self._macro_delay = macro.delay_ms
        self._play_macro_next()

    def _play_macro_next(self) -> bool:
        if not self._macro_queue:
            self.status.set_text("Macro terminée")
            return False
        sound = self._macro_queue.pop(0)

        def finished(error):
            if error:
                self._macro_queue.clear()
            elif self._macro_queue:
                GLib.timeout_add(self._macro_delay, self._play_macro_next)

        self.play_sound(sound, finished)
        return False

    def delete_macro(self, macro: Macro) -> None:
        self.library.macros = [item for item in self.library.macros if item.id != macro.id]
        self.library.save()
        self._refresh_macros()

    def show_settings(self, first_run: bool = False) -> None:
        dialog = Gtk.Dialog(title="Réglages", transient_for=self, modal=True)
        dialog.add_button("Annuler", Gtk.ResponseType.CANCEL)
        dialog.add_button("Enregistrer", Gtk.ResponseType.OK)
        area = dialog.get_content_area()
        area.set_spacing(8)
        area.set_margin_top(16)
        area.set_margin_bottom(16)
        area.set_margin_start(16)
        area.set_margin_end(16)
        if first_run:
            intro = Gtk.Label(label="Une clé API gratuite Freesound est nécessaire pour charger automatiquement le catalogue.", wrap=True, xalign=0)
            intro.add_css_class("muted")
            area.append(intro)
        token = Gtk.PasswordEntry(show_peek_icon=True)
        token.set_text(self.library.settings.freesound_token)
        area.append(Gtk.Label(label="Clé API Freesound", xalign=0))
        area.append(token)
        api_link = Gtk.LinkButton(uri="https://freesound.org/apiv2/apply/", label="Obtenir une clé API Freesound")
        area.append(api_link)
        auto_route = Gtk.CheckButton(label="Connecter automatiquement la lecture à Discord")
        auto_route.set_active(self.library.settings.auto_route)
        area.append(auto_route)
        area.append(Gtk.Label(label="Motif de l’entrée PipeWire Discord", xalign=0))
        pattern = Gtk.Entry(text=self.library.settings.discord_pattern)
        area.append(pattern)
        warning = Gtk.Label(label="La clé est conservée localement dans le fichier de configuration.", wrap=True, xalign=0)
        warning.add_css_class("muted")
        area.append(warning)

        def response(source, response_id):
            if response_id == Gtk.ResponseType.OK:
                had_token = bool(self.library.settings.freesound_token)
                self.library.settings.freesound_token = token.get_text().strip()
                self.library.settings.auto_route = auto_route.get_active()
                self.library.settings.discord_pattern = pattern.get_text().strip()
                self.library.save()
                self.route_status.set_text("PipeWire · auto" if auto_route.get_active() else "PipeWire · désactivé")
                source.destroy()
                if self.library.settings.freesound_token and not had_token:
                    self.refresh_online()
                return
            source.destroy()

        dialog.connect("response", response)
        dialog.present()

    def show_error(self, title: str, detail: str) -> None:
        Gtk.AlertDialog(message=title, detail=detail, buttons=["Fermer"]).show(self)

    def _volume_changed(self, scale) -> None:
        value = scale.get_value()
        self.library.settings.volume = value
        self.audio.set_volume(value)
        self.library.save()

    def _effect_changed(self, dropdown, _param) -> None:
        selected = dropdown.get_selected()
        self.library.settings.effect = list(EFFECTS)[selected] if selected < len(EFFECTS) else "Aucun"
        self.library.save()

    def _tab_changed(self, _notebook, _page, index: int) -> None:
        self.library.settings.last_tab = index
        self.library.save()

    def _on_close(self, _window) -> bool:
        self.audio.stop(notify=False)
        width, height = self.get_width(), self.get_height()
        self.library.settings.window_width = width
        self.library.settings.window_height = height
        self.library.save()
        return False
