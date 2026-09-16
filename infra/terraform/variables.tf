variable "region" {
  description = "us-east-1: la región más barata. sa-east-1 cuesta 30-50 % más."
  type        = string
  default     = "us-east-1"
}

variable "stage" {
  description = "Etapa del despliegue. Forma parte de los nombres y del prefijo de SSM."
  type        = string
  default     = "prueba"
}

variable "create_budget" {
  description = <<-EOT
    Crear un presupuesto con alertas. Desactivado: la cuenta ya tiene "My Zero-Spend
    Budget" (avisa por correo desde $0,01) y "My Monthly Cost Budget" ($10), que cubren
    la prueba. Activarlo solo en una cuenta sin alertas propias.
  EOT
  type        = bool
  default     = false
}

variable "alert_email" {
  description = "Correo para las alarmas de la API (errores y throttles) y el presupuesto. Vacío = sin alarmas."
  type        = string
  default     = ""
}

variable "budget_usd" {
  description = "Presupuesto mensual. Alerta al 20 % real y al 100 % previsto."
  type        = number
  default     = 5
}

variable "api_zip_path" {
  description = "Paquete de la API construido con infra/scripts/build_api_zip.sh."
  type        = string
  default     = "../build/api.zip"
}

variable "infer_image_tag" {
  description = <<-EOT
    Tag de la imagen de inferencia en ECR. Vacío = el Lambda de inferencia NO se crea
    (primer apply: solo existe el repositorio ECR para poder subir la imagen).
  EOT
  type        = string
  default     = ""
}
