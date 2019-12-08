"""A tiny example binary for the native Python rules of Bazel."""

import unittest
import os


class Test(unittest.TestCase):

    def test_ok(self):
        # do stuff
        os.chdir("./test/test2/input")
        for f in os.listdir():
            if f.startswith("_"):
                os.rename(f, f[1:])
        os.system("bazel_to_cmake.py test")
        os.chdir("..")

        with open("./expected/CMakeLists.txt.expected", 'r') as f:
            expected = f.read().replace("\n", "").replace(" ", "").lower()

        with open("./input/test", 'r') as f:
            actual = f.read().replace("\n", "").replace(" ", "").lower()

        self.assertTrue(expected in actual)


if __name__ == '__main__':
    unittest.main()
