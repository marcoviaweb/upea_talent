const auditActions: Record<string, string> = {
  "evidence.submitted": "Evidencia presentada",
  "evidence.resubmitted": "Evidencia reenviada",
  "evidence.approve": "Evidencia aprobada",
  "evidence.observe": "Evidencia observada",
  "evidence.reject": "Evidencia rechazada",
  "evidence.revoked": "Evidencia revocada",
  "evidence.admin_recorded": "Mérito registrado por administración",
  "grade.recorded": "Nota académica registrada",
  "development.project_submitted": "Proyecto enviado a revisión",
  "trajectory.development_submitted": "Registro enviado a revisión",
  "trajectory.development_saved": "Borrador de trayectoria guardado",
  "trajectory.development_validated": "Registro de trayectoria validado",
  "trajectory.development_observed": "Registro de trayectoria observado",
  "trajectory.grade_corrected": "Nota académica rectificada",
  "spd.regulation_published": "Reglamento SPD publicado",
  "opportunity.published": "Convocatoria publicada",
  "opportunity.closed": "Convocatoria cerrada",
  "opportunity.cancelled": "Convocatoria cancelada",
  "opportunity.resolved": "Convocatoria resuelta",
  "opportunity.application_submitted": "Postulación presentada",
  "opportunity.application_decided": "Postulación resuelta",
  "opportunity.application_withdrawn": "Postulación retirada",
  "transfer.submitted": "Transferencia solicitada",
  "transfer.approved": "Transferencia aprobada",
  "transfer.rejected": "Transferencia rechazada",
  "transfer.cancelled": "Transferencia cancelada",
  "transfer.risk_resolved": "Alerta de transferencia resuelta",
  "evaluation.campaign_created": "Encuesta creada",
  "evaluation.campaign_superseded": "Versión anterior de encuesta reemplazada",
  "evaluation.campaign_opened": "Encuesta abierta",
  "evaluation.campaign_closed": "Encuesta cerrada",
  "evaluation.results_published": "Resultados de encuesta publicados",
  "evaluation.campaign_cancelled": "Encuesta cancelada",
  "support.rule_published": "Regla de acompañamiento publicada",
  "support.alert_created": "Alerta de acompañamiento generada",
  "support.case_opened": "Caso de acompañamiento abierto",
  "support.action_recorded": "Acción de acompañamiento registrada",
  "support.case_closed": "Caso de acompañamiento cerrado",
  "support.case_discarded": "Caso de acompañamiento descartado",
  "role.granted": "Rol asignado",
  "role.revoked": "Rol retirado",
  "auth.login_succeeded": "Inicio de sesión correcto",
  "auth.login_failed": "Intento de acceso fallido",
  "auth.logout": "Cierre de sesión",
  "api.operation_failed": "Operación no completada",
  "admin.period_created": "Periodo académico creado",
  "admin.course_created": "Asignatura creada",
  "admin.offering_created": "Grupo académico creado",
  "admin.enrollment_created": "Matrícula registrada",
  "admin.student_created": "Estudiante dado de alta",
  "academics.grade_recorded": "Nota académica registrada",
  "academics.grade_corrected": "Nota académica rectificada",
};

const opportunityStatuses: Record<string, string> = {
  draft: "Borrador", published: "Publicada", closed: "Cerrada", resolved: "Resuelta", cancelled: "Cancelada",
};

const applicationStatuses: Record<string, string> = {
  submitted: "Enviada", in_review: "En revisión", selected: "Seleccionada",
  not_selected: "No seleccionada", withdrawn: "Retirada",
};

const requirementStatuses: Record<string, string> = {
  meets: "Cumple", does_not_meet: "No cumple", insufficient: "Datos insuficientes",
};

const roles: Record<string, string> = {
  student: "Estudiante", teacher: "Docente", auxiliary: "Auxiliar", coordinator: "Coordinación",
  career_admin: "Administración de carrera", institution_admin: "Administración institucional",
  evidence_reviewer: "Revisión de evidencias", opportunity_owner: "Responsable de oportunidad",
  superuser: "Administración del sistema",
};

const objectTypes: Record<string, string> = {
  "activities.activity": "Evidencia", "activities.regulation": "Reglamento SPD",
  "academics.graderecord": "Nota académica", "accounts.roleassignment": "Asignación de rol",
  "evaluations.evaluationcampaign": "Encuesta", "opportunities.opportunityversion": "Convocatoria",
  "opportunities.application": "Postulación", "opportunities.applicationdecision": "Resolución de postulación",
  "profiles.studentproject": "Proyecto", "profiles.studentskill": "Habilidad",
  "support.supportalert": "Alerta de acompañamiento", "support.supportcase": "Caso de acompañamiento",
  "support.supportaction": "Acción de acompañamiento", "transfers.transferrequest": "Solicitud de transferencia",
  "transfers.transferriskalert": "Alerta de transferencia", "transfers.transferadjustment": "Ajuste de transferencia",
  "http.request": "Solicitud del sistema", "accounts.user": "Cuenta institucional",
  "academics.academicperiod": "Periodo académico", "academics.course": "Asignatura",
  "academics.courseoffering": "Grupo académico", "academics.enrollment": "Matrícula",
  "academics.studentprofile": "Perfil de estudiante",
};

const scopes: Record<string, string> = {
  career: "Carrera", institution: "Institución", group: "Grupo", global: "General",
};

export function auditActionLabel(action: string) {
  return auditActions[action] ?? "Otra acción registrada";
}

export function auditActionFilterValue(query: string) {
  const normalized = query.trim().toLocaleLowerCase("es-BO");
  if (!normalized) return query;
  const match = Object.entries(auditActions).find(([code, label]) =>
    code.toLocaleLowerCase("es-BO") === normalized || label.toLocaleLowerCase("es-BO").includes(normalized),
  );
  return match?.[0] ?? query;
}

export function auditRoleScopeLabel(value: string) {
  if (value === "Autenticación") return "Evento de autenticación";
  return value.split(", ").map((assignment) => {
    const [role, scope] = assignment.split(" · ");
    return `${roles[role] ?? "Personal autorizado"} · ${scope ?? "UPEA"}`;
  }).join(", ");
}

export function auditObjectTypeLabel(value: string) {
  return objectTypes[value] ?? "Registro académico";
}

export function auditScopeLabel(value: string) {
  const [scope, identifier] = value.split(":", 2);
  const label = scopes[scope] ?? "Ámbito";
  return identifier ? `${label} · ${identifier}` : label;
}

export function auditResultLabel(value: string) {
  return value === "success" ? "Correcto" : value === "failure" ? "No completado" : "Registrado";
}

export function opportunityStatusLabel(value: string) {
  return opportunityStatuses[value] ?? "Estado actualizado";
}

export function applicationStatusLabel(value: string) {
  return applicationStatuses[value] ?? "Estado actualizado";
}

export function requirementStatusLabel(value: string) {
  return requirementStatuses[value] ?? "Sin determinar";
}
