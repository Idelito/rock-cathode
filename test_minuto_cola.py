"""Pruebas del modelo ¿Cuánto vale un minuto de cola?  ->  python -m pytest -v"""

from dataclasses import replace

import pytest

from minuto_cola import LB_POR_TONELADA, Parametros, calcular, valor_de_un_minuto

BASE = Parametros()


def caso_simple(**kw):
    """1 camión, 1 h, ciclo 30 + cola 30: números fáciles de verificar a mano."""
    p = dict(
        n_camiones=1, capacidad_t=100, ciclo_sin_cola_min=30, cola_min_por_ciclo=30,
        horas_efectivas_turno=1, turnos_por_dia=1, dias_operativos_anio=1,
        fraccion_mineral=1.0, ley_cu_pct=1.0, recuperacion_pct=100,
        precio_cu_usd_lb=1.0, costo_hora_camion_usd=100, costo_proceso_usd_t=0,
    )
    p.update(kw)
    return Parametros(**p)


# ------------------------------------------------------------ cálculos a mano

def test_caso_calculado_a_mano():
    r = calcular(caso_simple())
    # 60 min / (30 + 30) = 1 ciclo; ese ciclo tuvo 30 min de cola
    assert r.ciclos_por_camion_turno == pytest.approx(1.0)
    assert r.horas_camion_perdidas == pytest.approx(0.5)
    # 30 min de cola / 30 min de ciclo = 1 viaje perdido de 100 t
    assert r.toneladas_no_movidas == pytest.approx(100)
    # 100 t × 1 % Cu × 100 % rec = 1 t Cu
    assert r.cu_fino_no_producido_lb == pytest.approx(LB_POR_TONELADA)
    assert r.ingreso_bruto_usd == pytest.approx(LB_POR_TONELADA * 1.0)
    assert r.costo_operativo_usd == pytest.approx(50)


def test_toneladas_igual_a_diferencia_de_produccion():
    """Lo no movido = producción sin cola − producción con cola."""
    p = BASE
    minutos = p.horas_efectivas_turno * 60
    sin_cola = p.n_camiones * minutos / p.ciclo_sin_cola_min * p.capacidad_t
    con_cola = p.n_camiones * minutos / (p.ciclo_sin_cola_min + p.cola_min_por_ciclo) * p.capacidad_t
    assert calcular(p).toneladas_no_movidas == pytest.approx(sin_cola - con_cola)


def test_margen_resta_costo_de_proceso():
    r = calcular(caso_simple(costo_proceso_usd_t=5))
    assert r.costo_oportunidad_usd == pytest.approx(LB_POR_TONELADA - 100 * 5)


def test_margen_no_es_negativo():
    r = calcular(caso_simple(costo_proceso_usd_t=1e6))
    assert r.costo_oportunidad_usd == 0


# ------------------------------------------------------------ cuello de botella

def test_acarreo_cuenta_margen_y_planta_cuenta_horas():
    a = calcular(replace(BASE, cuello_de_botella="acarreo"))
    pl = calcular(replace(BASE, cuello_de_botella="planta"))
    assert a.costo_total_usd == pytest.approx(a.costo_oportunidad_usd)
    assert pl.costo_oportunidad_usd == 0
    assert pl.costo_total_usd == pytest.approx(pl.costo_operativo_usd)
    # la parte física es la misma; solo cambia su valor económico
    assert a.horas_camion_perdidas == pytest.approx(pl.horas_camion_perdidas)
    assert a.toneladas_no_movidas == pytest.approx(pl.toneladas_no_movidas)


def test_costos_no_se_suman():
    r = calcular(BASE)
    assert r.costo_total_usd < r.costo_operativo_usd + r.costo_oportunidad_usd


# ------------------------------------------------------------ comportamiento

def test_sin_cola_no_hay_perdidas():
    r = calcular(replace(BASE, cola_min_por_ciclo=0))
    assert r.horas_camion_perdidas == 0
    assert r.toneladas_no_movidas == 0
    assert r.costo_total_usd == 0


def test_escala_lineal_con_la_flota():
    r1 = calcular(replace(BASE, n_camiones=10))
    r2 = calcular(replace(BASE, n_camiones=20))
    assert r2.horas_camion_perdidas == pytest.approx(2 * r1.horas_camion_perdidas)
    assert r2.costo_total_usd == pytest.approx(2 * r1.costo_total_usd)


@pytest.mark.parametrize("campo", ["precio_cu_usd_lb", "ley_cu_pct"])
def test_mas_precio_o_ley_mas_perdida(campo):
    bajo = calcular(BASE)
    alto = calcular(replace(BASE, **{campo: getattr(BASE, campo) * 1.5}))
    assert alto.costo_total_usd > bajo.costo_total_usd


def test_mas_cola_mas_perdida_pero_con_rendimiento_decreciente():
    perdidas = [calcular(replace(BASE, cola_min_por_ciclo=c)).horas_camion_perdidas for c in (1, 2, 3, 4)]
    assert perdidas == sorted(perdidas)
    saltos = [b - a for a, b in zip(perdidas, perdidas[1:])]
    # cada minuto extra pesa algo menos, porque también se hacen menos ciclos
    assert saltos == sorted(saltos, reverse=True)


def test_periodos_escalan_correctamente():
    r = calcular(BASE)
    turnos_anio = BASE.turnos_por_dia * BASE.dias_operativos_anio
    assert r.por_periodo("anio")["costo_total_usd"] == pytest.approx(r.costo_total_usd * turnos_anio)
    assert r.por_periodo("dia")["horas_camion_perdidas"] == pytest.approx(r.horas_camion_perdidas * BASE.turnos_por_dia)
    assert r.por_periodo("mes")["toneladas_no_movidas"] == pytest.approx(r.toneladas_no_movidas * BASE.turnos_por_dia * 30)
    with pytest.raises(ValueError):
        r.por_periodo("semana")


def test_valor_de_un_minuto_usa_un_minuto():
    esperado = calcular(replace(BASE, cola_min_por_ciclo=1)).por_periodo("anio")
    assert valor_de_un_minuto(replace(BASE, cola_min_por_ciclo=4)) == esperado


# ------------------------------------------------------------ validaciones

@pytest.mark.parametrize("cambio", [
    {"n_camiones": 0},
    {"capacidad_t": -1},
    {"ciclo_sin_cola_min": 0},
    {"cola_min_por_ciclo": -0.5},
    {"horas_efectivas_turno": 25},
    {"fraccion_mineral": 1.2},
    {"recuperacion_pct": 101},
    {"ley_cu_pct": -1},
    {"precio_cu_usd_lb": -2},
    {"costo_proceso_usd_t": -1},
    {"cuello_de_botella": "chancadora"},
])
def test_entradas_invalidas(cambio):
    with pytest.raises(ValueError):
        calcular(replace(BASE, **cambio))
