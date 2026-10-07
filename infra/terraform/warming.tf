# Ping de calentamiento para el Lambda de inferencia.
#
# Medido el 2026-10-07: con el contenedor en frío (sin uso reciente), la
# primera invocación real tarda ~55 s por culpa del arranque (bajar la imagen
# de 3,4 GB, inicializar Python, cargar YOLO/ONNX y PaddleOCR). El presupuesto
# del camino crítico es 4 s. Sin esto, un auto que llega tras un rato de
# inactividad no recibiría veredicto a tiempo y la Pi no abriría.
#
# EventBridge invoca el Lambda cada 5 minutos con una foto mínima de prueba
# (un cuadrado gris de 64x64, sin placa: solo para que el pipeline se cargue
# y quede en memoria, no para leer nada). No pasa por la API ni gasta el cupo
# de autenticación del dispositivo.

locals {
  # 3 copias: igual forma que una ráfaga real (el contrato pide al menos 3),
  # aunque al no haber placa el consenso nunca se cumple — no es el objetivo.
  warmup_frame = trimspace(file("${path.module}/files/warmup_frame.b64"))
  warmup_payload = jsonencode({
    frames = [local.warmup_frame, local.warmup_frame, local.warmup_frame]
  })
}

resource "aws_cloudwatch_event_rule" "warm_infer" {
  count               = local.infer_enabled ? 1 : 0
  name                = "${local.name}-warm-infer"
  description         = "Mantiene tibio el Lambda de inferencia (evita el arranque en frío, ~55 s)"
  schedule_expression = "rate(5 minutes)"
}

resource "aws_cloudwatch_event_target" "warm_infer" {
  count = local.infer_enabled ? 1 : 0
  rule  = aws_cloudwatch_event_rule.warm_infer[0].name
  arn   = aws_lambda_function.infer[0].arn
  input = local.warmup_payload
}

resource "aws_lambda_permission" "warm_infer" {
  count         = local.infer_enabled ? 1 : 0
  statement_id  = "AllowEventBridgeWarming"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.infer[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.warm_infer[0].arn
}
