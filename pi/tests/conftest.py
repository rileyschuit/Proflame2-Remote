import pytest

from proflame2d.frame import Identity

TEST_IDENTITY = Identity(0xA00402, 0x0, 0xC, 0xA, 0x4)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()
