import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ReactNode } from "react";
import "./statistical-charts.css";

export type StatisticalPoint = { label: string; detail?: string; value: number };
export type StudentPeriod = {
  label: string; detail: string; average: number | null; points: number; evidence: number; validated: number;
  evidenceInReview: number; evidenceObserved: number; evidenceRejected: number; evidenceRevoked: number;
};

const palette = ["#18788c", "#50a89b", "#e5a24c", "#c86d56", "#7087b7", "#9a78ad"];
const grid = "#e6edf1";

function ChartTable({ title, rows }: { title: string; rows: StatisticalPoint[] }) {
  return <details className="stat-chart-data"><summary>Ver tabla de datos</summary><div className="stat-chart-table-wrap"><table><caption>{title}</caption><thead><tr><th>Categoría</th><th>Valor</th></tr></thead><tbody>{rows.map((row) => <tr key={row.label}><td>{row.detail ? `${row.label} · ${row.detail}` : row.label}</td><td>{row.value}</td></tr>)}</tbody></table></div></details>;
}

function ChartFrame({ title, description, data, children }: { title: string; description: string; data: StatisticalPoint[]; children: ReactNode }) {
  return <section className="stat-chart-card"><header><h3>{title}</h3><p>{description}</p></header><div className="stat-chart-plot" role="img" aria-label={`${title}. ${description}`}>{children}</div><ChartTable title={title} rows={data} /></section>;
}

export function StatisticalBarChart({ title, description, data, horizontal = false }: {
  title: string; description: string; data: StatisticalPoint[]; horizontal?: boolean;
}) {
  return <ChartFrame title={title} description={description} data={data}>
    {data.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 14, bottom: 8, left: 4 }} accessibilityLayer>
      <CartesianGrid stroke={grid} vertical={!horizontal} horizontal={horizontal} strokeDasharray="3 3" />
      {horizontal ? <><XAxis type="number" allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: "#6d8090", fontSize: 11 }} /><YAxis type="category" dataKey="label" width={112} axisLine={false} tickLine={false} tick={{ fill: "#526a7b", fontSize: 11 }} /></>
        : <><XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: "#526a7b", fontSize: 11 }} /><YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: "#6d8090", fontSize: 11 }} /></>}
      <Tooltip cursor={{ fill: "#eff6f7" }} formatter={(value) => [value, "Registros"]} labelFormatter={(label, payload) => payload?.[0]?.payload?.detail ? `${label} · ${payload[0].payload.detail}` : label} />
      <Bar dataKey="value" name="Registros" fill={palette[0]} radius={horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]} maxBarSize={42}>
        {data.map((item, index) => <Cell key={item.label} fill={palette[index % palette.length]} />)}
      </Bar>
    </BarChart></ResponsiveContainer> : <div className="stat-chart-empty">No hay datos para este alcance.</div>}
  </ChartFrame>;
}

export function StatisticalLineChart({ title, description, data, valueLabel = "Registros", domain }: {
  title: string; description: string; data: StatisticalPoint[]; valueLabel?: string; domain?: [number, number | "auto"];
}) {
  return <ChartFrame title={title} description={description} data={data}>
    {data.length ? <ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 12, right: 18, bottom: 8, left: 2 }} accessibilityLayer>
      <CartesianGrid stroke={grid} strokeDasharray="3 3" vertical={false} />
      <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: "#526a7b", fontSize: 11 }} />
      <YAxis domain={domain} allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: "#6d8090", fontSize: 11 }} />
      <Tooltip formatter={(value) => [value, valueLabel]} labelFormatter={(label, payload) => payload?.[0]?.payload?.detail ? `${label} · ${payload[0].payload.detail}` : label} />
      <Line type="monotone" dataKey="value" name={valueLabel} stroke={palette[0]} strokeWidth={3} dot={{ r: 4, fill: "#fff", stroke: palette[0], strokeWidth: 2 }} activeDot={{ r: 6 }} connectNulls={false} />
    </LineChart></ResponsiveContainer> : <div className="stat-chart-empty">Aún no hay datos por periodo.</div>}
  </ChartFrame>;
}

export function StatisticalPieChart({ title, description, data }: { title: string; description: string; data: StatisticalPoint[] }) {
  const nonzero = data.filter((item) => item.value > 0);
  return <ChartFrame title={title} description={description} data={data}>
    {nonzero.length ? <ResponsiveContainer width="100%" height="100%"><PieChart accessibilityLayer>
      <Tooltip formatter={(value) => [value, "Registros"]} />
      <Legend verticalAlign="bottom" height={38} iconType="circle" wrapperStyle={{ fontSize: 11, color: "#526a7b" }} />
      <Pie data={nonzero} dataKey="value" nameKey="label" cx="50%" cy="45%" innerRadius="43%" outerRadius="72%" paddingAngle={2} stroke="#fff" strokeWidth={2}>
        {nonzero.map((item, index) => <Cell key={item.label} fill={palette[index % palette.length]} />)}
      </Pie>
    </PieChart></ResponsiveContainer> : <div className="stat-chart-empty">No hay registros para representar en este alcance.</div>}
  </ChartFrame>;
}

export function StudentProgressCharts({ periods }: { periods: StudentPeriod[] }) {
  const averages = periods.filter((period) => period.average !== null).map((period) => ({ label: period.label, detail: period.detail, value: period.average as number }));
  const points = periods.map((period) => ({ label: period.label, detail: period.detail, value: period.points }));
  const evidence = periods.map((period) => ({ label: period.label, detail: period.detail, value: period.evidence }));
  const evidenceStatuses: StatisticalPoint[] = [
    { label: "Aprobadas", value: periods.reduce((sum, period) => sum + period.validated, 0) },
    { label: "En revisión", value: periods.reduce((sum, period) => sum + period.evidenceInReview, 0) },
    { label: "Observadas", value: periods.reduce((sum, period) => sum + period.evidenceObserved, 0) },
    { label: "Rechazadas", value: periods.reduce((sum, period) => sum + period.evidenceRejected, 0) },
    { label: "Revocadas", value: periods.reduce((sum, period) => sum + period.evidenceRevoked, 0) },
  ];
  return <div className="student-stat-charts">
    <StatisticalLineChart title="Promedio académico" description="Evolución del promedio verificado, normalizado sobre 100." data={averages} valueLabel="Promedio" domain={[0, 100]} />
    <StatisticalBarChart title="Puntos SPD por periodo" description="Puntos propios registrados en cada periodo académico." data={points} />
    <StatisticalBarChart title="Evidencias por periodo" description="Total de evidencias propias registradas por periodo." data={evidence} />
    <StatisticalPieChart title="Estado de mis evidencias" description="Proporción de evidencias propias por estado." data={evidenceStatuses} />
  </div>;
}
