data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_caller_identity" "current" {}

# ---------- API ----------

resource "aws_iam_role" "api" {
  name               = "${local.name}-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }

  statement {
    sid     = "LeerSecretos"
    actions = ["ssm:GetParametersByPath", "ssm:GetParameters"]
    resources = [
      "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}",
      "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}/*",
    ]
  }

  dynamic "statement" {
    for_each = local.infer_enabled ? [1] : []
    content {
      sid       = "InvocarInferencia"
      actions   = ["lambda:InvokeFunction"]
      resources = [aws_lambda_function.infer[0].arn]
    }
  }
}

resource "aws_iam_role_policy" "api" {
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# ---------- Inferencia ----------

resource "aws_iam_role" "infer" {
  name               = "${local.name}-infer"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "infer" {
  # Solo logs: la inferencia no toca base de datos ni secretos.
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.infer.arn}:*"]
  }
}

resource "aws_iam_role_policy" "infer" {
  role   = aws_iam_role.infer.id
  policy = data.aws_iam_policy_document.infer.json
}
