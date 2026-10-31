"""Ejecutar desde la raíz: python -m unittest discover -s tests -p test_blackpill.py -v"""
import struct
import threading
import time
import unittest
import numpy as np
from acquisition.acquisition_manager import AcquisitionManager
from communication.simulator import FakeBlackPill
from communication.framing import FrameParser, AudioFrame
from communication.protocol import decode_audio, FrameType


class TestBlackpill(unittest.TestCase):
    def test_pcm24_extremos(self):
        x = decode_audio(bytes.fromhex("000080 ffff7f 000000"), FrameType.AUDIO_L)
        np.testing.assert_allclose(x[:, 0], [-1, 1-1/8388608, 0], atol=1e-7)

    def test_firmware_header_and_fragmentation(self):
        for command, kind, channels in (("L", 3, 1), ("R", 4, 1), ("1", 1, 2)):
            with self.subTest(channel=command):
                dev = FakeBlackPill()
                self.assertEqual(dev.ring_size, 65536)
                dev.start(0)
                dev.receive(("STREAM:" + command + "\n").encode())
                dev.tick(2 * 256 / 97656.25)
                raw = dev.take(dev.tx_available)
                self.assertEqual(raw[:6], struct.pack("<2sBBH", b"\xaa\x55", kind, 0, 256))
                self.assertEqual(len(raw), 2 * (6 + 256 * channels * 3))
                parser = FrameParser()
                frames = []
                for b in raw:
                    frames.extend(parser.feed(bytes([b])))
                self.assertEqual(len(frames), 2)
                self.assertTrue(all(isinstance(f, AudioFrame) for f in frames))
                self.assertEqual(frames[0].samples.shape, (256, channels))

    def test_ping_and_global_sequence(self):
        dev = FakeBlackPill()
        dev.start(0)
        dev.receive(b"PING\nSTREAM:L\n")
        dev.tick(2 * 256 / 97656.25)
        frames = FrameParser().feed(dev.take(dev.tx_available))
        self.assertEqual(frames[0].text, "PONG")
        self.assertEqual([f.seq for f in frames], [0, 1, 2])

    def test_overflow_advances_sequence(self):
        dev = FakeBlackPill(ring_size=774)
        dev.start(0)
        dev.receive(b"STREAM:L\n")
        dev.tick(3 * 256 / 97656.25)
        self.assertEqual(dev.stream_dropped, 2)
        dev.take(dev.tx_available)
        dev.tick(4 * 256 / 97656.25)
        raw = dev.take(dev.tx_available)
        self.assertEqual(raw[3], 3)

    def test_manager_panel_and_reconnect(self):
        manager = AcquisitionManager(source="simulator")
        received = threading.Event()
        changed = threading.Event()
        states = []
        manager.on_state_changed = states.append
        def callback(samples):
            received.set()
            if np.allclose(samples, .25, atol=1e-6):
                changed.set()
        try:
            manager.start(callback)
            self.assertTrue(received.wait(3), manager.last_error)
            self.assertTrue(manager.is_running)
            manager.configure_simulator(
                waveform="triangle", frequency=2000,
                amplitude=0, offset=.25, noise=0,
            )
            self.assertTrue(changed.wait(3), manager.last_error)
            dev = manager._backend._simulated_device
            self.assertIn("LFREQ:2000.0", dev.commands_seen)
            self.assertIn("LWAVE:2", dev.commands_seen)
            self.assertIn("STREAM:L", dev.commands_seen)
            manager.stop()
            self.assertEqual(manager.state, "stopped")
            received.clear()
            manager.start(callback)
            self.assertTrue(received.wait(3))
        finally:
            manager.stop()

if __name__ == "__main__":
    unittest.main()
