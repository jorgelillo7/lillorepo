from core import utils


def test_read_secret_from_file_exists(mock_filesystem):
    """Reads the content of an existing file."""
    secret_path = mock_filesystem("test_secret.txt", "my_secret_password")
    assert utils.read_secret_from_file(secret_path) == "my_secret_password"


def test_read_secret_from_file_not_exists():
    """Returns the fallback when the file does not exist."""
    assert utils.read_secret_from_file("/nonexistent/path", "default") == "default"


def test_read_secret_from_file_empty_path():
    """Returns the fallback when the path is empty."""
    assert utils.read_secret_from_file("", "default") == "default"
