import unittest
from unittest.mock import MagicMock, patch
from src.ingestion.google_health_client import (
    parse_google_fit_dataset_points,
    fetch_and_store_google_health_data
)
from src.db.connection import get_db_connection, init_db

class TestGoogleHealthIngestion(unittest.TestCase):
    def test_parse_google_fit_dataset_points(self):
        sample_dataset = {
            "point": [
                {
                    "dataTypeName": "com.google.weight",
                    "value": [{"fpVal": 64.9}]
                },
                {
                    "dataTypeName": "com.google.body.fat.percentage",
                    "value": [{"fpVal": 17.2}]
                }
            ]
        }
        res = parse_google_fit_dataset_points(sample_dataset)
        self.assertEqual(res.get("weight_kg"), 64.9)
        self.assertEqual(res.get("body_fat_pct"), 17.2)

    @patch("src.ingestion.google_health_client.get_google_fit_credentials")
    @patch("src.ingestion.google_health_client.build")
    @patch("src.ingestion.google_health_client.get_garmin_client")
    def test_fetch_and_store_google_health_data(self, mock_get_garmin, mock_build, mock_get_creds):
        # Setup mocks
        mock_creds = MagicMock()
        mock_get_creds.return_value = mock_creds

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_garmin = MagicMock()
        mock_get_garmin.return_value = mock_garmin

        mock_agg_call = MagicMock()
        mock_service.users().dataset().aggregate.return_value = mock_agg_call
        mock_agg_call.execute.return_value = {
            "bucket": [
                {
                    "dataset": [
                        {
                            "point": [
                                {
                                    "dataTypeName": "com.google.weight",
                                    "value": [{"fpVal": 64.9}]
                                },
                                {
                                    "dataTypeName": "com.google.body.fat.percentage",
                                    "value": [{"fpVal": 17.2}]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Run ingestion
        target_date = "2026-09-19"
        res = fetch_and_store_google_health_data(target_date, verbose=False)

        # Assertions
        self.assertIsNotNone(res)
        self.assertEqual(res.get("weight_kg"), 64.9)
        self.assertEqual(res.get("body_fat_pct"), 17.2)

        # Verify DB entry
        init_db()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT weight_kg, body_fat_pct FROM daily_metrics WHERE date = ?", (target_date,))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 64.9)
            self.assertEqual(row[1], 17.2)

if __name__ == "__main__":
    unittest.main()
