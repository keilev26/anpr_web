# Opcional (create_budget): la cuenta de la prueba ya tiene alertas propias.
# Avisa temprano: a $1 real y si la previsión del mes supera el total.
resource "aws_budgets_budget" "monthly" {
  count = var.create_budget ? 1 : 0

  lifecycle {
    precondition {
      condition     = var.alert_email != ""
      error_message = "create_budget = true requiere alert_email."
    }
  }

  name         = "${local.name}-mensual"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 20
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
