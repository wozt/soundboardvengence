from __future__ import annotations

from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

from .routing import PipeWireRouter


Gst.init(None)

EFFECTS: dict[str, dict[str, float]] = {
    "Aucun": {"pitch": 1.0, "tempo": 1.0, "echo": 0.0, "feedback": 0.0},
    "Écho": {"pitch": 1.0, "tempo": 1.0, "echo": 0.55, "feedback": 0.35},
    "Chipmunk": {"pitch": 1.55, "tempo": 1.0, "echo": 0.0, "feedback": 0.0},
    "Démon": {"pitch": 0.62, "tempo": 0.92, "echo": 0.18, "feedback": 0.15},
    "Robot": {"pitch": 0.82, "tempo": 1.0, "echo": 0.35, "feedback": 0.62},
    "Rapide": {"pitch": 1.0, "tempo": 1.35, "echo": 0.0, "feedback": 0.0},
}


class AudioEngine:
    def __init__(self):
        self.pipeline: Gst.Element | None = None
        self.router: PipeWireRouter | None = None
        self._finished: Callable[[str | None], None] | None = None
        self._route_timer = 0

    @staticmethod
    def _make_pipeline(path: Path, volume: float, effect: str) -> Gst.Element:
        values = EFFECTS.get(effect, EFFECTS["Aucun"])
        pipeline = Gst.Pipeline.new("vengeance-player")
        source = Gst.ElementFactory.make("uridecodebin", "source")
        queue = Gst.ElementFactory.make("queue", "queue")
        convert = Gst.ElementFactory.make("audioconvert", "convert")
        resample = Gst.ElementFactory.make("audioresample", "resample")
        pitch = Gst.ElementFactory.make("pitch", "pitch")
        echo = Gst.ElementFactory.make("audioecho", "echo")
        volume_element = Gst.ElementFactory.make("volume", "volume")
        sink = Gst.ElementFactory.make("pipewiresink", "sink")
        elements = [source, queue, convert, resample, pitch, echo, volume_element, sink]
        if any(element is None for element in elements):
            raise RuntimeError("Plugins GStreamer requis manquants (base, good, bad et PipeWire).")
        source.set_property("uri", path.resolve().as_uri())
        pitch.set_property("pitch", values["pitch"])
        pitch.set_property("tempo", values["tempo"])
        delay = 180_000_000
        echo.set_property("max-delay", delay)
        echo.set_property("delay", delay)
        echo.set_property("intensity", values["echo"])
        echo.set_property("feedback", values["feedback"])
        volume_element.set_property("volume", max(0.0, min(volume, 1.5)))
        sink.set_property("client-name", "Vengeance Soundboard")
        for element in elements:
            pipeline.add(element)
        chain = [queue, convert, resample, pitch, echo, volume_element, sink]
        if not all(left.link(right) for left, right in zip(chain, chain[1:])):
            raise RuntimeError("Impossible de construire la chaîne audio GStreamer.")

        def pad_added(_source, pad):
            sink_pad = queue.get_static_pad("sink")
            caps = pad.get_current_caps() or pad.query_caps(None)
            structure = caps.get_structure(0) if caps and caps.get_size() else None
            if structure and structure.get_name().startswith("audio/") and not sink_pad.is_linked():
                pad.link(sink_pad)

        source.connect("pad-added", pad_added)
        return pipeline

    def play(
        self,
        path: Path,
        volume: float,
        effect: str,
        auto_route: bool,
        discord_pattern: str,
        finished: Callable[[str | None], None] | None = None,
    ) -> None:
        self.stop(notify=False)
        self._finished = finished
        self.pipeline = self._make_pipeline(path, volume, effect)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_message)
        if auto_route:
            self.router = PipeWireRouter(discord_pattern)
            self._route_timer = GLib.timeout_add(120, self._try_route)
        result = self.pipeline.set_state(Gst.State.PLAYING)
        if result == Gst.StateChangeReturn.FAILURE:
            self.stop(notify=False)
            raise RuntimeError("GStreamer n'a pas pu démarrer la lecture.")

    def _try_route(self) -> bool:
        if not self.pipeline or not self.router:
            return False
        if self.router.connect() or not self.router.available:
            self._route_timer = 0
            return False
        return True

    def _on_message(self, _bus, message) -> None:
        if message.type == Gst.MessageType.EOS:
            self.stop()
        elif message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            self.stop(error=f"{error.message}\n{debug or ''}".strip())

    def set_volume(self, volume: float) -> None:
        if self.pipeline:
            element = self.pipeline.get_by_name("volume")
            if element:
                element.set_property("volume", max(0.0, min(volume, 1.5)))

    def stop(self, notify: bool = True, error: str | None = None) -> None:
        callback = self._finished if notify else None
        self._finished = None
        if self._route_timer:
            GLib.source_remove(self._route_timer)
            self._route_timer = 0
        if self.router:
            self.router.disconnect()
            self.router = None
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        if callback:
            GLib.idle_add(callback, error)
