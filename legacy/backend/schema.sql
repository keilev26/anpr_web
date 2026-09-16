-- Usa MySQL/InnoDB
SET NAMES utf8mb4;

-- El orden importa por FKs (primero hijas)
DROP TABLE IF EXISTS `event_detection`;
DROP TABLE IF EXISTS `list_car`;
DROP TABLE IF EXISTS `user`;
DROP TABLE IF EXISTS `login`;

-- Tabla de usuarios
CREATE TABLE `user` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL,
  `phone` VARCHAR(32),
  `email` VARCHAR(255) NOT NULL,
  `role` ENUM('student','teacher','administrator') NOT NULL DEFAULT 'student',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ux_user_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Tabla de vehículos registrados por usuarios
CREATE TABLE `list_car` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `plate` VARCHAR(16) NOT NULL,
  `user_id` INT UNSIGNED NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ux_list_car_plate` (`plate`),
  KEY `ix_list_car_user_id` (`user_id`),
  CONSTRAINT `fk_list_car_user`
    FOREIGN KEY (`user_id`) REFERENCES `user` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Tabla de detección de eventos (por cámara o sistema de visión)
CREATE TABLE `event_detection` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `plate` VARCHAR(16) NOT NULL,
  `datetime` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_event_detection_plate` (`plate`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Tabla de login simple (email y contraseña)
CREATE TABLE `login` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `email` VARCHAR(255) NOT NULL,
  `password` VARCHAR(255) NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ux_login_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
