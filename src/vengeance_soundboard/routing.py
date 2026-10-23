from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Link:
    output: str
    input: str


def list_ports(direction: str) -> list[str]:
    if direction not in {"-o", "-i"} or not shutil.which("pw-link"):
        return []
    result = subprocess.run(["pw-link", direction], capture_output=True, text=True, timeout=3, check=False)
    if result.returncode:
        return []
    return [line.strip() for line in result.stdout.splitlines() if ":" in line]


def list_capture_nodes() -> list[str]:
    """Return PipeWire nodes suitable as microphone/software-loopback sources."""
    nodes: list[str] = []
    for port in list_ports("-o"):
        lowered = port.casefold()
        if not any(marker in lowered for marker in ("alsa_input", "bluez_input", ":capture_", ":monitor_")):
            continue
        node = port.rsplit(":", 1)[0]
        if node not in nodes and "vengeance soundboard" not in lowered:
            nodes.append(node)
    return nodes


def choose_links(outputs: list[str], inputs: list[str], source_pattern: str, target_pattern: str) -> list[Link]:
    try:
        source_re = re.compile(source_pattern)
        target_re = re.compile(target_pattern)
    except re.error:
        return []
    sources = [port for port in outputs if source_re.search(port)]
    targets = [port for port in inputs if target_re.search(port)]
    links: list[Link] = []
    for source in sources:
        source_channel = source.rsplit("_", 1)[-1]
        channel_targets = [target for target in targets if target.endswith(f"_{source_channel}")]
        if not channel_targets and targets:
            # Discord often exposes a single MONO input; both stereo ports may feed it.
            channel_targets = [targets[0]]
        links.extend(Link(source, target) for target in channel_targets[:1])
    return links


class PipeWireRouter:
    SOURCE_PATTERN = r"(?i)Vengeance Soundboard.*:output"

    def __init__(self, target_pattern: str, source_pattern: str | None = None):
        self.target_pattern = target_pattern
        self.source_pattern = source_pattern or self.SOURCE_PATTERN
        self.created: list[Link] = []

    @property
    def available(self) -> bool:
        return bool(shutil.which("pw-link"))

    def candidates(self) -> list[Link]:
        if not self.available:
            return []
        return choose_links(list_ports("-o"), list_ports("-i"), self.source_pattern, self.target_pattern)

    def connect(self) -> int:
        for link in self.candidates():
            result = subprocess.run(["pw-link", link.output, link.input], capture_output=True, timeout=3, check=False)
            if result.returncode == 0 and link not in self.created:
                self.created.append(link)
        return len(self.created)

    def disconnect(self) -> None:
        for link in self.created:
            subprocess.run(["pw-link", "-d", link.output, link.input], capture_output=True, timeout=3, check=False)
        self.created.clear()
