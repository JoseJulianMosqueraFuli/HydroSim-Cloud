# Plan inicial — HydroSim Cloud

## 1. Objetivo

Modernizar la ejecucion de modelos hidraulicos como un servicio automatizado en AWS. La plataforma debe iniciar escenarios de forma controlada, obtener sus datos desde capas curadas de Redshift, ejecutar el software ISV en capacidad escalable y conservar entradas, resultados y metricas para auditoria y analisis.

Este documento es una propuesta inicial, no una especificacion final. La vacante no nombra el ISV ni el sistema operativo. Para dar un punto de partida orientado a Estados Unidos, HEC-RAS sera el motor de referencia para el caso de rios/inundaciones; no significa que sea el motor del cliente ni que exista un ranking universal de uso para todos los tipos de modelado hidraulico. La ejecucion de HEC-RAS, la compatibilidad con AWS Batch y el sistema operativo del worker quedan sujetos a una prueba tecnica antes de fijar el diseño.

## 2. Alcance inicial propuesto

### Incluido en el MVP

- Infraestructura reproducible con Terraform y separacion por entorno.
- Recepcion autenticada de solicitudes para ejecutar escenarios y consultar su estado.
- Orquestacion de escenarios y manejo de errores con AWS Step Functions.
- Cola y computo elastico para modelos con AWS Batch sobre instancias EC2.
- Integracion desacoplada entre Redshift, almacenamiento de archivos de entrada/salida y los workers de simulacion.
- Registro de estado, logs, metricas de duracion y trazabilidad por `scenario_id`.
- Despliegue inicial en un entorno no productivo, una vez aprobados cuenta, region y costo.

### Fuera del MVP, salvo confirmacion

- Alta disponibilidad multi-region.
- Interfaz web completa y portal de usuarios.
- Reemplazo o cambios en el software ISV.
- Promesa de compatibilidad con modelos Windows/Linux o formatos de datos aun no confirmados.
- Reprocesamiento historico masivo o analitica avanzada de resultados.

## 3. Arquitectura propuesta

```text
Cliente / sistema llamador
          |
   API de control
          |
          v
   AWS Step Functions <---- Amazon EventBridge (disparadores programados/eventos)
          |
          +---- lee/extrae datos curados desde Redshift
          |       y materializa archivos en Amazon S3
          |
          +---- fan-out de escenarios -> AWS Batch Job Queue
          |                              |
          |                              v
          |                    Compute Environment (EC2)
          |                    contenedor/worker ISV
          |                              |
          +<----- estado/resultado ------+
                                         |
                              S3: entradas, salidas,
                              manifiestos y artefactos
                                         |
                          carga de resultados a Redshift
```

### Componentes

| Componente | Responsabilidad inicial |
| --- | --- |
| API de control | Aceptar solicitudes pequenas, validar parametros, iniciar ejecuciones y devolver identificadores/estado. No transportar archivos grandes. |
| Step Functions | Administrar el ciclo del escenario, reintentos acotados, timeouts, paralelismo, errores y estado final. |
| EventBridge | Iniciar ejecuciones por calendario o por eventos aprobados; evitar acoplar productores y consumidores. |
| AWS Batch | Encolar trabajos Linux compatibles y asignar capacidad EC2 segun demanda, recursos del modelo y limites configurados. No asumir compatibilidad de jobs Windows con Batch sin prueba documentada. |
| EC2 / worker de simulacion | Ejecutar una unidad de simulacion en un entorno reproducible compatible con el motor y su licencia. HEC-RAS es el motor de referencia inicial; validar ejecucion headless, SO y mecanismo de paralelismo. Si exige Windows, evaluar un pool EC2 Windows separado y su integracion con Step Functions. |
| Amazon S3 | Intercambiar conjuntos de entrada/salida y guardar manifiestos versionados por ejecucion. |
| Amazon Redshift | Fuente de datos curados y, si se confirma, destino de resultados estructurados. |
| Observabilidad | CloudWatch Logs/Metrics y alarmas de cola, fallos, duracion, capacidad y costo operacional. |
| Terraform | Declarar redes, IAM, buckets, orquestacion, Batch, integraciones y recursos de observabilidad por entorno. |

### Flujo de una ejecucion

1. Un cliente solicita un escenario a la API o un evento autorizado lo inicia.
2. La API valida la solicitud y lanza una ejecucion de Step Functions con un `scenario_id` y una referencia a la configuracion, no con datos sensibles en el historial.
3. El flujo prepara el conjunto de entrada desde Redshift. Se evaluara Redshift Data API y/o `UNLOAD` a S3 segun volumen, latencia y permisos. El worker no recibira credenciales incrustadas.
4. Step Functions divide una solicitud en trabajos independientes y los envia a AWS Batch si el motor puede ejecutarse en su entorno compatible. La concurrencia maxima es configurable.
5. El worker descarga las entradas, ejecuta el motor, escribe logs y artefactos de salida en S3 y reporta estado/metricas. Si HEC-RAS requiere Windows, primero se debe diseñar y validar una ruta Windows en EC2; no se presentara como un job Batch soportado sin demostrarlo.
6. El flujo consolida el resultado, opcionalmente carga datos tabulares a Redshift y publica el estado terminal.
7. Se conservan metadatos de ejecucion para poder consultar duracion, consumo, resultado y causa de fallo.

La forma exacta de fan-out (por ejemplo, `Map` distribuido o trabajos Batch array) se decidira con el tamano de lote, cuotas y limites de concurrencia reales. No se asumira que ambos mecanismos son necesarios.

## 4. Diseno de infraestructura y controles

- **Entornos:** empezar con `dev`; promover a `stage`/`prod` con configuracion separada, no con recursos compartidos accidentalmente.
- **Red:** workers en subredes privadas. Definir acceso de salida minimo, endpoints necesarios y estrategia de descarga/actualizacion del software. NAT Gateway y endpoints privados tienen impacto de costo que debe compararse antes de elegir.
- **Datos:** buckets separados o prefijos claramente aislados por entorno; cifrado, bloqueo de acceso publico, politicas de ciclo de vida y versionado segun requisitos de retencion.
- **IAM:** roles distintos para Step Functions, Batch, worker y API; permisos de menor privilegio y secretos/licencias en un gestor de secretos cuando aplique.
- **Ejecucion:** limites de CPU/memoria, reintentos, timeout, prioridad, concurrencia y capacidad maxima definidos para evitar tormentas de trabajos y gasto inesperado.
- **Costos:** etiquetas obligatorias, budgets/alertas, limites de capacidad Batch, limpieza de datos temporales y medicion de costo por escenario.
- **Estado Terraform:** backend remoto cifrado con bloqueo de estado (por ejemplo, S3 y locking soportado por la version elegida de Terraform). Bootstrapping y permisos se documentaran antes de aplicarlo.
- **Entrega:** formato, validacion, pruebas y revision de `terraform plan` automatizados; secretos y archivos de estado nunca se guardan en Git.

## 5. Fases de construccion

### Fase 0 — Descubrimiento y decisiones

- Confirmar ISV, version, sistema operativo, empaquetado, dependencias, licencia y ejecucion sin interfaz grafica.
- Perfilar una simulacion representativa: CPU, RAM, disco, duracion, tamano de entradas/salidas, concurrencia y tolerancia a interrupciones.
- Identificar Redshift (cuenta/cluster o Serverless, region, conectividad, tablas/vistas curadas), contratos de datos y estrategia de escritura de resultados.
- Definir quien solicita escenarios, autenticacion/autorizacion, volumen esperado, SLO, retencion, RPO/RTO y clasificacion de datos.
- Confirmar cuenta AWS, region, convenciones, restricciones organizacionales, presupuesto y autorizacion de despliegue.

**Salida:** ADRs aprobados y criterios de aceptacion del MVP.

### Fase 1 — Fundacion Terraform

- Estructura por modulos y entornos, versionado fijado de Terraform/proveedores y validaciones CI.
- Backend remoto y bootstrap del estado; convenciones de tags, nombres, IAM y cifrado.
- VPC/subredes, grupos de seguridad y estrategia de conectividad basada en requisitos.
- S3 para intercambio y artefactos, cifrado, politicas de acceso y retencion.

**Salida:** `terraform fmt`, `validate`, pruebas estaticas y plan revisable para `dev`.

### Fase 2 — Ejecucion de un escenario

- Construir imagen/paquete del worker compatible con el ISV y proceso de licencia.
- Configurar AWS Batch (compute environment, job queue, job definition) con capacidad y limites iniciales.
- Ejecutar un escenario de prueba con entradas controladas y resultados reproducibles.
- Registrar metricas: preparacion, espera en cola, ejecucion, transferencia, CPU/RAM y resultado.

**Salida:** un trabajo ejecutado de extremo a extremo, medible y repetible.

### Fase 3 — Orquestacion e integracion de datos

- Implementar Step Functions con validaciones, estados, reintentos, timeouts y manejo de fallos.
- Integrar Redshift -> S3 -> worker y, si se requiere, worker -> S3 -> Redshift.
- Incorporar solicitudes API y disparadores EventBridge autorizados.
- Probar ejecucion serial, paralela, duplicada, cancelada y fallida.

**Salida:** flujo vertical automatizado con trazabilidad completa por escenario.

### Fase 4 — Endurecimiento y optimizacion

- Carga/concurrencia, pruebas de resiliencia y limites/quota de AWS.
- Ajustar tipos de instancia, autoscaling, paralelismo, almacenamiento, caché y transferencia usando datos de perfilado.
- Alarmas, dashboards, runbooks, politicas de retencion, seguridad y recuperacion.
- Revisar costo por escenario y objetivos de rendimiento con stakeholders.

**Salida:** criterios de produccion medidos y aceptados.

### Fase 5 — Despliegue gradual y operacion

- Promocion controlada de `dev` a `stage` y `prod` por pipeline y aprobaciones.
- Planes de rollback, soporte, ownership operativo y handoff documentado.
- Revisiones periodicas de costos, rendimiento, cuotas, vulnerabilidades y cambios del ISV.

**Salida:** plataforma operable, con responsabilidades y controles acordados.

## 6. Decisiones necesarias antes de implementar

1. **Simulador:** la vacante no da nombre/version del ISV. Motor de referencia para el caso de uso estadounidense: HEC-RAS para rios/inundaciones. Confirmar que el dominio aplica, la version, automatizacion sin GUI, SO soportado, dependencias, metodo de distribucion y compatibilidad con Batch.
2. **Carga:** recursos por ejecucion y distribucion de duraciones; escenarios simultaneos promedio/pico y tiempo objetivo de respuesta.
3. **Datos:** Redshift existente (provisionado o Serverless), region/cuenta, volumen, frecuencia, esquema de entradas y formato/consumidor de resultados.
4. **Interfaz:** ¿quien dispara escenarios y como se autentica? ¿Se necesita API publica, privada o solo ejecucion programada/event-driven?
5. **Entorno AWS:** ¿ya hay cuenta y region aprobadas? ¿Se puede crear VPC, NAT, endpoints, Batch, Step Functions y roles IAM?
6. **Operacion:** ambientes requeridos, presupuesto mensual/por escenario, retencion, SLO, RPO/RTO y requisitos de cumplimiento.

## 7. Riesgos y mitigaciones iniciales

| Riesgo | Mitigacion |
| --- | --- |
| Restricciones de sistema operativo/licencia del ISV | Validar con el partner antes de elegir imagen, AMI, contenedores o tipo de instancia. |
| Demanda de memoria/CPU o duracion desconocidas | Perfilar una carga representativa antes de fijar familias, limites y concurrencia. |
| Conectividad/costos de red | Comparar NAT, endpoints privados y transferencia requerida; modelar costos antes del despliegue. |
| Datos grandes o sensibles en flujos | Pasar referencias S3 y metadatos; no enviar payloads voluminosos ni secretos a historial de Step Functions. |
| Reintentos duplican trabajos o costos | Definir idempotencia por `scenario_id`, estados y politicas de reintento seguras. |
| Cuotas insuficientes o picos de demanda | Verificar cuotas por region y limitar capacidad/concurrencia con alertas. |
| Drift o exposicion del estado Terraform | Backend cifrado, bloqueo, acceso IAM restringido y controles para no versionar estado ni secretos. |

## 8. Criterios de aceptacion del MVP

- Una solicitud identificable puede completar un escenario real representativo de principio a fin.
- Las entradas y salidas se vinculan a un `scenario_id`, con permisos y retencion definidos.
- Se puede consultar estado, errores, logs y tiempos por etapa sin acceder manualmente a la instancia.
- La concurrencia y el maximo de capacidad son configurables y tienen limites.
- La integracion Redshift tiene contratos de datos probados y no usa credenciales embebidas.
- La infraestructura se puede planificar y desplegar desde Terraform de forma repetible en `dev`.
- Se conoce el costo aproximado por escenario y existen alertas/limites acordados.
- Hay instrucciones de operacion, fallos conocidos y procedimiento de despliegue/rollback.

## 9. Siguiente paso

Completar las seis decisiones de la seccion 6. Con esas respuestas, convertir el plan en ADRs breves y empezar la Fase 1, incluyendo `terraform plan` para revision. No ejecutar `terraform apply` ni crear recursos de pago hasta que se aprueben explicitamente cuenta, region, alcance y presupuesto.

### Nota sobre la eleccion del motor

No existe un unico simulador hidraulico "mas usado" para todos los casos, ni una estadistica publica unica que permita afirmar un lider mundial para todos los dominios. HEC-RAS es una referencia habitual en Estados Unidos para rios e inundaciones y lo desarrolla el Hydrologic Engineering Center del USACE; EPA SWMM es frecuente en drenaje pluvial/urbano y EPANET en redes de distribucion de agua. La vacante solo dice "ISV simulation software", asi que no permite inferir cual requiere el cliente y HEC-RAS no es un ISV comercial. La recomendacion es desacoplar el contrato de datos y la orquestacion del motor. Antes de comprometer la ruta HEC-RAS + Batch, verificar por prueba tecnica si el motor se ejecuta de forma automatizada en una imagen Linux compatible. Si requiere Windows, comparar un pool EC2 Windows orquestado por Step Functions con el requisito Batch, y decidir si Batch se mantiene para trabajos compatibles o si se cambia el motor. La documentacion consultada de AWS Batch describe entornos ECS y AMIs ECS optimizadas; no se debe inferir de ella soporte de jobs Windows.

Referencia oficial: [HEC-RAS — USACE Hydrologic Engineering Center](https://www.hec.usace.army.mil/software/hec-ras/), que describe sus capacidades para flujo 1D/2D, sedimentos, redes pluviales y calidad de agua.
