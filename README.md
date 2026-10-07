# HydroSim Cloud

Modernizacion cloud-native de una plataforma de modelado hidraulico en AWS.

El objetivo es ejecutar escenarios de simulacion de forma automatizada y escalable, integrar datos curados de Amazon Redshift con el software ISV y medir el rendimiento de cada ejecucion.

## Estado del proyecto

El MVP de la API se ejecuta localmente y simula la recepcion, ejecucion y consulta de escenarios. Su motor `demo` genera una salida sintetica y **no realiza calculos hidraulicos**. La integracion real con HEC-RAS todavia no esta configurada. HEC-RAS es el motor de referencia para rios e inundaciones en EE. UU., no una seleccion confirmada por la vacante. La fundacion Terraform existe, pero no hay infraestructura desplegada.

La arquitectura, los supuestos y las decisiones pendientes estan en [docs/plan-inicial.md](docs/plan-inicial.md). La fundacion Terraform esta en [infra/](infra/).

## Ejecutar el MVP local

Requiere Python 3.11 o superior; no necesita instalar paquetes externos.

```sh
python -m hydrosim.api
```

La API escucha en `http://127.0.0.1:8080` y guarda estado local en `data/scenarios.sqlite3`. Para crear una ejecucion sintetica desde otra terminal:

```sh
curl -X POST http://127.0.0.1:8080/scenarios \
  -H 'Content-Type: application/json' \
  --data @examples/scenario.json
```

Consulta el estado con el `scenario_id` de la respuesta:

```sh
curl http://127.0.0.1:8080/scenarios/<scenario_id>
```

Rutas implementadas: `GET /health`, `POST /scenarios` y `GET /scenarios/{scenario_id}`. El modo local no tiene autenticacion: solo debe usarse en loopback y con datos no sensibles. No expongas el contenedor o servidor a una red compartida o publica.

Ejecuta las pruebas automatizadas con:

```sh
python -m unittest discover -s tests -v
```

## Despliegue AWS (prototipo)

La configuracion Terraform tambien incluye una HTTP API con autenticacion AWS IAM, Lambda, Step Functions, DynamoDB y el bucket privado. Usa `demo` como worker; este flujo **no instala ni ejecuta HEC-RAS y no crea Batch ni EC2**.

Con credenciales SSO activas y cuenta/región revisadas, inicializa `infra/environments/dev` siguiendo [infra/README.md](infra/README.md), genera y revisa `terraform plan` antes de cualquier `apply`. Objetivo de costo acordado para `dev`: USD 100/mes; es un objetivo, no un tope garantizado.

## Siguiente etapa

Probar el flujo AWS con `demo`, agregar tareas Batch Linux si el procesamiento las necesita, y diseñar el worker EC2/SSM para HEC-RAS luego de validar el software, la licencia, el modo automatizado y el presupuesto. Integrar Redshift cuando haya un entorno disponible. No ejecutar `terraform apply` hasta verificar la identidad de AWS, revisar el plan y confirmar el costo.
