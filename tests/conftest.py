import pytest
from fastapi.testclient import TestClient

from paid_media.analytics import diagnose
from paid_media.api import create_app
from paid_media.data import generate, write_samples


@pytest.fixture(scope="session")
def dataset():
    return generate()


@pytest.fixture(scope="session")
def report(dataset):
    return diagnose(*dataset)


@pytest.fixture
def client(tmp_path):
    write_samples(tmp_path / "data")
    with TestClient(create_app(tmp_path / "data", tmp_path / "reviews.sqlite")) as test_client:
        yield test_client
