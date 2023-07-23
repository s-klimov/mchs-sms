from unittest.mock import patch


class MockResponse:
    status_code: int

    def json(self):
        pass


@patch(__name__ + ".MockResponse")
async def test_request_smsc(mock_class):

    instance = mock_class.return_value
    instance.json.return_value = {"cnt": 2, "id": 430}
    instance.status_code = 200

    assert True
