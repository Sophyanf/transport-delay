# Позволяет тестам импортировать друг друга (test_no_future_leak → test_builder).
import sys
from pathlib import Path

TESTS_DIRECTORY = Path(__file__).resolve().parent
if str(TESTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(TESTS_DIRECTORY))
