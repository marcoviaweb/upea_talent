import { lazy, Suspense, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, NavLink, Navigate, Outlet, Route, Routes, useNavigate, useOutletContext, useParams } from "react-router-dom";
import {
  ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, BookOpenCheck, BriefcaseBusiness, CalendarDays,
  Check, CheckCircle2, ChevronDown, FileBarChart2, GraduationCap, LayoutDashboard,
  Lightbulb, LoaderCircle, LockKeyhole, LogOut, Menu, MessageSquareText, Plus, Search, ShieldCheck, Sparkles, UserRound,
  UsersRound, X, HandHeart,
} from "lucide-react";
import { api, dateLabel, errorMessage, signIn, signOut, type DevelopmentRecord, type Enrollment, type HomeData, type Profile } from "./api";
import E06Page from "./features/e06/E06Page";
import E07Page from "./features/e07/E07Page";
import E09Page from "./features/e09/E09Page";
import E10Page from "./features/e10/E10Page";
const E11Page = lazy(() => import("./features/e11/E11Page"));
const StudentProgressCharts = lazy(() => import("./components/StatisticalCharts").then((module) => ({ default: module.StudentProgressCharts })));

function Spinner({ label = "Cargando tu espacio" }: { label?: string }) {
  return <div className="loading-state" role="status"><LoaderCircle size={20} className="spin" /><span>{label}</span></div>;
}

function StatusPill({ status, label }: { status: string; label: string }) {
  const icons: Record<string, ReactNode> = {
    validated: <CheckCircle2 size={14} />, in_review: <span className="status-dot" />, needs_changes: <ArrowDownRight size={14} />,
    declared: <Lightbulb size={14} />, active: <span className="status-dot" />,
  };
  return <span className={`status-pill status-${status}`}>{icons[status]}{label}</span>;
}

function App() {
  const [home, setHome] = useState<HomeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const reload = () => api<HomeData>("/api/v1/home/").then((data) => { setHome(data); setError(""); }).catch((err) => {
    if (err instanceof Error && ["Authentication credentials", "credenciales", "No se proporcionaron credenciales"].some((term) => err.message.includes(term))) navigate("/acceso/");
    setError(errorMessage(err));
  }).finally(() => setLoading(false));

  useEffect(() => {
    if (window.location.pathname === "/") navigate("/acceso/", { replace: true });
    else if (window.location.pathname !== "/acceso/") void reload();
    else setLoading(false);
  }, []);

  async function logout() {
    try { await signOut(); } finally { setHome(null); navigate("/acceso/"); }
  }

  return <Routes>
    <Route path="/" element={<Navigate to="/acceso/" replace />} />
    <Route path="/acceso/" element={<LoginPage onLogin={(data) => { setHome(data); navigate("/trayectoria/"); }} />} />
    <Route element={<AppShell home={home} loading={loading} error={error} reload={reload} onLogout={logout} />}>
      <Route path="/trayectoria/" element={<Dashboard />} />
      <Route path="/trayectoria/evidencias/" element={<EvidencePage />} />
      <Route path="/trayectoria/puntos/" element={<PointsPage />} />
      <Route path="/trayectoria/transferencias/" element={<EvidencePage />} />
      <Route path="/trayectoria/oportunidades/" element={<E07Page />} />
      <Route path="/trayectoria/evaluaciones/" element={<E09Page />} />
      <Route path="/trayectoria/acompanamiento/" element={<E10Page />} />
      <Route path="/trayectoria/gestion/" element={<Suspense fallback={<Spinner label="Preparando gráficos e informes" />}><E11Page /></Suspense>} />
      <Route path="/trayectoria/matricula/:enrollmentId/" element={<ProfilePage />} />
      <Route path="/trayectoria/grupo/:offeringId/" element={<RosterPage />} />
      <Route path="/trayectoria/matricula/:enrollmentId/nuevo/:recordType/" element={<DevelopmentFormPage />} />
      <Route path="/trayectoria/matricula/:enrollmentId/editar/:recordType/:recordId/" element={<DevelopmentFormPage />} />
      <Route path="*" element={<Navigate to="/trayectoria/" replace />} />
    </Route>
  </Routes>;
}

function EvidencePage() { const { home } = useOutletContext<{ home: HomeData }>(); return <E06Page enrollments={home.enrollments} canRegisterVerifiedActivity={home.canRegisterVerifiedActivity} />; }
function PointsPage() { const { home } = useOutletContext<{ home: HomeData }>(); return <E06Page enrollments={home.enrollments} canRegisterVerifiedActivity={home.canRegisterVerifiedActivity} />; }

function LoginPage({ onLogin }: { onLogin: (data: HomeData) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await signIn(username, password); const home = await api<HomeData>("/api/v1/home/"); onLogin(home); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <main id="main-content" className="login-layout">
    <section className="login-story">
      <div className="brand-lockup"><span className="brand-mark"><GraduationCap size={25} /></span><span>UPEA <b>Talent+</b></span></div>
      <div className="story-copy"><span className="eyebrow light-eyebrow"><Sparkles size={14} /> PLATAFORMA ACADÉMICA</span><h1>Tu talento deja<br /><em>huella.</em></h1><p>Una visión completa de lo que aprendes, construyes y aportas durante tu formación profesional.</p>
        <div className="story-orbit orbit-one" /><div className="story-orbit orbit-two" />
      </div>
      <div className="story-foot"><span>Universidad Pública de El Alto</span><span>Formación · Experiencia · Futuro</span></div>
    </section>
    <section className="login-panel" aria-labelledby="login-title">
      <div className="login-mobile-brand"><span className="brand-mark"><GraduationCap size={22} /></span>UPEA <b>Talent+</b></div>
      <div className="login-form-wrap"><span className="eyebrow">BIENVENIDO DE NUEVO</span><h2 id="login-title">Ingresa a tu espacio</h2><p className="muted">Usa las credenciales de tu cuenta institucional.</p>
        <form className="login-form" onSubmit={submit}>
          <label htmlFor="username">Usuario</label><div className="input-wrap"><UserRound size={17} /><input id="username" name="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></div>
          <label htmlFor="password">Contraseña</label><div className="input-wrap"><LockKeyhole size={17} /><input id="password" name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
          {error && <p className="error-banner" role="alert">{error}</p>}
          <button className="button button-primary button-login" disabled={busy}>{busy ? <><LoaderCircle className="spin" size={17} /> Verificando…</> : <>Iniciar sesión <ArrowRight size={17} /></>}</button>
        </form><p className="security-hint"><ShieldCheck size={16} /> Conexión protegida · acceso según tu rol académico</p>
      </div><div className="login-footer">© UPEA Talent+ <span>¿Necesitas ayuda? Contacta a tu coordinación académica.</span></div>
    </section>
  </main>;
}

function AppShell({ home, loading, error, reload, onLogout }: { home: HomeData | null; loading: boolean; error: string; reload: () => void; onLogout: () => void }) {
  const [mobileNav, setMobileNav] = useState(false);
  const navigate = useNavigate();
  useEffect(() => { if (!loading && error.toLowerCase().includes("credenciales")) navigate("/acceso/"); }, [loading, error]);
  const initials = (home?.user.name ?? "U").split(" ").slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  if (loading) return <Spinner />;
  if (!home) return <main className="unauthorized"><div className="empty-icon"><LockKeyhole /></div><h1>Tu espacio requiere una cuenta</h1><p>{error || "Inicia sesión con tu cuenta institucional para continuar."}</p><Link className="button button-primary" to="/acceso/">Ir al acceso</Link></main>;
  return <div className="app-frame">
    <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
      <Link className="brand-lockup sidebar-brand" to="/trayectoria/"><span className="brand-mark"><GraduationCap size={23} /></span><span>UPEA <b>Talent+</b></span></Link>
      <div className="sidebar-caption">TU ESPACIO</div>
      <nav className="primary-nav" aria-label="Navegación principal">
        <NavLink to="/trayectoria/" end className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`} onClick={() => setMobileNav(false)}><LayoutDashboard size={18} />Resumen de trayectoria</NavLink>
        <NavLink to="/trayectoria/evidencias/" className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`} onClick={() => setMobileNav(false)}><ShieldCheck size={18} />Evidencias y SPD</NavLink>
        <NavLink to="/trayectoria/oportunidades/" className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`} onClick={() => setMobileNav(false)}><BriefcaseBusiness size={18} />Oportunidades</NavLink>
        <NavLink to="/trayectoria/evaluaciones/" className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`} onClick={() => setMobileNav(false)}><MessageSquareText size={18} />Evaluación académica</NavLink>
        <NavLink to="/trayectoria/acompanamiento/" className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`} onClick={() => setMobileNav(false)}><HandHeart size={18} />Acompañamiento</NavLink>
        <NavLink to="/trayectoria/gestion/" className={({ isActive }) => `nav-item ${isActive ? "nav-active" : ""}`} onClick={() => setMobileNav(false)}><FileBarChart2 size={18} />Gestión y análisis</NavLink>
        {home.groups.length > 0 && <div className="nav-section"><span className="sidebar-caption">DOCENCIA</span>{home.groups.slice(0, 4).map((group) => <NavLink key={group.id} to={`/trayectoria/grupo/${group.id}/`} className={({ isActive }) => `nav-item nav-subitem ${isActive ? "nav-active" : ""}`} onClick={() => setMobileNav(false)}><UsersRound size={17} /><span className="nav-truncate">{group.course.code} · {group.group}</span></NavLink>)}</div>}
      </nav>
      <div className="sidebar-bottom"><div className="sidebar-version"><span className="version-dot" /> Portal académico · v1.0</div></div>
    </aside>
    {mobileNav && <button className="mobile-scrim" aria-label="Cerrar menú" onClick={() => setMobileNav(false)} />}
    <div className="workspace">
      <header className="topbar"><button className="mobile-menu" aria-label="Abrir menú" onClick={() => setMobileNav(true)}><Menu /></button><div className="breadcrumbs-top"><span>Mi espacio</span><ChevronDown size={14} /><span className="crumb-current">Trayectoria</span></div><div className="topbar-right"><div className="topbar-context"><span className="online-dot" /> Ciclo académico activo</div><div className="topbar-divider" /><div className="user-menu"><span className="avatar avatar-small">{initials}</span><span className="user-name">{home.user.name}</span><button className="icon-button logout-button" onClick={onLogout} aria-label="Cerrar sesión" title="Cerrar sesión"><LogOut size={17} /></button></div></div></header>
      <main id="main-content" className="main-content" tabIndex={-1}>
        {error && <div className="toast-error" role="alert"><span>{error}</span><button onClick={reload} className="text-button">Reintentar</button></div>}
        <Outlet context={{ home, reload }} />
      </main>
      <footer className="app-footer"><span>UPEA Talent+ <span className="footer-sep">·</span> Universidad Pública de El Alto</span><span>Tu trayectoria, en un solo lugar.</span></footer>
    </div>
  </div>;
}

function Dashboard() {
  const outlet = useOutletContext<{ home: HomeData | null; reload: () => void }>();
  const [home, setHome] = useState(outlet.home);
  const [loading, setLoading] = useState(!outlet.home);
  const [filter, setFilter] = useState("");
  useEffect(() => {
    if (outlet.home) { setHome(outlet.home); setLoading(false); }
    else api<HomeData>("/api/v1/home/").then(setHome).catch(() => setHome(null)).finally(() => setLoading(false));
  }, [outlet.home]);
  if (loading) return <Spinner />;
  if (!home) return <ErrorPanel error="No se pudieron recuperar los datos de tu espacio." retry={outlet.reload} />;
  const greeting = new Intl.DateTimeFormat("es-BO", { weekday: "long", day: "numeric", month: "long", timeZone: "America/La_Paz" }).format(new Date());
  const filtered = home.enrollments.filter((e) => `${e.career.name} ${e.period.name}`.toLowerCase().includes(filter.toLowerCase()));
  const teacherHome = home.enrollments.length === 0 && home.groups.length > 0;
  return <div className="page-stack">
    <section className="welcome-hero">
      <div className="welcome-copy"><span className="eyebrow hero-eyebrow"><CalendarDays size={14} /> {greeting}</span><h1>Hola, {home.user.name.split(" ")[0]}<span className="wave">.</span></h1><p>{teacherHome ? "Aquí tienes los grupos académicos y las tareas de revisión a tu cargo." : "Este es el recorrido que estás construyendo. Explora tu avance y sigue sumando experiencias."}</p><div className="hero-note"><span className="hero-note-icon"><Sparkles size={15} /></span><span><strong>{teacherHome ? "Tu espacio docente está listo." : "Todo lo que aprendes cuenta."}</strong> {teacherHome ? "Consulta las trayectorias de tus grupos y revisa las actividades asignadas." : "Actualiza tu trayectoria a medida que avanzas."}</span></div></div>
      <div className="hero-art" aria-hidden="true"><div className="hero-art-ring ring-a" /><div className="hero-art-ring ring-b" /><div className="hero-art-ring ring-c" /><div className="hero-art-core"><GraduationCap size={42} strokeWidth={1.4} /></div><span className="art-star star-a">✳</span><span className="art-star star-b">✦</span><span className="art-orbit-label label-a">APRENDE</span><span className="art-orbit-label label-b">CREA</span><span className="art-orbit-label label-c">CRECE</span></div>
    </section>
    {home.enrollments.length > 0 && <><div className="section-title-row"><div><span className="eyebrow">TU HISTORIAL ACADÉMICO</span><h2>Mis matrículas</h2><p>Selecciona un periodo para explorar tu trayectoria.</p></div><span className="record-count"><span>{home.enrollments.length.toString().padStart(2, "0")}</span> periodos</span></div>
    {home.enrollments.length > 3 && <div className="search-row"><Search size={17} /><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Buscar carrera o periodo" aria-label="Buscar carrera o periodo" /></div>}
    {filtered.length ? <div className="enrollment-grid">{filtered.map((enrollment, index) => <EnrollmentCard key={enrollment.id} enrollment={enrollment} index={index} />)}</div> : <EmptyState icon={<BookOpenCheck />} title="No encontramos matrículas" body="Ajusta la búsqueda o consulta con tu coordinación." />}</>}
    {home.enrollments.length > 0 && (home.progress?.length ?? 0) > 0 && <section className="student-progress"><div className="section-title-row compact-title"><div><span className="eyebrow">AVANCE PERSONAL</span><h2>Mi progreso por periodo</h2><p>Promedio verificado, puntos SPD y evidencias registradas en tus matrículas.</p></div></div><Suspense fallback={<div className="loading-state" role="status">Preparando tus gráficos…</div>}><StudentProgressCharts periods={home.progress!}/></Suspense><div className="student-progress-grid">{home.progress!.map((item)=><article className="student-progress-card" key={`${item.label}-${item.detail}`}><div><strong>{item.label}</strong><span>{item.detail}</span></div><div className="student-progress-stats"><span><b>{item.average ?? "—"}</b>Promedio / 100</span><span><b>{item.points}</b>Puntos SPD</span><span><b>{item.validated}/{item.evidence}</b>Evidencias validadas</span></div>{item.average !== null && <div className="student-progress-track" role="img" aria-label={`Promedio verificado ${item.average} de 100`}><i style={{width:`${Math.min(100,Math.max(0,item.average))}%`}}/></div>}</article>)}</div></section>}
    {home.groups.length > 0 && <section className="teacher-section"><div className="section-title-row compact-title"><div><span className="eyebrow">ESPACIO DOCENTE</span><h2>Grupos asignados</h2><p>Accede a las trayectorias de los estudiantes de tus grupos.</p></div><span className="record-count"><span>{home.groups.length.toString().padStart(2, "0")}</span> grupos</span></div><div className="group-card-grid">{home.groups.map((group) => <Link key={group.id} className="group-card" to={`/trayectoria/grupo/${group.id}/`}><span className="group-icon"><UsersRound size={19} /></span><span className="group-info"><strong>{group.course.name}</strong><small>{group.course.code} · {group.period} · Grupo {group.group}</small></span><span className="group-students">{group.studentCount}<small>estudiantes</small></span><ArrowRight className="group-arrow" size={17} /></Link>)}</div></section>}
  </div>;
}


function EnrollmentCard({ enrollment, index }: { enrollment: Enrollment; index: number }) {
  return <article className={`enrollment-card card-accent-${index % 3}`}><div className="enrollment-card-top"><span className="career-code">{enrollment.career.code}</span><StatusPill status={enrollment.status} label={enrollment.statusLabel} /></div><span className="period-index">PERIODO {String(enrollment.semester).padStart(2, "0")}</span><h3>{enrollment.career.name}</h3><p className="period-title">{enrollment.period.name}</p><div className="enrollment-card-foot"><span><CalendarDays size={15} /> {dateLabel(enrollment.period.startsOn)}</span><Link className="card-arrow" to={`/trayectoria/matricula/${enrollment.id}/`} aria-label={`Ver trayectoria de ${enrollment.period.name}`}><ArrowUpRight size={19} /></Link></div><div className="card-watermark" aria-hidden="true"><GraduationCap size={91} /></div></article>;
}

function ProfilePage() {
  const { enrollmentId = "" } = useParams();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const load = () => api<Profile>(`/api/v1/enrollments/${enrollmentId}/`).then((data) => { setProfile(data); setError(""); }).catch((err) => setError(errorMessage(err))).finally(() => setLoading(false));
  useEffect(() => { setLoading(true); setProfile(null); setError(""); void load(); }, [enrollmentId]);
  if (loading) return <Spinner label="Cargando trayectoria" />;
  if (error || !profile) return <ErrorPanel error={error || "No se encontró la trayectoria."} retry={load} />;
  const { enrollment, student } = profile;
  const initials = student.name.split(" ").slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  const projects = profile.projects.filter((record) => `${record.title} ${record.description}`.toLowerCase().includes(query.toLowerCase()));
  const skills = profile.skills.filter((record) => `${record.name} ${record.description}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="page-stack">
    <div className="breadcrumb-line"><Link to="/trayectoria/">Mis matrículas</Link><ArrowRight size={13} /><span>{enrollment.period.name}</span></div>
    <section className="profile-banner"><div className="profile-avatar">{initials}</div><div className="profile-person"><span className="eyebrow">{enrollment.career.code} <span className="eyebrow-dot">·</span> {enrollment.period.name}</span><h1>{student.name}</h1><p><span>N.º {student.studentNumber}</span><span className="person-sep" />{enrollment.semester}.º semestre</p></div><div className="profile-state"><StatusPill status={enrollment.status} label={enrollment.statusLabel} /><span>Vigencia {dateLabel(enrollment.period.startsOn)} — {dateLabel(enrollment.period.endsOn)}</span></div></section>
    <div className="metric-grid">
      <MetricCard icon={<BookOpenCheck size={18} />} label="Notas verificadas" value={String(profile.grades.length).padStart(2, "0")} caption="En este periodo" tone="blue" />
      <MetricCard icon={<GraduationCap size={18} />} label="Media simple" value={profile.average ?? "—"} caption={profile.average ? "No ponderada · informativa" : "Sin datos verificados"} tone="mint" />
      <MetricCard icon={<BriefcaseBusiness size={18} />} label="Proyectos validados" value={String(profile.counts.validatedProjects).padStart(2, "0")} caption={`${profile.projects.length} en total`} tone="amber" />
      <MetricCard icon={<Lightbulb size={18} />} label="Habilidades validadas" value={String(profile.counts.validatedSkills).padStart(2, "0")} caption={`${profile.skills.length} en total`} tone="violet" />
    </div>
    <section className="content-section"><div className="section-title-row section-title-tight"><div><span className="eyebrow">RENDIMIENTO</span><h2>Historial académico</h2><p>Notas de solo lectura, visibles después de su verificación.</p></div><span className="verified-label"><ShieldCheck size={15} /> Verificado</span></div>
      {profile.grades.length ? <div className="table-shell"><table className="data-table"><thead><tr><th>Asignatura</th><th>Periodo / grupo</th><th>Nota</th><th>Resultado</th><th>Verificada por</th></tr></thead><tbody>{profile.grades.map((grade) => <tr key={grade.id}><td data-label="Asignatura"><strong>{grade.course}</strong><small>{grade.courseCode}</small></td><td data-label="Periodo / grupo">{grade.period}<small>Grupo {grade.group}</small></td><td data-label="Nota"><strong className="grade-value">{grade.value}<small> / {grade.scale}</small></strong>{grade.correctsValue && <small>Rectifica {grade.correctsValue}</small>}</td><td data-label="Resultado"><span className={`result-pill ${grade.passed ? "result-pass" : "result-fail"}`}><span />{grade.passed ? "Aprobada" : "No aprobada"}</span></td><td data-label="Verificada por">{grade.verifiedBy}<small>{dateLabel(grade.verifiedAt)}</small></td></tr>)}</tbody></table></div> : <EmptyState icon={<BookOpenCheck />} title="Aún no hay notas verificadas" body="Las calificaciones aparecerán cuando hayan sido revisadas y confirmadas." compact />}
      <p className="footnote"><ShieldCheck size={14} /> La media es simple, no ponderada y solo informativa. Las correcciones conservan el historial.</p>
    </section>
    <section className="content-section"><div className="section-title-row section-title-tight"><div><span className="eyebrow">FORMACIÓN ACTUAL</span><h2>Asignaturas y grupos</h2><p>Materias inscritas en este periodo académico.</p></div><span className="subtle-count">{profile.courses.length} asignaturas</span></div><div className="subject-row">{profile.courses.length ? profile.courses.map((course) => <div className="subject-chip" key={`${course.code}-${course.group}`}><span className="subject-code">{course.code}</span><span>{course.name}</span><small>Grupo {course.group}</small></div>) : <p className="muted">Esta matrícula aún no tiene asignaturas asociadas.</p>}</div></section>
    <section className="content-section"><div className="section-title-row section-title-tight"><div><span className="eyebrow">EXPERIENCIA APLICADA</span><h2>Proyectos</h2><p>Experiencias y soluciones que estás desarrollando.</p></div>{profile.canDeclare && <Link className="button button-primary" to={`/trayectoria/matricula/${enrollment.id}/nuevo/project/`}><Plus size={17} /> Añadir proyecto</Link>}</div>
      {profile.projects.length > 2 && <div className="section-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar en tu trayectoria" aria-label="Buscar proyectos y habilidades" /></div>}
      {projects.length ? <div className="project-grid">{projects.map((project) => <RecordCard key={project.id} record={project} onReview={load} />)}</div> : <EmptyState icon={<BriefcaseBusiness />} title="Aquí empieza tu experiencia" body={profile.canDeclare ? "Registra proyectos académicos, personales o colaborativos y envíalos a revisión." : "Los proyectos que registres aparecerán en esta sección."} action={profile.canDeclare ? <Link className="text-link" to={`/trayectoria/matricula/${enrollment.id}/nuevo/project/`}>Registrar primer proyecto <ArrowRight size={15} /></Link> : undefined} compact />}
    </section>
    <section className="content-section"><div className="section-title-row section-title-tight"><div><span className="eyebrow">CAPACIDADES</span><h2>Habilidades</h2><p>Conocimientos y capacidades que forman parte de tu perfil.</p></div>{profile.canDeclare && <Link className="button button-secondary" to={`/trayectoria/matricula/${enrollment.id}/nuevo/skill/`}><Plus size={17} /> Añadir habilidad</Link>}</div>
      {skills.length ? <div className="skill-grid">{skills.map((skill) => <RecordCard key={skill.id} record={skill} onReview={load} />)}</div> : <EmptyState icon={<Lightbulb />} title="Haz visibles tus capacidades" body={profile.canDeclare ? "Agrega habilidades y niveles para completar tu perfil profesional." : "Las habilidades declaradas se mostrarán aquí."} action={profile.canDeclare ? <Link className="text-link" to={`/trayectoria/matricula/${enrollment.id}/nuevo/skill/`}>Añadir una habilidad <ArrowRight size={15} /></Link> : undefined} compact />}
    </section>
  </div>;
}

function MetricCard({ icon, label, value, caption, tone }: { icon: ReactNode; label: string; value: string; caption: string; tone: string }) {
  return <article className="metric-card"><span className={`metric-icon metric-${tone}`}>{icon}</span><span className="metric-label">{label}</span><strong className="metric-value">{value}</strong><span className="metric-caption">{caption}</span><ArrowUpRight className="metric-spark" size={15} /></article>;
}

function RecordCard({ record, onReview }: { record: DevelopmentRecord; onReview: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const isProject = record.type === "project";
  async function review(outcome: "approve" | "observe") {
    setBusy(true); setError("");
    try { await api(`/api/v1/records/${record.type}/${record.id}/review/`, { method: "POST", body: JSON.stringify({ outcome, note }) }); onReview(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <article className={`record-card ${isProject ? "project-card" : "skill-card"}`}>
    <div className="record-card-head"><span className={`record-icon ${isProject ? "record-project" : "record-skill"}`}>{isProject ? <BriefcaseBusiness size={17} /> : <Lightbulb size={17} />}</span><StatusPill status={record.status} label={record.statusLabel} /></div>
    <h3>{isProject ? record.title : record.name}</h3>
    {!isProject && record.proficiencyLabel && <span className="skill-level">{record.proficiencyLabel}</span>}
    <p className="record-description">{record.description || "Sin descripción adicional."}</p>
    {isProject && <div className="project-meta"><span><UserRound size={14} /> {record.role}</span>{record.startedOn && <span><CalendarDays size={14} /> {dateLabel(record.startedOn)}{record.completedOn ? ` — ${dateLabel(record.completedOn)}` : ""}</span>}</div>}
    {record.status === "validated" && <div className="validation-line"><Check size={15} /> Validado por {record.validatedBy} · {dateLabel(record.validatedAt)}</div>}
    {record.reviewNote && <div className="review-note"><strong>Observación:</strong> {record.reviewNote}</div>}
    {record.canEdit && <Link className="text-link record-edit" to={`/trayectoria/matricula/${useParams().enrollmentId}/editar/${record.type}/${record.id}/`}>Editar declaración <ArrowRight size={14} /></Link>}
    {!record.canEdit && record.status !== "validated" && <span className="submitted-line">Enviado {dateLabel(record.createdAt)}</span>}
    {error && <p className="inline-error" role="alert">{error}</p>}
    {!record.canEdit && record.status === "in_review" && <div className="review-controls"><label htmlFor={`note-${record.id}`}>Comentario <span>(requerido si solicitas cambios)</span></label><textarea id={`note-${record.id}`} value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} rows={2} /><div className="review-buttons"><button className="button button-secondary" disabled={busy || !note.trim()} onClick={() => void review("observe")}>Solicitar cambios</button><button className="button button-primary" disabled={busy} onClick={() => void review("approve")}>{busy ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />} Validar</button></div></div>}
  </article>;
}

function RosterPage() {
  const { offeringId = "" } = useParams();
  const [data, setData] = useState<{ offering: { course: string; code: string; period: string; group: string }; students: Array<{ enrollmentId: string; name: string; studentNumber: string; enrollmentStatus: string }> } | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const load = () => api<typeof data>(`/api/v1/groups/${offeringId}/`).then((result) => setData(result)).catch((err) => setError(errorMessage(err)));
  useEffect(() => { setData(null); setError(""); void load(); }, [offeringId]);
  if (!data && !error) return <Spinner label="Cargando grupo" />;
  if (!data) return <ErrorPanel error={error} retry={load} />;
  const students = data.students.filter((student) => `${student.name} ${student.studentNumber}`.toLowerCase().includes(query.toLowerCase()));
  return <div className="page-stack"><div className="breadcrumb-line"><Link to="/trayectoria/">Mis grupos</Link><ArrowRight size={13} /><span>{data.offering.code} · {data.offering.group}</span></div>
    <section className="group-hero"><span className="group-hero-icon"><UsersRound size={23} /></span><div><span className="eyebrow">ESPACIO DOCENTE · {data.offering.period}</span><h1>{data.offering.course}</h1><p>{data.offering.code} <span>·</span> Grupo {data.offering.group} <span>·</span> {data.students.length} estudiantes</p></div></section>
    <section className="content-section"><div className="section-title-row section-title-tight"><div><span className="eyebrow">LISTA DEL GRUPO</span><h2>Estudiantes</h2><p>Las trayectorias visibles corresponden únicamente a matrículas de este grupo asignado.</p></div><div className="roster-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar estudiante" aria-label="Buscar estudiante" /></div></div>
      {students.length ? <div className="table-shell"><table className="data-table roster-table"><thead><tr><th>Estudiante</th><th>N.º de registro</th><th>Matrícula</th><th /></tr></thead><tbody>{students.map((student) => <tr key={student.enrollmentId}><td data-label="Estudiante"><span className="roster-person"><span className="avatar avatar-tiny">{student.name.split(" ").slice(0, 2).map((p) => p[0]).join("").toUpperCase()}</span><strong>{student.name}</strong></span></td><td data-label="N.º de registro">{student.studentNumber}</td><td data-label="Matrícula"><StatusPill status="active" label={student.enrollmentStatus} /></td><td data-label="Acción"><Link className="table-action" to={`/trayectoria/matricula/${student.enrollmentId}/`}>Ver trayectoria <ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div> : <EmptyState icon={<UsersRound />} title="No hay estudiantes con ese criterio" body="Prueba con otro nombre o número de registro." compact />}
    </section></div>;
}

function DevelopmentFormPage() {
  const { enrollmentId = "", recordType = "project", recordId } = useParams();
  const isProject = recordType === "project";
  const navigate = useNavigate();
  const [initial, setInitial] = useState<DevelopmentRecord | null>(null);
  const [loading, setLoading] = useState(Boolean(recordId));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!recordId) return;
    setLoading(true); setInitial(null); setError("");
    api<Profile>(`/api/v1/enrollments/${enrollmentId}/`).then((profile) => {
      const found = [...profile.projects, ...profile.skills].find((record) => record.id === recordId);
      if (!found || !found.canEdit) throw new Error("Esta declaración ya no puede editarse.");
      setInitial(found);
    }).catch((err) => setError(errorMessage(err))).finally(() => setLoading(false));
  }, [enrollmentId, recordId]);
  if (loading) return <Spinner label="Preparando formulario" />;
  const title = isProject ? (recordId ? "Editar proyecto" : "Registrar un proyecto") : (recordId ? "Editar habilidad" : "Añadir una habilidad");
  async function submit(event: FormEvent<HTMLFormElement>, intent: "draft" | "submit") {
    event.preventDefault(); setBusy(true); setError("");
    const formData = new FormData(event.currentTarget);
    const fields: Record<string, FormDataEntryValue | string> = Object.fromEntries(formData.entries());
    fields.intent = intent;
    const url = recordId ? `/api/v1/enrollments/${enrollmentId}/records/${recordType}/${recordId}/` : `/api/v1/enrollments/${enrollmentId}/records/${recordType}/`;
    try {
      await api(url, { method: recordId ? "PATCH" : "POST", body: JSON.stringify(fields) });
      navigate(`/trayectoria/matricula/${enrollmentId}/`);
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <div className="page-stack form-page"><div className="breadcrumb-line"><Link to={`/trayectoria/matricula/${enrollmentId}/`}>Volver a trayectoria</Link><ArrowRight size={13} /><span>{title}</span></div>
    <section className="form-heading"><span className={`form-heading-icon ${isProject ? "record-project" : "record-skill"}`}>{isProject ? <BriefcaseBusiness size={23} /> : <Lightbulb size={23} />}</span><div><span className="eyebrow">{isProject ? "EXPERIENCIA APLICADA" : "PERFIL PROFESIONAL"}</span><h1>{title}</h1><p>{isProject ? "Describe lo que construiste, el problema que resolviste y tu aporte." : "Registra una capacidad y especifica el nivel que consideras haber alcanzado."}</p></div></section>
    {error && <p className="error-banner" role="alert">{error}</p>}
    <form className="declaration-form" onSubmit={(event) => void submit(event, "submit")}>
      {isProject ? <>
        <div className="form-section-label"><span>01</span><div><strong>Sobre el proyecto</strong><small>Cuéntanos qué hiciste y cuál fue tu contribución.</small></div></div>
        <div className="form-field"><label htmlFor="title">Nombre del proyecto <span>*</span></label><input id="title" name="title" maxLength={160} required defaultValue={initial?.title ?? ""} placeholder="Ej. Sistema de monitoreo de calidad del aire" /><small>Usa un nombre breve y descriptivo.</small></div>
        <div className="form-field"><label htmlFor="description">Descripción <span>*</span></label><textarea id="description" name="description" maxLength={3000} rows={5} required defaultValue={initial?.description ?? ""} placeholder="¿Qué necesidad aborda? ¿Qué construiste y qué resultados obtuviste?" /><small>Describe el objetivo, proceso y resultado en hasta 3000 caracteres.</small></div>
        <div className="form-field"><label htmlFor="role">Tu participación <span>*</span></label><input id="role" name="role" maxLength={120} required defaultValue={initial?.role ?? ""} placeholder="Ej. Diseño de base de datos y desarrollo backend" /></div>
        <div className="form-two-cols"><div className="form-field"><label htmlFor="started_on">Fecha de inicio</label><input id="started_on" name="started_on" type="date" defaultValue={initial?.startedOn ?? ""} /></div><div className="form-field"><label htmlFor="completed_on">Fecha de finalización</label><input id="completed_on" name="completed_on" type="date" defaultValue={initial?.completedOn ?? ""} /></div></div>
      </> : <>
        <div className="form-section-label"><span>01</span><div><strong>Sobre la habilidad</strong><small>Indica qué sabes hacer y en qué nivel te encuentras.</small></div></div>
        <div className="form-field"><label htmlFor="name">Habilidad <span>*</span></label><input id="name" name="name" maxLength={100} required defaultValue={initial?.name ?? ""} placeholder="Ej. Python, análisis de datos, liderazgo" /></div>
        <div className="form-field"><label htmlFor="proficiency_label">Nivel declarado</label><select id="proficiency_label" name="proficiency_label" defaultValue={initial?.proficiencyLabel ?? ""}><option value="">Selecciona un nivel</option><option>Básico</option><option>Intermedio</option><option>Avanzado</option><option>Especializado</option></select><small>El nivel es autodeclarado hasta que se revise.</small></div>
        <div className="form-field"><label htmlFor="description">Descripción o evidencia</label><textarea id="description" name="description" maxLength={500} rows={4} defaultValue={initial?.description ?? ""} placeholder="Describe brevemente cómo aplicas esta habilidad." /></div>
      </>}
      <div className="form-notice"><ShieldCheck size={17} /><p>Al enviarlo, una persona docente asignada revisará esta declaración. Tu nivel se mostrará como <strong>autodeclarado</strong> hasta que sea validado.</p></div>
      <div className="form-actions"><Link className="button button-ghost" to={`/trayectoria/matricula/${enrollmentId}/`}><ArrowLeft size={16} /> Cancelar</Link><div><button type="button" className="button button-secondary" disabled={busy} onClick={(event) => { const form = event.currentTarget.form; if (form) void submit({ preventDefault: () => {}, currentTarget: form } as FormEvent<HTMLFormElement>, "draft"); }}>Guardar borrador</button><button className="button button-primary" disabled={busy}>{busy ? <LoaderCircle size={16} className="spin" /> : <ArrowUpRight size={16} />} Enviar a revisión</button></div></div>
    </form>
  </div>;
}

function EmptyState({ icon, title, body, action, compact = false }: { icon: ReactNode; title: string; body: string; action?: ReactNode; compact?: boolean }) {
  return <div className={`empty-state ${compact ? "empty-compact" : ""}`}><span className="empty-icon">{icon}</span><h3>{title}</h3><p>{body}</p>{action}</div>;
}

function ErrorPanel({ error, retry }: { error: string; retry: () => void }) {
  return <EmptyState icon={<X />} title="No se pudo cargar la información" body={error} action={<button className="button button-secondary" onClick={retry}>Intentar de nuevo</button>} />;
}

export default App;
