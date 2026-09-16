terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Estado local para la fase de prueba. Contiene el secreto de origen de
  # CloudFront: está en .gitignore y NO debe commitearse.
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      proyecto = "anpr"
      etapa    = var.stage
      gestion  = "terraform"
    }
  }
}
