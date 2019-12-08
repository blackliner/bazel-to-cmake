"""A tiny example binary for the native Python rules of Bazel."""

import unittest
import os


class Test(unittest.TestCase):

    def test_ok(self):
        # do stuff
        print("hellooooooooooooooooooooooooooo")
        print(os.getcwd())
        os.chdir("input/")
        os.system("bazel_to_cmake.py test")
        os.chdir("..")

        expected = open(
            "./expected/CMakeLists.txt.expected").read().replace("\n", "").replace(" ", "")
        actual = open("./input/test").read().replace("\n", "").replace(" ", "")

        self.assertTrue(actual in expected)


if __name__ == '__main__':
    unittest.main()
