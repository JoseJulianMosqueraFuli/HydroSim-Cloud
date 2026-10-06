# Terraform

## Estructura

- `bootstrap/`: crea el bucket versionado y cifrado que almacenara los estados de los entornos.
- `environments/dev/`: configura el backend remoto y recursos iniciales de desarrollo.

El bootstrap empieza con estado local porque el bucket remoto todavia no existe. `*.tfstate` esta excluido de Git; conserva el estado local de bootstrap de forma segura y no lo compartas. El estado del entorno `dev` usa backend S3 con cifrado y bloqueo nativo por archivo (`use_lockfile`), disponible en Terraform 1.10 o superior.

## Requisitos previos

- Terraform 1.10 o superior.
- AWS CLI configurado con credenciales autorizadas para la cuenta objetivo.
- Cuenta, region y nombres/tags aprobados.
- Acceso IAM minimo para crear y administrar los recursos del bootstrap y del entorno.

## Inicializar y revisar

Primero copia `bootstrap/terraform.tfvars.example` a `bootstrap/terraform.tfvars` y fija la region aprobada. Desde `infra/bootstrap/`, ejecuta:

```sh
terraform init
terraform fmt -check
terraform validate
terraform plan
```

Revisa el plan. `terraform apply` crea recursos en AWS y requiere aprobacion explicita de cuenta, region y costo. No lo ejecutes automaticamente desde CI.

Cuando el bucket exista, copia el valor de `terraform output -raw state_bucket_name`. Copia `environments/dev/terraform.tfvars.example` a `environments/dev/terraform.tfvars` y fija la misma region. Desde `infra/environments/dev/`, inicializa el backend pasando el bucket y region aprobados:

```sh
terraform init \
  -backend-config="bucket=<state-bucket-name>" \
  -backend-config="region=<approved-region>"
terraform fmt -check
terraform validate
terraform plan
```

El primer plan de `dev` propone crear un bucket de artefactos privado, versionado, cifrado y con denegacion de transporte no TLS. No se incluyen aun VPC, AWS Batch ni ejecucion HEC-RAS: primero se deben confirmar Redshift, conectividad, retencion, costos y compatibilidad del motor.

## Seguridad y operacion

- No guardes `terraform.tfvars`, credenciales, estado ni planes con datos sensibles en Git.
- El bucket de estado usa versionado y bloqueo de acceso publico; los permisos IAM deben limitarse a los operadores/pipelines aprobados.
- El bucket de artefactos no tiene expiracion automatica hasta que se defina una politica de retencion.
- Los buckets tienen `prevent_destroy`; eliminar o reemplazar datos requiere un cambio revisado y aprobado.
- Guarda `.terraform.lock.hcl` en Git despues de la primera inicializacion para fijar las versiones seleccionadas del proveedor.
