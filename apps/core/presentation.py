"""Presentation cleanup for labels left by earlier local seed versions."""

import json
import re


_REPLACEMENTS = (
    ("(datos ficticios)", ""),
    ("Universidad Pública de El Alto (datos ficticios)", "Universidad Pública de El Alto"),
    ("Ingeniería de Sistemas (datos ficticios)", "Ingeniería de Sistemas"),
    ("Reglamento SPD de demostración · v1", "Reglamento SPD · v1"),
    ("Encuesta académica de demostración", "Experiencia académica en Programación I"),
    ("Hecho ficticio para demostrar el libro de méritos propios en E07.", "Actividad académica registrada con respaldo documental."),
    ("Mentoría ficticia aprobada como origen de una transferencia de demostración.", "Mentoría entre pares registrada y revisada."),
    ("Actividad ficticia aprobada para recorrer la solicitud de transferencia E08.", "Mentoría entre pares registrada y revisada."),
    ("Constancia sintética de seed_demo", "Registro de participación académica"),
    ("Constancia sintética de mentoría entre pares", "Registro de mentoría académica"),
    ("Apoyo ficticio para estudiantes que desarrollan proyectos de investigación aplicada en Ingeniería de Sistemas.", "Apoyo a estudiantes que desarrollan proyectos de investigación aplicada en Ingeniería de Sistemas."),
    ("Apoyo económico de demostración, mentoría académica y acceso a laboratorio.", "Apoyo económico, mentoría académica y acceso a laboratorio."),
    ("Proyecto demostrativo validado para comprobar requisitos de una beca ficticia.", "Proyecto validado de investigación aplicada y análisis de datos."),
    ("Aplicación académica de muestra para controlar equipos y préstamos del laboratorio.", "Aplicación académica para controlar equipos y préstamos del laboratorio."),
    ("Seminario académico de muestra", "Seminario de arquitectura de software"),
    ("Reconocimiento académico de muestra", "Reconocimiento por rendimiento académico"),
    ("Proyecto destacado de muestra", "Proyecto destacado de automatización"),
    ("Colaboración validada para reconocimiento E08", "Colaboración validada en proyecto"),
    ("Mentoría entre pares para transferencia de muestra", "Mentoría entre pares en laboratorio"),
    ("Mentoría entre pares para prueba E08", "Mentoría entre pares en laboratorio"),
    ("Colaboración en investigación de muestra", "Colaboración en investigación aplicada"),
    ("Registro de publicación del reglamento ficticio inicial", "Registro de publicación del reglamento SPD inicial"),
    ("Publicación del reglamento ficticio inicial", "Publicación del reglamento SPD inicial"),
    ("Creación de campaña estructurada de demostración.", "Creación de campaña de evaluación estructurada."),
    ("Aporte corroborado en el registro ficticio de demostración.", "Aporte corroborado en el registro académico de colaboración."),
    ("Cuenta sintética para demostración local", "Asignación de estudiante en Ingeniería de Sistemas"),
    ("Coordinación sintética para recorrido local de oportunidades", "Asignación de coordinación en Ingeniería de Sistemas"),
    ("Carga de nota ficticia para prueba local", "Carga académica inicial"),
    ("Carga ficticia verificada para el recorrido E07", "Registro académico inicial"),
)


def clean_legacy_text(value):
    """Replace known seed-era wording without changing stored audit or ledger records."""
    if not isinstance(value, str):
        return value
    result = value
    for old, new in _REPLACEMENTS:
        result = result.replace(old, new)
    result = re.sub(r"\b(?:ficticios?|ficticias?|sintéticos?|sintéticas?)\b|\bde demostración\b", "", result, flags=re.IGNORECASE)
    result = " ".join(result.split())
    result = result.replace("( )", "").replace("(  )", "")
    return result.strip(" ,;·")


def _clean_tree(value):
    if isinstance(value, dict):
        return {key: _clean_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_tree(item) for item in value]
    if isinstance(value, str):
        return clean_legacy_text(value)
    return value


class LegacyPresentationTextMiddleware:
    """Clean legacy local seed labels from API JSON while preserving stored history."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/api/") or "application/json" not in response.get("Content-Type", ""):
            return response
        try:
            payload = json.loads(response.content)
        except (TypeError, ValueError, UnicodeDecodeError):
            return response
        response.content = json.dumps(_clean_tree(payload), ensure_ascii=False).encode("utf-8")
        return response
