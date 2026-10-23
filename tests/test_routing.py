import unittest

from unittest.mock import patch

from vengeance_soundboard.routing import Link, choose_links, list_capture_nodes


class RoutingTests(unittest.TestCase):
    @patch("vengeance_soundboard.routing.list_ports")
    def test_capture_nodes_include_microphones_and_software_monitors(self, ports):
        ports.return_value = [
            "alsa_input.usb-microphone:capture_MONO",
            "discord_capture:monitor_FL",
            "discord_capture:monitor_FR",
            "WEBRTC VoiceEngine:monitor_MONO",
            "Firefox:output_FL",
        ]
        self.assertEqual(
            list_capture_nodes(),
            ["alsa_input.usb-microphone", "discord_capture"],
        )

    def test_choose_stereo_links_by_channel(self):
        outputs = ["Vengeance Soundboard:output_FL", "Vengeance Soundboard:output_FR"]
        inputs = ["WEBRTC VoiceEngine:input_FL", "WEBRTC VoiceEngine:input_FR"]
        self.assertEqual(
            choose_links(outputs, inputs, r"Vengeance.*:output", r"WEBRTC.*:input"),
            [Link(outputs[0], inputs[0]), Link(outputs[1], inputs[1])],
        )

    def test_choose_mono_discord_input_for_stereo_source(self):
        outputs = ["Vengeance Soundboard:output_FL", "Vengeance Soundboard:output_FR"]
        inputs = ["WEBRTC VoiceEngine:input_MONO"]
        links = choose_links(outputs, inputs, r"Vengeance.*:output", r"WEBRTC.*:input")
        self.assertEqual(links, [Link(outputs[0], inputs[0]), Link(outputs[1], inputs[0])])
