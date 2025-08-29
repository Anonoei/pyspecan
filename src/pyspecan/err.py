"""Error types"""
class _Error(Exception):
    """pyspecan Error"""

class UnknownOption(_Error):
    """Error thrown when an unknown option is provided"""

class Overflow(_Error):
    """Error thrown when an overflow occurs"""
