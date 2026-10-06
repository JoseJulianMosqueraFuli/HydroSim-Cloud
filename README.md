# HydroSim Cloud

Modernizacion cloud-native de una plataforma de modelado hidraulico en AWS.

El objetivo es ejecutar escenarios de simulacion de forma automatizada y escalable, integrar datos curados de Amazon Redshift con el software ISV y medir el rendimiento de cada ejecucion.

## Estado del proyecto

En etapa de definicion. La arquitectura y las fases propuestas estan en [docs/plan-inicial.md](docs/plan-inicial.md). No hay infraestructura desplegada.

## Proximos pasos

1. Confirmar las decisiones y restricciones de la seccion "Decisiones necesarias".
2. Crear la estructura Terraform y una estrategia segura de estado remoto.
3. Implementar primero un flujo vertical minimo en un entorno no productivo.
4. Validar y revisar el plan de Terraform antes de cualquier despliegue.

No se deben aplicar cambios en AWS hasta confirmar la cuenta, region, entorno, limites de gasto y autorizacion de despliegue.
