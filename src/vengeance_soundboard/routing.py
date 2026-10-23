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

    def __init__(self, target_pattern: str):
        self.target_pattern = target_pattern
        self.created: list[Link] = []

    @property
    def available(self) -> bool:
        return bool(shutil.which("pw-link"))

    def connect(self) -> int:
        if not self.available:
            return 0
        candidates = choose_links(list_ports("-o"), list_ports("-i"), self.SOURCE_PATTERN, self.target_pattern)
        for link in candidates:
            result = subprocess.run(["pw-link", link.output, link.input], capture_output=True, timeout=3, check=False)
            if result.returncode == 0 and link not in self.created:
                self.created.append(link)
        return len(self.created)

    def disconnect(self) -> None:
        for link in self.created:
            subprocess.run(["pw-link", "-d", link.output, link.input], capture_output=True, timeout=3, check=False)
        self.created.clear()
