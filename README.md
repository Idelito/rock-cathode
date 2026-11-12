# ¿Cuánto vale un minuto de cola?

**Rock Cathode · Temporada 1 "Del despacho al plan" · Publicación 1**

Un minuto de cola por ciclo parece poco. Multiplicado por la flota, los ciclos y los turnos, se convierte en horas-camión, toneladas y dólares.
Pero **su valor depende de dónde está el cuello de botella**:

| Restricción del sistema | ¿Qué se pierde? |
|---|---|
| **Acarreo** | El margen del cobre que no llega a la planta. Las horas-camión se pagan igual. |
| **Planta** | Solo el costo de las horas-camión en cola. Mover más mineral no produce más cobre. |

Los dos costos son **alternativos**: no se suman.

![Sensibilidad](sensibilidad_cola.png)

## Lógica del cálculo (por turno)

```
ciclos por camión      = horas efectivas × 60 / (ciclo sin cola + cola)
horas-camión en cola   = camiones × ciclos × cola / 60
toneladas no movidas   = (minutos en cola / ciclo sin cola) × capacidad
Cu fino no producido   = t no movidas × % mineral × ley × recuperación × 2 204.62 lb/t
margen no capturado    = Cu fino × precio − t mineral × costo de proceso
```

## Uso

```bash
pip install -r requirements.txt
python minuto_cola.py                          # valores por defecto
python minuto_cola.py --cola 3 --camiones 40   # tu escenario
python minuto_cola.py --cuello planta          # planta como restricción
python minuto_cola.py --grafico                # genera sensibilidad_cola.png
python -m pytest -v                            # 24 pruebas
```

## Supuestos

- Todos los valores por defecto son **ilustrativos**. No provienen de ninguna operación real.
- El tiempo que hoy se pierde en cola se convertiría en ciclos productivos con el mismo ciclo sin cola.
- En el escenario de acarreo, se asume que la planta tiene capacidad para procesar el mineral adicional. El resultado es un **techo teórico**.
- No incluye costos de fundición y refinación, ni el efecto del desmonte no movido en el plan de minado futuro.

---
Edgar Mamani Ponaylos · Ingeniero de Gestión Minera
