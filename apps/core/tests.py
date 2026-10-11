import json
from unittest.mock import patch

from django.db import OperationalError
from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase, TestCase

from .presentation import LegacyPresentationTextMiddleware, clean_legacy_text


class LegacyPresentationTextTests(SimpleTestCase):
    def test_known_legacy_markers_are_removed_from_api_text(self):
        self.assertEqual(clean_legacy_text("Ingeniería de Sistemas (datos ficticios)"), "Ingeniería de Sistemas")
        self.assertEqual(clean_legacy_text("Reglamento SPD de demostración · v1"), "Reglamento SPD · v1")

    def test_api_json_is_cleaned_recursively(self):
        request = RequestFactory().get("/api/v1/profile/", HTTP_ACCEPT="application/json")
        middleware = LegacyPresentationTextMiddleware(
            lambda _request: JsonResponse({"career": "Ingeniería de Sistemas (datos ficticios)",
                                           "activity": {"source": "Constancia sintética de seed_demo"}})
        )
        response = middleware(request)
        self.assertEqual(json.loads(response.content), {
            "career": "Ingeniería de Sistemas",
            "activity": {"source": "Registro de participación académica"},
        })


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
