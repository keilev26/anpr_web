resource "aws_ssm_parameter" "manual" {
  for_each = local.manual_secrets

  name        = "${local.ssm_prefix}/${each.key}"
  description = each.value
  # SecureString estándar: cifrado con la clave gestionada de SSM, sin costo.
  # (Secrets Manager cobraría $0,40/secreto/mes.)
  type  = "SecureString"
  tier  = "Standard"
  value = "PENDIENTE"

  lifecycle {
    ignore_changes = [value]
  }
}

# Secreto compartido entre CloudFront (cabecera que añade) y la API (que la exige).
# Sí queda en el estado: CloudFront necesita el valor en su configuración.
resource "random_password" "origin_verify" {
  length  = 48
  special = false
}

resource "aws_ssm_parameter" "origin_verify" {
  name  = "${local.ssm_prefix}/origin_verify_secret"
  type  = "SecureString"
  tier  = "Standard"
  value = random_password.origin_verify.result
}
