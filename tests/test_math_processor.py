import unittest

import numpy as np

from processing.math_processor import MathProcessor


class MathProcessorTests(unittest.TestCase):
    def setUp(self):
        self.data = np.column_stack((
            np.linspace(-1.0, 1.0, 1000),
            np.full(1000, 2.0),
        ))

    def evaluate(self, operation):
        processor = MathProcessor()
        processor.configure(operation=operation, source_a=1, source_b=2)
        return processor.evaluate(self.data, 1000.0).values

    def test_binary_operations(self):
        np.testing.assert_allclose(self.evaluate("add"), self.data[:, 0] + 2)
        np.testing.assert_allclose(self.evaluate("subtract"), self.data[:, 0] - 2)
        np.testing.assert_allclose(self.evaluate("multiply"), self.data[:, 0] * 2)
        np.testing.assert_allclose(self.evaluate("divide"), self.data[:, 0] / 2)

    def test_unary_and_calculus_operations(self):
        processor = MathProcessor()
        processor.configure(operation="abs", source_a=1)
        np.testing.assert_allclose(processor.evaluate(self.data, 1000).values, np.abs(self.data[:, 0]))
        processor.configure(operation="derivative", source_a=1)
        np.testing.assert_allclose(processor.evaluate(self.data, 1000).values, 2.0, atol=.01)

    def test_logic_and_comparison(self):
        values = self.evaluate("greater")
        self.assertTrue(np.all((values == 0) | (values == 1)))
        processor = MathProcessor()
        processor.configure(operation="and")
        result = processor.evaluate(self.data, 1000).values
        self.assertTrue(np.all((result == 0) | (result == 1)))
        self.assertGreater(result.sum(), 0)


if __name__ == "__main__":
    unittest.main()
