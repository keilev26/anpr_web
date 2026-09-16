locals {
  name       = "anpr-${var.stage}"
  ssm_prefix = "/anpr/${var.stage}"

  infer_enabled = var.infer_image_tag != ""

  # Rellenados a mano con infra/scripts/set_secrets.sh. Terraform los crea con un
  # valor de relleno y luego los ignora: así no quedan en texto plano en el estado.
  manual_secrets = {
    database_url   = "URL de Aiven: mysql+aiomysql://usuario:clave@host:puerto/defaultdb"
    db_ssl_ca      = "Certificado CA de Aiven (PEM completo)"
    secret_key     = "Clave de firma JWT: python -c 'import secrets;print(secrets.token_urlsafe(48))'"
    device_api_key = "Clave que presenta la Raspberry en X-Device-Key"
  }
}
