"""Pruebas sin PySide6: python -m unittest discover -s tests -p 'test_horizontal_navigation.py' -v"""
import unittest
from math import isclose
import numpy as np
from horizontal_navigation import HorizontalView, reference_fraction


class HorizontalNavigationTest(unittest.TestCase):
    def test_referencia_centro(self):
        v = HorizontalView(0.001)
        self.assertTrue(isclose(v.x_range[0], -0.006))
        self.assertTrue(isclose(v.x_range[1], 0.006))

    def test_referencias_laterales(self):
        self.assertEqual(HorizontalView(0.001, reference=0).x_range, (0, .012))
        self.assertEqual(HorizontalView(0.001, reference=1).x_range, (-.012, 0))

    def test_delay_positivo(self):
        v = HorizontalView(.001, delay_seconds=.002)
        self.assertAlmostEqual(v.x_range[0], -.004)
        self.assertAlmostEqual(v.x_range[1], .008)

    def test_delay_negativo(self):
        v = HorizontalView(.001, delay_seconds=-.002)
        self.assertAlmostEqual(v.x_range[0], -.008)

    def test_zoom_no_altera_time_div_adquisicion(self):
        v = HorizontalView(.001, zoom=4)
        self.assertEqual(v.time_per_division, .001)
        self.assertAlmostEqual(v.span_seconds, .003)

    def test_muestra_exacta_al_trigger(self):
        rate = 97656.25
        v = HorizontalView(.001, zoom=2)
        recorte = v.sample_interval(97656, rate, 50000)
        self.assertIsNotNone(recorte)
        first, end, anchor = recorte
        self.assertAlmostEqual(first + anchor, 50000)
        self.assertLess(end-first, 1000)

    def test_view_fuera_de_historial(self):
        v = HorizontalView(.001, delay_seconds=.5)
        self.assertIsNone(v.sample_interval(1024, 97656.25, 500))

    def test_explora_datos_historicos(self):
        rate = 100000.
        data = np.arange(100000)
        anchor = 75000
        v1 = HorizontalView(.001, delay_seconds=-.1)
        v2 = HorizontalView(.001, delay_seconds=+.1)
        s1 = v1.sample_interval(len(data), rate, anchor)
        s2 = v2.sample_interval(len(data), rate, anchor)
        self.assertLess(s1[0], s2[0])
        self.assertEqual(data[s1[0]], s1[0])

    def test_referencia_personalizada(self):
        self.assertAlmostEqual(reference_fraction("Custom", .27), .27)
        self.assertEqual(reference_fraction("Center"), .5)

    def test_parametros_invalidos(self):
        for kwargs in ({"time_per_division": 0}, {"time_per_division": .001, "zoom": .5},
                       {"time_per_division": .001, "reference": 1.1},
                       {"time_per_division": .001, "delay_seconds": float('nan')}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    HorizontalView(**kwargs)
        with self.assertRaises(ValueError):
            reference_fraction("Unknown")


if __name__ == '__main__':
    unittest.main()
