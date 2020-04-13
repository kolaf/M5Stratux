from unittest import TestCase

from clip_line import clip_line, compute_out_code, BOTTOM


class TestClip(TestCase):
    def test_out_code(self):
        out0 = compute_out_code(0, -4)
        out1 = compute_out_code(400, -4)
        print(out0 & BOTTOM)
        print(out1 & BOTTOM)
        self.assertEqual(out0 & BOTTOM, out1 & BOTTOM)
        print(out0 & out1)

    def test_below(self):
        x0, y0, x1, y1 = clip_line(0, -4, 400, -4)
        self.assertIsNone(x0)
