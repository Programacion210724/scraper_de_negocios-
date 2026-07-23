import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_service_account_file(tmp_path):
    """Create a temporary service_account.json for testing"""
    sa_path = tmp_path / "service_account.json"
    sa_path.write_text('{"type": "service_account", "project_id": "test"}')
    return str(sa_path)


@patch("google_sheets.os.path.exists")
@patch("google_sheets.Credentials.from_service_account_file")
def test_get_credentials_success(mock_creds, mock_exists):
    mock_exists.return_value = True
    mock_creds.return_value = MagicMock()

    from google_sheets import get_credentials
    creds = get_credentials()
    assert creds is not None
    mock_creds.assert_called_once()


@patch("google_sheets.os.path.exists")
def test_get_credentials_missing_file(mock_exists):
    mock_exists.return_value = False

    from google_sheets import get_credentials
    with pytest.raises(FileNotFoundError):
        get_credentials()


@patch("google_sheets.get_credentials")
@patch("google_sheets.build")
def test_append_rows_success(mock_build, mock_get_creds, sample_results):
    mock_get_creds.return_value = MagicMock()
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.spreadsheets().values().append().execute.return_value = {"updates": {"updatedRows": 5}}

    from google_sheets import append_rows
    headers = ["Nombre", "Dirección", "Teléfono", "Ciudad", "Categoría", "Google Maps"]
    rows = [headers] + [
        [r["nombre"], r["direccion"], r["telefono"], r["ciudad"], r["categoria"], r["maps_url"]]
        for r in sample_results
    ]
    result = append_rows("test_sheet_id", rows)
    assert result["updates"]["updatedRows"] == 5


@patch("google_sheets.get_credentials")
@patch("google_sheets.build")
def test_append_rows_empty_values_succeeds(mock_build, mock_get_creds):
    mock_get_creds.return_value = MagicMock()
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_service.spreadsheets().values().append().execute.return_value = {"updates": {"updatedRows": 0}}

    from google_sheets import append_rows
    result = append_rows("test_sheet_id", [])
    assert result["updates"]["updatedRows"] == 0


@patch("google_sheets.get_credentials")
def test_append_rows_credentials_fail(mock_get_creds):
    mock_get_creds.side_effect = FileNotFoundError("No credentials file")

    from google_sheets import append_rows
    with pytest.raises(Exception, match="Error de configuración"):
        append_rows("test_sheet_id", [["data"]])
