# Plan inicial — HydroSim Cloud

## 1. Objetivo

Modernizar la ejecucion de modelos hidraulicos como un servicio automatizado en AWS. La plataforma debe iniciar escenarios de forma controlada, obtener sus datos desde capas curadas de Redshift, ejecutar el software ISV en capacidad escalable y conservar entradas, resultados y metricas para auditoria y analisis.

Este documento es una propuesta inicial, no una especificacion final. La vacante no nombra el ISV ni el sistema operativo. Para dar un punto de partida orientado a Estados Unidos, HEC-RAS sera el motor de referencia para el caso de rios/inundaciones; no significa que sea el motor del cliente ni que exista un ranking universal de uso para todos los tipos de modelado hidraulico. La ejecucion de HEC-RAS, la compatibilidad con AWS Batch y el sistema operativo del worker quedan sujetos a una prueba tecnica antes de fijar el diseño.

## 2. Alcance inicial propuesto

### Incluido en el MVP

- Infraestructura reproducible con Terraform y separacion por entorno.
- Recepcion autenticada de solicitudes para ejecutar escenarios y consultar su estado.
- Orquestacion de escenarios y manejo de errores con AWS Step Functions.
- Ejecucion HEC-RAS en workers EC2 Windows orquestados por Step Functions; AWS Batch para trabajos Linux auxiliares.
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
          +---- trabajos Linux auxiliares -> AWS Batch
          |
          +---- escenarios HEC-RAS -> EC2 Windows
                                      |
                                      +-- Systems Manager (SSM)
                                      +-- descarga/resultado en S3
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
| AWS Batch | Ejecutar tareas Linux auxiliares (preparacion y/o postproceso de datos) con capacidad EC2 elastica. No ejecuta HEC-RAS en esta arquitectura. |
| EC2 Windows / worker HEC-RAS | Ejecutar una unidad de simulacion en una AMI controlada, con version de HEC-RAS, licencia, agente SSM y rol de instancia de minimo privilegio. |
| AWS Systems Manager | Ejecutar comandos y recuperar estado del worker Windows sin abrir acceso administrativo entrante a la instancia. |
| Amazon S3 | Intercambiar conjuntos de entrada/salida y guardar manifiestos versionados por ejecucion. |
| Amazon Redshift | Fuente de datos curados y, si se confirma, destino de resultados estructurados. |
| Observabilidad | CloudWatch Logs/Metrics y alarmas de cola, fallos, duracion, capacidad y costo operacional. |
| Terraform | Declarar redes, IAM, buckets, orquestacion, Batch, integraciones y recursos de observabilidad por entorno. |

### Flujo de una ejecucion

1. Un cliente solicita un escenario a la API o un evento autorizado lo inicia.
2. La API valida la solicitud y lanza una ejecucion de Step Functions con un `scenario_id` y una referencia a la configuracion, no con datos sensibles en el historial.
3. Para el MVP, el flujo obtiene los archivos de entrada desde S3 de prueba. Cuando exista Redshift, se evaluara Redshift Data API y/o `UNLOAD` a S3 segun volumen, latencia y permisos. El worker no recibira credenciales incrustadas.
4. Step Functions divide la solicitud en escenarios independientes y limita la concurrencia. AWS Batch procesa tareas Linux auxiliares; EC2 Windows ejecuta los trabajos HEC-RAS.
5. Para cada escenario, Step Functions crea o asigna un worker Windows, espera a que SSM lo registre, envia el comando de simulacion y consulta el resultado. El worker descarga entradas y sube resultados/logs a S3. El flujo termina la instancia en una rama de limpieza tanto en exito como en fallo.
6. El flujo consolida el resultado, opcionalmente carga datos tabulares a Redshift y publica el estado terminal.
7. Se conservan metadatos de ejecucion para poder consultar duracion, consumo, resultado y causa de fallo.

La forma exacta de fan-out (por ejemplo, `Map` distribuido o trabajos Batch array) se decidira con el tamano de lote, cuotas y limites de concurrencia reales. No se asumira que ambos mecanismos son necesarios.

## 4. Diseno de infraestructura y controles

- **Entornos:** empezar con `dev`; promover a `stage`/`prod` con configuracion separada, no con recursos compartidos accidentalmente.
- **Red:** workers en subredes privadas. Definir acceso de salida minimo, endpoints necesarios y estrategia de descarga/actualizacion del software. NAT Gateway y endpoints privados tienen impacto de costo que debe compararse antes de elegir.
- **Datos:** buckets separados o prefijos claramente aislados por entorno; cifrado, bloqueo de acceso publico, politicas de ciclo de vida y versionado segun requisitos de retencion.
- **IAM:** roles distintos para Step Functions, Batch, worker y API; permisos de menor privilegio y secretos/licencias en un gestor de secretos cuando aplique.
- **Ejecucion:** limites de CPU/memoria, reintentos, timeout, prioridad, concurrencia y capacidad maxima definidos para evitar tormentas de trabajos y gasto inesperado. Medir costo de arranque, horas de EC2 Windows y licenciamiento por escenario. El MVP empieza con un solo worker Windows temporal y sin paralelismo de workers hasta tener mediciones.
- **Costos:** objetivo inicial de USD 100/mes para `dev`, etiquetas obligatorias, budgets/alertas, limites de capacidad Batch, limpieza de datos temporales y medicion de costo por escenario. Evitar NAT Gateway y servicios/instancias permanentes hasta comparar costos. Las alertas de AWS Budgets notifican, pero no imponen un limite de gasto.
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

- Crear una AMI Windows reproducible con HEC-RAS y SSM; validar automatizacion sin GUI, licencia, arranque y ejecucion.
- Configurar AWS Batch para tareas Linux auxiliares solo si el flujo las necesita, con capacidad y limites iniciales.
- Probar lanzamiento, ejecucion, captura del resultado y terminacion de un worker HEC-RAS Windows.
- Registrar metricas: preparacion, espera en cola, ejecucion, transferencia, CPU/RAM y resultado.

**Salida:** un trabajo ejecutado de extremo a extremo, medible y repetible.

### Fase 3 — Orquestacion e integracion de datos

- Implementar Step Functions con validaciones, estados, reintentos, timeouts y limpieza garantizada de instancias Windows en fallos.
- Integrar Redshift -> S3 -> worker y, si se requiere, worker -> S3 -> Redshift.
- Incorporar solicitudes API y disparadores EventBridge autorizados.
- Usar AWS Batch para transformaciones Linux auxiliares y paralelizar escenarios HEC-RAS mediante EC2 Windows con limites explicitos de concurrencia/cuota.
- Probar ejecucion serial, paralela, duplicada, cancelada, fallida y limpieza tras interrupcion.

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

1. **Simulador:** la vacante no da nombre/version del ISV. Motor de referencia para el caso de uso estadounidense: HEC-RAS para rios/inundaciones. Confirmar que el dominio aplica, la version, automatizacion sin GUI, SO soportado, dependencias, metodo de distribucion y licencia.
2. **Carga:** recursos por ejecucion y distribucion de duraciones; escenarios simultaneos promedio/pico y tiempo objetivo de respuesta.
3. **Datos:** se acordo iniciar con archivos de prueba en S3; Redshift se integrara cuando haya un entorno/dataset disponible. Definir volumen, frecuencia, esquemas y formato/consumidor de resultados en esa fase.
4. **Interfaz:** ¿quien dispara escenarios y como se autentica? ¿Se necesita API publica, privada o solo ejecucion programada/event-driven?
5. **Entorno AWS:** ¿ya hay cuenta y region aprobadas? ¿Se puede crear VPC, NAT, endpoints, Batch, Step Functions y roles IAM?
6. **Operacion:** ambientes requeridos, presupuesto mensual/por escenario, retencion, SLO, RPO/RTO y requisitos de cumplimiento.

### Decisiones acordadas para el arranque

- Motor de referencia: HEC-RAS para rios/inundaciones en EE. UU.; es una hipotesis de proyecto, no el ISV nombrado por la vacante ni una confirmacion del cliente.
- Ejecucion: HEC-RAS en EC2 Windows, orquestado por Step Functions y administrado con SSM. AWS Batch queda para tareas Linux auxiliares; esta decision no equivale a ejecutar los modelos con Batch y requiere validacion con stakeholders.
- Region de desarrollo propuesta: `us-east-1`, pendiente de confirmar que cumple las politicas del cliente.
- Datos iniciales: archivos de prueba en S3; no hay Redshift existente confirmado.
- Presupuesto de diseno: USD 100/mes para `dev`; mantener workers bajo demanda y limitar inicialmente la concurrencia a uno.

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

Completar las decisiones operativas pendientes de la seccion 6, convertir las elecciones de arranque en ADRs breves y avanzar la Fase 1. No ejecutar `terraform apply` ni crear recursos de pago hasta que se aprueben explicitamente cuenta, region, alcance y presupuesto.

### Nota sobre la eleccion del motor

No existe un unico simulador hidraulico "mas usado" para todos los casos, ni una estadistica publica unica que permita afirmar un lider mundial para todos los dominios. HEC-RAS es una referencia habitual en Estados Unidos para rios e inundaciones y lo desarrolla el Hydrologic Engineering Center del USACE; EPA SWMM es frecuente en drenaje pluvial/urbano y EPANET en redes de distribucion de agua. La vacante solo dice "ISV simulation software", asi que no permite inferir cual requiere el cliente y HEC-RAS no es un ISV comercial. La decision provisional es desacoplar el contrato de datos y ejecutar HEC-RAS en EC2 Windows orquestado por Step Functions; AWS Batch queda para trabajos Linux auxiliares. Esto conserva Batch en la plataforma, pero no cumple literalmente el requisito de usar Batch para ejecutar los modelos, por lo que debe validarse con los stakeholders. La documentacion consultada de AWS Batch describe entornos ECS y AMIs ECS optimizadas, no un flujo de ejecucion Windows documentado.

Referencias oficiales: [HEC-RAS — USACE Hydrologic Engineering Center](https://www.hec.usace.army.mil/software/hec-ras/), que describe sus capacidades para flujo 1D/2D, sedimentos, redes pluviales y calidad de agua; [AWS Batch compute environments](https://docs.aws.amazon.com/batch/latest/userguide/compute_environments.html) y [compute resource AMIs](https://docs.aws.amazon.com/batch/latest/userguide/compute_resource_AMIs.html).
