# HydroSim Cloud

Modernizacion cloud-native de una plataforma de modelado hidraulico en AWS.

El objetivo es ejecutar escenarios de simulacion de forma automatizada y escalable, integrar datos curados de Amazon Redshift con el software ISV y medir el rendimiento de cada ejecucion.

## Estado del proyecto

En etapa de definicion/construccion de la fundacion Terraform. HEC-RAS es el motor de referencia para rios e inundaciones en EE. UU., no una seleccion confirmada por la vacante. No hay infraestructura desplegada.

La arquitectura, los supuestos y las decisiones pendientes estan en [docs/plan-inicial.md](docs/plan-inicial.md). La fundacion Terraform esta en [infra/](infra/).

## Proximos pasos

1. Confirmar las decisiones y restricciones de la seccion "Decisiones necesarias".
2. Validar la ejecucion automatizada de HEC-RAS y su compatibilidad con AWS Batch; no asumir que un job Windows se puede ejecutar en Batch.
3. Completar la fundacion Terraform para `dev` y revisar el plan antes del despliegue.
4. Implementar el flujo vertical minimo en un entorno no productivo.

No se deben aplicar cambios en AWS hasta confirmar la cuenta, region, entorno, limites de gasto y autorizacion de despliegue.
