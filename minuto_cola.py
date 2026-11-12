"""
Rock Cathode · Temporada 1 "Del despacho al plan" · Publicación 1
¿Cuánto vale un minuto de cola?

Modelo simple que traduce los minutos de cola de una flota de acarreo
a horas-camión, toneladas no movidas y dólares.

Idea clave: el valor de ese minuto depende del cuello de botella.
  - Si el ACARREO es la restricción, las horas-camión ya se pagan igual;
    lo que se pierde es el margen del cobre que no llega a la planta.
  - Si la PLANTA es la restricción, mover más mineral no produce más cobre;
    la cola solo cuesta horas-camión improductivas (podría operarse con
    menos camiones).
  Los dos costos son alternativos: no se suman.

Todos los valores por defecto son ILUSTRATIVOS.

Uso:
    python minuto_cola.py                      # resultado con valores por defecto
    python minuto_cola.py --cola 3 --camiones 40
    python minuto_cola.py --grafico            # guarda el gráfico de sensibilidad
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace

LB_POR_TONELADA = 2204.62
DIAS_POR_MES = 30


@dataclass(frozen=True)
class Parametros:
    # Flota y operación
    n_camiones: int = 30
    capacidad_t: float = 300.0            # toneladas por viaje
    ciclo_sin_cola_min: float = 30.0      # carga + acarreo + descarga + retorno
    cola_min_por_ciclo: float = 2.0       # espera promedio por ciclo
    horas_efectivas_turno: float = 10.0   # de un turno de 12 h
    turnos_por_dia: int = 2
    dias_operativos_anio: int = 360
    # Mineral
    fraccion_mineral: float = 0.40        # parte del material movido que es mineral
    ley_cu_pct: float = 0.60              # % Cu
    recuperacion_pct: float = 85.0        # % recuperación en planta
    # Economía
    precio_cu_usd_lb: float = 6.40
    costo_hora_camion_usd: float = 450.0
    costo_proceso_usd_t: float = 12.0     # costo variable de procesar 1 t de mineral
    # Restricción del sistema: "acarreo" o "planta"
    cuello_de_botella: str = "acarreo"

    def validar(self) -> None:
        positivos = {
            "n_camiones": self.n_camiones,
            "capacidad_t": self.capacidad_t,
            "ciclo_sin_cola_min": self.ciclo_sin_cola_min,
            "horas_efectivas_turno": self.horas_efectivas_turno,
            "turnos_por_dia": self.turnos_por_dia,
            "dias_operativos_anio": self.dias_operativos_anio,
        }
        for nombre, valor in positivos.items():
            if valor <= 0:
                raise ValueError(f"{nombre} debe ser mayor que 0 (recibido: {valor})")
        no_negativos = {
            "cola_min_por_ciclo": self.cola_min_por_ciclo,
            "ley_cu_pct": self.ley_cu_pct,
            "precio_cu_usd_lb": self.precio_cu_usd_lb,
            "costo_hora_camion_usd": self.costo_hora_camion_usd,
            "costo_proceso_usd_t": self.costo_proceso_usd_t,
        }
        for nombre, valor in no_negativos.items():
            if valor < 0:
                raise ValueError(f"{nombre} no puede ser negativo (recibido: {valor})")
        if not 0 <= self.fraccion_mineral <= 1:
            raise ValueError("fraccion_mineral debe estar entre 0 y 1")
        if not 0 <= self.recuperacion_pct <= 100:
            raise ValueError("recuperacion_pct debe estar entre 0 y 100")
        if self.ley_cu_pct > 100:
            raise ValueError("ley_cu_pct no puede superar 100")
        if self.horas_efectivas_turno > 24:
            raise ValueError("horas_efectivas_turno no puede superar 24")
        if self.cuello_de_botella not in ("acarreo", "planta"):
            raise ValueError('cuello_de_botella debe ser "acarreo" o "planta"')


@dataclass(frozen=True)
class Resultado:
    ciclos_por_camion_turno: float
    horas_camion_perdidas: float          # por turno
    toneladas_no_movidas: float           # por turno
    toneladas_mineral_no_movidas: float   # por turno
    cu_fino_no_producido_lb: float        # por turno
    costo_operativo_usd: float            # por turno
    ingreso_bruto_usd: float              # por turno: cobre no producido × precio
    costo_oportunidad_usd: float          # por turno: margen perdido (0 si la planta es la restricción)
    turnos_por_anio: int
    dias_operativos_anio: int
    cuello_de_botella: str

    @property
    def costo_total_usd(self) -> float:
        """Pérdida económica del turno según el cuello de botella (no se suman)."""
        if self.cuello_de_botella == "acarreo":
            return self.costo_oportunidad_usd
        return self.costo_operativo_usd

    def por_periodo(self, periodo: str) -> dict[str, float]:
        """Escala los resultados por turno a 'turno', 'dia', 'mes' o 'anio'."""
        turnos_por_dia = self.turnos_por_anio / self.dias_operativos_anio
        factores = {
            "turno": 1,
            "dia": turnos_por_dia,
            "mes": turnos_por_dia * DIAS_POR_MES,
            "anio": self.turnos_por_anio,
        }
        if periodo not in factores:
            raise ValueError(f"periodo inválido: {periodo}")
        f = factores[periodo]
        return {
            "horas_camion_perdidas": self.horas_camion_perdidas * f,
            "toneladas_no_movidas": self.toneladas_no_movidas * f,
            "toneladas_mineral_no_movidas": self.toneladas_mineral_no_movidas * f,
            "cu_fino_no_producido_lb": self.cu_fino_no_producido_lb * f,
            "costo_operativo_usd": self.costo_operativo_usd * f,
            "ingreso_bruto_usd": self.ingreso_bruto_usd * f,
            "costo_oportunidad_usd": self.costo_oportunidad_usd * f,
            "costo_total_usd": self.costo_total_usd * f,
        }


def calcular(p: Parametros) -> Resultado:
    """Calcula las pérdidas de UN turno causadas por la cola."""
    p.validar()

    ciclo_total = p.ciclo_sin_cola_min + p.cola_min_por_ciclo
    minutos_turno = p.horas_efectivas_turno * 60

    # Con cola, cada camión completa menos ciclos por turno
    ciclos_por_camion = minutos_turno / ciclo_total

    # Minutos de toda la flota esperando en cola
    minutos_cola_flota = p.n_camiones * ciclos_por_camion * p.cola_min_por_ciclo
    horas_perdidas = minutos_cola_flota / 60

    # Esos minutos, sin cola, se habrían usado en ciclos productivos
    ciclos_no_realizados = minutos_cola_flota / p.ciclo_sin_cola_min
    toneladas_no_movidas = ciclos_no_realizados * p.capacidad_t

    toneladas_mineral = toneladas_no_movidas * p.fraccion_mineral
    cu_fino_lb = (
        toneladas_mineral
        * (p.ley_cu_pct / 100)
        * (p.recuperacion_pct / 100)
        * LB_POR_TONELADA
    )

    costo_operativo = horas_perdidas * p.costo_hora_camion_usd
    ingreso_bruto = cu_fino_lb * p.precio_cu_usd_lb
    if p.cuello_de_botella == "acarreo":
        # margen: ingreso del cobre menos el costo variable de procesar ese mineral
        costo_oportunidad = max(0.0, ingreso_bruto - toneladas_mineral * p.costo_proceso_usd_t)
    else:  # la planta no puede procesar más: el mineral extra no se convierte en cobre
        costo_oportunidad = 0.0

    r = Resultado(
        ciclos_por_camion_turno=ciclos_por_camion,
        horas_camion_perdidas=horas_perdidas,
        toneladas_no_movidas=toneladas_no_movidas,
        toneladas_mineral_no_movidas=toneladas_mineral,
        cu_fino_no_producido_lb=cu_fino_lb,
        costo_operativo_usd=costo_operativo,
        ingreso_bruto_usd=ingreso_bruto,
        costo_oportunidad_usd=costo_oportunidad,
        turnos_por_anio=p.turnos_por_dia * p.dias_operativos_anio,
        dias_operativos_anio=p.dias_operativos_anio,
        cuello_de_botella=p.cuello_de_botella,
    )
    return r


def valor_de_un_minuto(p: Parametros, periodo: str = "anio") -> dict[str, float]:
    """Pérdida causada por exactamente 1 minuto de cola por ciclo."""
    return calcular(replace(p, cola_min_por_ciclo=1.0)).por_periodo(periodo)


# ----------------------------------------------------------------- salida

def _usd(x: float) -> str:
    if abs(x) >= 1e6:
        return f"US$ {x / 1e6:,.2f} M"
    return f"US$ {x:,.0f}"


def resumen(p: Parametros) -> str:
    r = calcular(p)
    lineas = [
        "ROCK CATHODE · ¿Cuánto vale un minuto de cola?  (valores ilustrativos)",
        "-" * 72,
        f"Flota: {p.n_camiones} camiones de {p.capacidad_t:.0f} t · ciclo {p.ciclo_sin_cola_min:.0f} min"
        f" + {p.cola_min_por_ciclo:g} min de cola · cuello de botella: {p.cuello_de_botella.upper()}",
        "",
        f"{'':28}{'Turno':>14}{'Mes':>16}{'Año':>16}",
    ]
    t, m, a = (r.por_periodo(x) for x in ("turno", "mes", "anio"))
    filas = [
        ("Horas-camión perdidas", "horas_camion_perdidas", lambda v: f"{v:,.0f} h"),
        ("Toneladas no movidas", "toneladas_no_movidas", lambda v: f"{v / 1e3:,.1f} kt"),
        ("Cu fino no producido", "cu_fino_no_producido_lb", lambda v: f"{v / 1e3:,.0f} klb"),
        ("Costo horas-camión en cola", "costo_operativo_usd", _usd),
        ("Margen no capturado", "costo_oportunidad_usd", _usd),
        ("PÉRDIDA (según restricción)", "costo_total_usd", _usd),
    ]
    for etiqueta, clave, fmt in filas:
        lineas.append(f"{etiqueta:28}{fmt(t[clave]):>14}{fmt(m[clave]):>16}{fmt(a[clave]):>16}")
    un_min = valor_de_un_minuto(p)
    lineas += [
        "",
        f"→ Cada minuto de cola por ciclo cuesta ≈ {_usd(un_min['costo_total_usd'])} al año"
        f" ({un_min['horas_camion_perdidas']:,.0f} horas-camión).",
    ]
    return "\n".join(lineas)


def grafico_sensibilidad(p: Parametros, archivo: str = "sensibilidad_cola.png") -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colas = [x / 4 for x in range(0, 21)]  # 0 a 5 min
    acarreo = [calcular(replace(p, cola_min_por_ciclo=c, cuello_de_botella="acarreo")).por_periodo("anio")["costo_total_usd"] / 1e6 for c in colas]
    planta = [calcular(replace(p, cola_min_por_ciclo=c, cuello_de_botella="planta")).por_periodo("anio")["costo_total_usd"] / 1e6 for c in colas]

    verde, naranja, gris = "#226214", "#FF751F", "#555555"
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=150)
    ax.plot(colas, acarreo, color=verde, lw=3, label="Cuello de botella: ACARREO → margen del cobre no producido")
    ax.plot(colas, planta, color=naranja, lw=3, label="Cuello de botella: PLANTA → costo de horas-camión en cola")
    ax.fill_between(colas, planta, acarreo, color=verde, alpha=0.08)
    for serie, color in ((acarreo, verde), (planta, naranja)):
        ax.annotate(f"US$ {serie[4]:,.1f} M", (colas[4], serie[4]), textcoords="offset points",
                    xytext=(8, 8), color=color, fontsize=11, fontweight="bold")
    ax.axvline(1, color=gris, lw=1, ls="--", ymax=0.78)
    ax.set_title("¿Cuánto vale un minuto de cola? · Pérdida anual según minutos de cola por ciclo",
                 fontsize=13, fontweight="bold", loc="left")
    ax.set_xlabel("Minutos de cola por ciclo")
    ax.set_ylabel("US$ millones por año")
    ax.grid(axis="y", color="#DDDDDD")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper left", fontsize=10)
    fig.text(0.01, 0.01,
             f"Rock Cathode · Valores ilustrativos: {p.n_camiones} camiones de {p.capacidad_t:.0f} t, ciclo {p.ciclo_sin_cola_min:.0f} min, "
             f"ley {p.ley_cu_pct}% Cu, recuperación {p.recuperacion_pct:.0f}%, Cu US$ {p.precio_cu_usd_lb}/lb",
             fontsize=8, color=gris)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(archivo)
    plt.close(fig)
    return archivo


def _cli() -> None:
    d = Parametros()
    ap = argparse.ArgumentParser(description="¿Cuánto vale un minuto de cola? (Rock Cathode)")
    ap.add_argument("--camiones", type=int, default=d.n_camiones)
    ap.add_argument("--capacidad", type=float, default=d.capacidad_t)
    ap.add_argument("--ciclo", type=float, default=d.ciclo_sin_cola_min, help="ciclo sin cola (min)")
    ap.add_argument("--cola", type=float, default=d.cola_min_por_ciclo, help="minutos de cola por ciclo")
    ap.add_argument("--horas", type=float, default=d.horas_efectivas_turno, help="horas efectivas por turno")
    ap.add_argument("--mineral", type=float, default=d.fraccion_mineral, help="fracción de mineral (0-1)")
    ap.add_argument("--ley", type=float, default=d.ley_cu_pct, help="ley de Cu (%%)")
    ap.add_argument("--recuperacion", type=float, default=d.recuperacion_pct, help="recuperación (%%)")
    ap.add_argument("--precio", type=float, default=d.precio_cu_usd_lb, help="precio Cu (US$/lb)")
    ap.add_argument("--costo-hora", type=float, default=d.costo_hora_camion_usd, help="costo hora-camión (US$)")
    ap.add_argument("--costo-proceso", type=float, default=d.costo_proceso_usd_t, help="costo de proceso (US$/t mineral)")
    ap.add_argument("--cuello", choices=["acarreo", "planta"], default=d.cuello_de_botella)
    ap.add_argument("--grafico", action="store_true", help="guarda sensibilidad_cola.png")
    a = ap.parse_args()
    p = Parametros(
        n_camiones=a.camiones, capacidad_t=a.capacidad, ciclo_sin_cola_min=a.ciclo,
        cola_min_por_ciclo=a.cola, horas_efectivas_turno=a.horas, fraccion_mineral=a.mineral,
        ley_cu_pct=a.ley, recuperacion_pct=a.recuperacion, precio_cu_usd_lb=a.precio,
        costo_hora_camion_usd=a.costo_hora, costo_proceso_usd_t=a.costo_proceso, cuello_de_botella=a.cuello,
    )
    print(resumen(p))
    if a.grafico:
        print(f"\nGráfico guardado en: {grafico_sensibilidad(p)}")


if __name__ == "__main__":
    _cli()
