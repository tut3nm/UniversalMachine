"""
Lector de archivos de texto generados por la maquina de ensayos de Fuerza-Velocidad
para amortiguadores (formato *** con bloques de configuracion + mediciones).

No depende de ninguna libreria externa (solo la libreria estandar de Python).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Expresiones regulares del formato
# ---------------------------------------------------------------------------

HEADER_DELIM_RE = re.compile(r"^\*{5,}\s*$")
DATE_TIME_RE = re.compile(
    r"^(\d{1,2}):(\d{1,2}):(\d{4})\s+(\d{1,2}):(\d{1,2}):(\d{1,2})$"
)
ARCHIVO_RE = re.compile(
    r"ARCHIVO\s*=\s*(.+?)\s+CARRERA\s*=\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE
)
VELOC_RE = re.compile(r"VELOC\s*=\s*(.+)$", re.IGNORECASE)
CPEXTSUP_RE = re.compile(r"CPEXTSUP\s*=\s*(.+)$", re.IGNORECASE)
CPEXTINF_RE = re.compile(r"CPEXTINF\s*=\s*(.+)$", re.IGNORECASE)
CPCOMPSUP_RE = re.compile(r"CPCOMPSUP\s*=\s*(.+)$", re.IGNORECASE)
CPCOMPINF_RE = re.compile(r"CPCOMPINF\s*=\s*(.+)$", re.IGNORECASE)
CPCAVIT_RE = re.compile(r"CPCAVIT\s*=\s*(.+)$", re.IGNORECASE)
FZA_RE = re.compile(
    r"FZA\[VEL\]\s+(-?\d+(?:\.\d+)?)\s*mm/s\s+(-?\d+(?:\.\d+)?)\s*Kg\s+(-?\d+(?:\.\d+)?)\s*Kg",
    re.IGNORECASE,
)

EC_LINE_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s+E(-?\d+(?:\.\d+)?)\s+C(-?\d+(?:\.\d+)?)\s+Y([+-])\s+V([+-])\s*$"
)
VF_LINE_RE = re.compile(r"^V(\d+(?:\.\d+)?)\s+F(-?\d+(?:\.\d+)?)\s+F([+-])\s*$")


def _num_list(text: str) -> list[float]:
    return [float(x) for x in text.split()]


def _to_number(x: float) -> float | int:
    """Devuelve int si el valor es entero, si no float (para mostrar mas limpio)."""
    return int(x) if float(x).is_integer() else x


# ---------------------------------------------------------------------------
# Estructuras de datos
# ---------------------------------------------------------------------------


@dataclass
class ConfigBlock:
    index: int
    effective_from: Optional[datetime]
    archivo: str
    carrera: float
    velocities: list
    ext_sup: list
    ext_inf: list
    comp_sup: list
    comp_inf: list
    cpcavit: list
    fv_speed: Optional[float]
    fv_max: Optional[float]
    fv_min: Optional[float]
    raw_text: str
    n_measurements: int = 0
    n_ok: int = 0
    n_nok: int = 0

    def tolerancia_ext(self, velocidad):
        if velocidad in self.velocities:
            i = self.velocities.index(velocidad)
            return self.ext_inf[i], self.ext_sup[i]
        return None, None

    def tolerancia_comp(self, velocidad):
        if velocidad in self.velocities:
            i = self.velocities.index(velocidad)
            return self.comp_inf[i], self.comp_sup[i]
        return None, None


@dataclass
class ECReading:
    velocidad: float
    extendido: float
    comprimido: float
    flag_y: str
    flag_v: str
    ok_ext: Optional[bool] = None
    ok_comp: Optional[bool] = None


@dataclass
class Measurement:
    row_num: int
    dt: Optional[datetime]
    config: Optional[ConfigBlock]
    ec: list  # list[ECReading]
    v70_speed: Optional[float]
    v70_force: Optional[float]
    v70_flag: Optional[str]
    v70_ok: Optional[bool] = None
    resultado_general: bool = True


@dataclass
class DateAnomaly:
    row_ini: int
    row_fin: int
    dt_ini: datetime
    dt_fin: datetime
    dt_referencia: datetime  # ultima fecha "buena" antes de la anomalia


@dataclass
class ParseResult:
    configs: list
    measurements: list
    warnings: list
    total_lines: int
    date_anomalies: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parseo de un bloque de configuracion (header)
# ---------------------------------------------------------------------------


def _parse_header_block(block_lines: list[str], index: int) -> ConfigBlock:
    raw_text = "\n".join(block_lines)
    effective_from = None
    archivo = ""
    carrera = 0.0
    velocities: list[float] = []
    ext_sup: list[float] = []
    ext_inf: list[float] = []
    comp_sup: list[float] = []
    comp_inf: list[float] = []
    cpcavit: list[float] = []
    fv_speed = fv_max = fv_min = None

    veloc_raw: list[float] = []
    extsup_raw: list[float] = []
    extinf_raw: list[float] = []
    compsup_raw: list[float] = []
    compinf_raw: list[float] = []

    for line in block_lines:
        s = line.strip()
        m = DATE_TIME_RE.match(s.lstrip("*").strip())
        if m and effective_from is None:
            d, mo, y, hh, mm, ss = (int(g) for g in m.groups())
            try:
                effective_from = datetime(y, mo, d, hh, mm, ss)
            except ValueError:
                effective_from = None
            continue
        m = ARCHIVO_RE.search(s)
        if m:
            archivo = m.group(1).strip()
            carrera = float(m.group(2))
            continue
        m = VELOC_RE.search(s)
        if m:
            veloc_raw = _num_list(m.group(1))
            continue
        m = CPEXTSUP_RE.search(s)
        if m:
            extsup_raw = _num_list(m.group(1))
            continue
        m = CPEXTINF_RE.search(s)
        if m:
            extinf_raw = _num_list(m.group(1))
            continue
        m = CPCOMPSUP_RE.search(s)
        if m:
            compsup_raw = _num_list(m.group(1))
            continue
        m = CPCOMPINF_RE.search(s)
        if m:
            compinf_raw = _num_list(m.group(1))
            continue
        m = CPCAVIT_RE.search(s)
        if m:
            cpcavit = _num_list(m.group(1))
            continue
        m = FZA_RE.search(s)
        if m:
            fv_speed, fv_max, fv_min = (float(g) for g in m.groups())
            continue

    active_idx = [i for i, v in enumerate(veloc_raw) if v != 0]
    velocities = [veloc_raw[i] for i in active_idx]
    ext_sup = [extsup_raw[i] if i < len(extsup_raw) else None for i in active_idx]
    ext_inf = [extinf_raw[i] if i < len(extinf_raw) else None for i in active_idx]
    comp_sup = [compsup_raw[i] if i < len(compsup_raw) else None for i in active_idx]
    comp_inf = [compinf_raw[i] if i < len(compinf_raw) else None for i in active_idx]

    return ConfigBlock(
        index=index,
        effective_from=effective_from,
        archivo=archivo,
        carrera=carrera,
        velocities=velocities,
        ext_sup=ext_sup,
        ext_inf=ext_inf,
        comp_sup=comp_sup,
        comp_inf=comp_inf,
        cpcavit=cpcavit,
        fv_speed=fv_speed,
        fv_max=fv_max,
        fv_min=fv_min,
        raw_text=raw_text,
    )


# ---------------------------------------------------------------------------
# Parseo principal
# ---------------------------------------------------------------------------


def parse_lines(
    lines: list[str],
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> ParseResult:
    """Recorre todas las lineas del archivo y devuelve configuraciones + mediciones.

    progress_callback(linea_actual, total_lineas) se llama periodicamente.
    """
    configs: list[ConfigBlock] = []
    measurements: list[Measurement] = []
    warnings: list[str] = []

    n = len(lines)
    stripped = [l.strip() for l in lines]

    current_config: Optional[ConfigBlock] = None
    i = 0
    report_every = max(1, n // 200)

    while i < n:
        if progress_callback and i % report_every == 0:
            progress_callback(i, n)

        s = stripped[i]

        if s == "":
            i += 1
            continue

        if HEADER_DELIM_RE.match(s):
            block_lines = []
            i += 1
            while i < n and not HEADER_DELIM_RE.match(stripped[i]):
                if stripped[i] != "":
                    block_lines.append(stripped[i])
                i += 1
            i += 1  # saltar el delimitador de cierre
            cfg = _parse_header_block(block_lines, len(configs) + 1)
            configs.append(cfg)
            current_config = cfg
            continue

        m = DATE_TIME_RE.match(s)
        if m:
            d, mo, y, hh, mm, ss = (int(g) for g in m.groups())
            try:
                dt = datetime(y, mo, d, hh, mm, ss)
            except ValueError:
                dt = None
            i += 1

            ec_readings: list[ECReading] = []
            while i < n and EC_LINE_RE.match(stripped[i]):
                em = EC_LINE_RE.match(stripped[i])
                vel, ext, comp, fy, fv = em.groups()
                ec_readings.append(
                    ECReading(
                        velocidad=float(vel),
                        extendido=float(ext),
                        comprimido=float(comp),
                        flag_y=fy,
                        flag_v=fv,
                    )
                )
                i += 1

            v70_speed = v70_force = None
            v70_flag = None
            if i < n:
                vm = VF_LINE_RE.match(stripped[i])
                if vm:
                    v70_speed, v70_force = float(vm.group(1)), float(vm.group(2))
                    v70_flag = vm.group(3)
                    i += 1

            measurements.append(
                Measurement(
                    row_num=len(measurements) + 1,
                    dt=dt,
                    config=current_config,
                    ec=ec_readings,
                    v70_speed=v70_speed,
                    v70_force=v70_force,
                    v70_flag=v70_flag,
                )
            )
            continue

        warnings.append(f"Linea {i + 1} no reconocida: {lines[i]!r}")
        i += 1

    if progress_callback:
        progress_callback(n, n)

    _evaluate(configs, measurements)
    anomalies = _detect_date_anomalies(measurements)
    return ParseResult(
        configs=configs, measurements=measurements, warnings=warnings,
        total_lines=n, date_anomalies=anomalies,
    )


def _detect_date_anomalies(measurements: list[Measurement]) -> list[DateAnomaly]:
    """Detecta tramos donde la fecha/hora del equipo retrocede respecto al maximo
    visto hasta ese punto (tipico de un reloj interno mal configurado o una
    bateria de RTC agotada). No corrige nada: solo informa el tramo afectado."""
    anomalies: list[DateAnomaly] = []
    running_max = None
    current: Optional[DateAnomaly] = None

    for m in measurements:
        if m.dt is None:
            continue
        if running_max is not None and m.dt < running_max:
            if current is None:
                current = DateAnomaly(m.row_num, m.row_num, m.dt, m.dt, running_max)
            else:
                current.row_fin = m.row_num
                current.dt_fin = m.dt
        else:
            if current is not None:
                anomalies.append(current)
                current = None
            running_max = m.dt

    if current is not None:
        anomalies.append(current)
    return anomalies


def _evaluate(configs: list[ConfigBlock], measurements: list[Measurement]) -> None:
    """Calcula OK/NOK de cada medicion contra la configuracion (tolerancias) vigente.

    El criterio de aceptacion real del equipo (verificado contra 416.956 lecturas
    reales, 0 discrepancias) es un intervalo semi-abierto: el valor debe ser
    MAYOR O IGUAL al limite inferior y MENOR ESTRICTO al limite superior
    (lo <= valor < hi). Tocar el limite superior exacto ya se considera fuera
    de tolerancia; tocar el limite inferior exacto todavia se considera valido.
    Esta misma regla reproduce exactamente la bandera "Y" que imprime el equipo,
    por lo que ok_ext/ok_comp equivalen a esa bandera.

    La bandera "V" que imprime el equipo no esta documentada en el archivo de
    anotaciones y no se corresponde con ningun limite de CPEXT/CPCOMP/FZA (no es
    booleanamente derivable de los datos visibles). Se respeta como una señal de
    NOK adicional del propio equipo, pero no se reinterpreta ni se le asigna una
    formula propia.
    """
    for meas in measurements:
        cfg = meas.config
        general_ok = True

        for ec in meas.ec:
            if cfg is not None:
                lo_e, hi_e = cfg.tolerancia_ext(ec.velocidad)
                lo_c, hi_c = cfg.tolerancia_comp(ec.velocidad)
            else:
                lo_e = hi_e = lo_c = hi_c = None

            if lo_e is not None and hi_e is not None:
                ec.ok_ext = lo_e <= ec.extendido < hi_e
            if lo_c is not None and hi_c is not None:
                ec.ok_comp = lo_c <= abs(ec.comprimido) < hi_c

            if ec.ok_ext is False or ec.ok_comp is False:
                general_ok = False
            if ec.flag_v == "-":
                general_ok = False

        if cfg is not None and cfg.fv_min is not None and cfg.fv_max is not None and meas.v70_force is not None:
            meas.v70_ok = cfg.fv_min <= meas.v70_force < cfg.fv_max
            if not meas.v70_ok:
                general_ok = False

        meas.resultado_general = general_ok

        if cfg is not None:
            cfg.n_measurements += 1
            if general_ok:
                cfg.n_ok += 1
            else:
                cfg.n_nok += 1


def read_text_file(path: str) -> list[str]:
    """Lee el archivo probando encodings tipicos de equipos industriales."""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    with open(path, encoding="latin-1", errors="replace") as f:
        return f.readlines()


def parse_file(path: str, progress_callback=None) -> ParseResult:
    lines = read_text_file(path)
    return parse_lines(lines, progress_callback=progress_callback)
