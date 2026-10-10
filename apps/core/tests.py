from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase, TestCase


class LivenessEndpointTests(SimpleTestCase):
    def test_liveness_does_not_require_database(self):
        response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


class ReadinessEndpointTests(TestCase):
    def test_readiness_reports_database_connection(self):
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "connected"})

    @patch("apps.core.views.connection.cursor", side_effect=OperationalError("database offline"))
    def test_readiness_returns_service_unavailable_when_database_is_down(self, _cursor):
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable", "database": "disconnected"})
