# Alarmas de la API. Las 10 primeras alarmas y los correos de SNS son gratuitos.
# Sin alert_email no se crea nada: una alarma sin nadie que la reciba no sirve.

locals {
  alarms_enabled = var.alert_email != ""
}

resource "aws_sns_topic" "alerts" {
  count = local.alarms_enabled ? 1 : 0
  name  = "${local.name}-alertas"
}

# AWS envía un correo de confirmación: hasta aceptarlo, no llega ninguna alerta.
resource "aws_sns_topic_subscription" "alerts_email" {
  count     = local.alarms_enabled ? 1 : 0
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

locals {
  api_alarms = {
    # Errores no controlados (500) o el contenedor muriendo por memoria/timeout.
    errors = {
      metric      = "Errors"
      description = "La API está fallando: revisar /aws/lambda/${local.name}-api"
    }
    # La cuenta llegó a su límite de ejecuciones simultáneas: peticiones rechazadas,
    # la puerta no abre. Puede ser un pico legítimo o alguien saturando la URL.
    throttles = {
      metric      = "Throttles"
      description = "Lambda rechaza peticiones por concurrencia: la puerta puede no responder"
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "api" {
  for_each = local.alarms_enabled ? local.api_alarms : {}

  alarm_name          = "${local.name}-api-${each.key}"
  alarm_description   = each.value.description
  namespace           = "AWS/Lambda"
  metric_name         = each.value.metric
  dimensions          = { FunctionName = aws_lambda_function.api.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching" # sin tráfico no es una alarma
  alarm_actions       = [aws_sns_topic.alerts[0].arn]
  ok_actions          = [aws_sns_topic.alerts[0].arn]
}
