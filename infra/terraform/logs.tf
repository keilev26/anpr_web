# Creados explícitamente para fijar la retención. Si los crea Lambda por su cuenta
# quedan con retención infinita, y los logs son lo que más crece sin que se note.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}-api"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "infer" {
  name              = "/aws/lambda/${local.name}-infer"
  retention_in_days = 7
}
