#!/usr/bin/env python3
"""
测试适配器模块
"""

class LegacyTestAdapter:
    """遗留测试适配器"""
    def __init__(self):
        pass
    
    def adapt_test(self, test_case):
        return test_case