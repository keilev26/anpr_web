# ---------- API (FastAPI + Mangum) ----------

resource "aws_lambda_function" "api" {
  function_name    = "${local.name}-api"
  role             = aws_iam_role.api.arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "app.lambda_handler.handler"
  filename         = var.api_zip_path
  source_code_hash = filebase64sha256(var.api_zip_path)

  # Argon2 es deliberadamente costoso en CPU; en Lambda la CPU escala con la memoria.
  memory_size = 1024
  timeout     = 30

  environment {
    variables = merge(
      {
        SSM_PREFIX = local.ssm_prefix
        DEV_MODE   = "false" # cookie de refresh con Secure
        # Sin pool: conexiones de una invocación anterior quedan ligadas a otro
        # bucle de eventos y SQLAlchemy async falla.
        DB_NULLPOOL = "true"
      },
      local.infer_enabled ? { INFER_FUNCTION_NAME = aws_lambda_function.infer[0].function_name } : {}
    )
  }

  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.api]
}

# URL pública, pero la API rechaza con 403 lo que no traiga la cabecera secreta
# que añade CloudFront. Se descartó autenticación IAM + OAC: obliga a que el
# cliente firme el hash del cuerpo en cada POST, y ni el navegador ni la Pi lo hacen.
resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"
}

# Una Function URL pública necesita DOS permisos. Con solo el primero, AWS
# responde 403 a todas las peticiones: desde finales de 2025 exige también
# InvokeFunction restringido a llamadas que lleguen por la URL.
resource "aws_lambda_permission" "api_url" {
  statement_id           = "FunctionUrlPublica"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "api_url_invoke" {
  statement_id             = "FunctionUrlPublicaInvoke"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "*"
  invoked_via_function_url = true
}

# ---------- Inferencia (imagen de ml/Dockerfile) ----------

resource "aws_lambda_function" "infer" {
  count = local.infer_enabled ? 1 : 0

  function_name = "${local.name}-infer"
  role          = aws_iam_role.infer.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.infer.repository_url}:${var.infer_image_tag}"
  # x86_64: paddlepaddle no publica paquetes aarch64.
  architectures = ["x86_64"]

  # 10 GB = ~6 vCPU. A este volumen entra en los 400.000 GB-s/mes gratuitos.
  memory_size = 10240
  # El primer arranque carga YOLO y PaddleOCR; las siguientes invocaciones son rápidas.
  timeout = 60

  ephemeral_storage {
    size = 1024 # PaddleX escribe su caché en /tmp al importarse
  }

  depends_on = [aws_cloudwatch_log_group.infer, aws_iam_role_policy.infer]
}
