import unittest
import numpy as np
from acquisition.frame_decoder import FrameDecoder, decode_pcm24
from acquisition.blackpill_simulator import BlackpillSimulator


class TestBlackpill(unittest.TestCase):
    def test_pcm24_sign(self):
        samples = decode_pcm24(bytes.fromhex("000080 ffff7f 000000"), 1)
        np.testing.assert_allclose(samples[:, 0], [-1, 1-1/8388608, 0], atol=1e-7)

    def test_fragmented_stereo(self):
        sim = BlackpillSimulator(channels=2)
        packet = sim.make_packet()
        decoder = FrameDecoder()
        result = []
        for b in packet:
            result.extend(decoder.feed(bytes((b,))))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].samples.shape, (256, 2))
        self.assertEqual(result[0].channel, None)

    def test_mono_and_sequence_wrap(self):
        sim = BlackpillSimulator(channels=1)
        sim._sequence = 255
        decoder = FrameDecoder()
        frames = decoder.feed(sim.make_packet() + sim.make_packet())
        self.assertEqual([f.sequence for f in frames], [255, 0])
        self.assertEqual(decoder.lost_packets, 0)
        self.assertEqual(frames[0].samples.shape, (256, 1))

    def test_resynchronization(self):
        sim = BlackpillSimulator()
        decoder = FrameDecoder()
        self.assertEqual(len(decoder.feed(b"noise\xaa")), 0)
        self.assertEqual(len(decoder.feed(sim.make_packet()[1:])), 1)


if __name__ == "__main__":
    unittest.main()
