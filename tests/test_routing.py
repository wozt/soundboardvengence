import unittest

from vengeance_soundboard.routing import Link, choose_links


class RoutingTests(unittest.TestCase):
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
