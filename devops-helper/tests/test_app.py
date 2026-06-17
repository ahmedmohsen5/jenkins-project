import tempfile
import unittest
from pathlib import Path

from app import STAGE_FLOW, create_app


class DevOpsHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test.db"
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE_PATH": str(db_path),
                "SEED_DEMO_DATA": False,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dashboard_loads(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"DevOps Cycle Helper", response.data)

    def test_can_add_and_advance_item(self) -> None:
        create_response = self.client.post(
            "/items",
            data={
                "service_name": "catalog-api",
                "environment": "staging",
                "stage": "Backlog",
                "status": "Planned",
                "owner": "ahmed",
                "reference_url": "http://localhost:8080/job/catalog-api/",
                "notes": "Ready for the next release train.",
            },
            follow_redirects=True,
        )
        self.assertEqual(create_response.status_code, 200)

        payload = self.client.get("/api/items").get_json()
        self.assertEqual(payload["count"], 1)
        item = payload["items"][0]
        self.assertEqual(item["service_name"], "catalog-api")

        advance_response = self.client.post(f"/items/{item['id']}/advance", follow_redirects=True)
        self.assertEqual(advance_response.status_code, 200)

        updated_payload = self.client.get("/api/items").get_json()
        self.assertEqual(updated_payload["items"][0]["stage"], STAGE_FLOW[1])

    def test_health_endpoint_returns_summary(self) -> None:
        self.client.post(
            "/items",
            data={
                "service_name": "ops-portal",
                "environment": "production",
                "stage": "Monitor",
                "status": "Healthy",
                "owner": "nora",
                "reference_url": "",
                "notes": "Stable after deployment.",
            },
        )

        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["tracked_services"], 1)
        self.assertEqual(payload["delivery_health"], 100)


if __name__ == "__main__":
    unittest.main()
