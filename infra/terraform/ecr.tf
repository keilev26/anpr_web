resource "aws_ecr_repository" "infer" {
  name                 = "${local.name}-infer"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true # que `terraform destroy` borre también las imágenes

  image_scanning_configuration {
    scan_on_push = true # escaneo básico, sin costo
  }
}

# ECR cobra por GB almacenado: con imágenes de ~3 GB, conservar solo las dos
# últimas (la actual y una para volver atrás).
resource "aws_ecr_lifecycle_policy" "infer" {
  repository = aws_ecr_repository.infer.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Conservar solo las 2 imágenes más recientes"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 2
      }
      action = { type = "expire" }
    }]
  })
}
