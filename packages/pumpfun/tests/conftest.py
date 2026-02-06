# Define fixture pumpfun_client
import pytest

from pumpfun.client import PumpfunClient


@pytest.fixture
def pumpfun_client():
    return PumpfunClient()
