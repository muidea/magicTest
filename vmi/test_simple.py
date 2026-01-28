#!/usr/bin/env python3
"""
简单的测试验证
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_base import TestBase
import unittest

class SimpleTest(TestBase):
    def test_simple(self):
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()