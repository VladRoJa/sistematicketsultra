
from app.models.database import get_db_connection

def inicializar_base_de_datos():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `detalle_movimiento` (
  `id` int NOT NULL AUTO_INCREMENT,
  `movimiento_id` int DEFAULT NULL,
  `producto_id` int DEFAULT NULL,
  `cantidad` int NOT NULL,
  `unidad_medida` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `movimiento_id` (`movimiento_id`),
  KEY `producto_id` (`producto_id`),
  CONSTRAINT `detalle_movimiento_ibfk_1` FOREIGN KEY (`movimiento_id`) REFERENCES `movimientos_inventario` (`id`),
  CONSTRAINT `detalle_movimiento_ibfk_2` FOREIGN KEY (`producto_id`) REFERENCES `productos` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `inventario_sucursal` (
  `id` int NOT NULL AUTO_INCREMENT,
  `producto_id` int DEFAULT NULL,
  `sucursal_id` int DEFAULT NULL,
  `stock` int DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `producto_id` (`producto_id`),
  KEY `sucursal_id` (`sucursal_id`),
  CONSTRAINT `inventario_sucursal_ibfk_1` FOREIGN KEY (`producto_id`) REFERENCES `productos` (`id`),
  CONSTRAINT `inventario_sucursal_ibfk_2` FOREIGN KEY (`sucursal_id`) REFERENCES `sucursales` (`id_sucursal`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `movimientos_inventario` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tipo_movimiento` enum('entrada','salida') NOT NULL,
  `fecha` datetime DEFAULT CURRENT_TIMESTAMP,
  `usuario_id` int DEFAULT NULL,
  `sucursal_id` int DEFAULT NULL,
  `observaciones` text,
  PRIMARY KEY (`id`),
  KEY `usuario_id` (`usuario_id`),
  KEY `sucursal_id` (`sucursal_id`),
  CONSTRAINT `movimientos_inventario_ibfk_1` FOREIGN KEY (`usuario_id`) REFERENCES `users` (`id`),
  CONSTRAINT `movimientos_inventario_ibfk_2` FOREIGN KEY (`sucursal_id`) REFERENCES `sucursales` (`id_sucursal`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `productos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nombre` varchar(255) NOT NULL,
  `descripcion` text,
  `unidad_medida` varchar(50) DEFAULT NULL,
  `categoria` varchar(100) DEFAULT NULL,
  `subcategoria` varchar(100) DEFAULT NULL,
  `stock_total` int DEFAULT '0',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `sucursales` (
  `id` int NOT NULL,
  `id_sucursal` int NOT NULL,
  `serie` varchar(10) NOT NULL,
  `sucursal` varchar(100) NOT NULL,
  `estado` varchar(100) NOT NULL,
  `municipio` varchar(100) NOT NULL,
  `direccion` varchar(255) NOT NULL,
  PRIMARY KEY (`id_sucursal`),
  UNIQUE KEY `id_sucursal` (`id_sucursal`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `tickets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `descripcion` text NOT NULL,
  `username` varchar(50) NOT NULL,
  `asignado_a` varchar(50) DEFAULT NULL,
  `id_sucursal` int NOT NULL,
  `estado` enum('abierto','en progreso','finalizado') NOT NULL DEFAULT 'abierto',
  `fecha_creacion` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `fecha_finalizado` datetime DEFAULT NULL,
  `departamento_id` int DEFAULT NULL,
  `criticidad` int NOT NULL DEFAULT '1',
  `categoria` varchar(255) NOT NULL,
  `historial_fechas` json DEFAULT NULL,
  `fecha_solucion` datetime DEFAULT NULL,
  `department_id` int DEFAULT NULL,
  `subcategoria` varchar(100) DEFAULT NULL,
  `subsubcategoria` varchar(100) DEFAULT NULL,
  `aparato_id` int DEFAULT NULL,
  `problema_detectado` text,
  `necesita_refaccion` tinyint(1) DEFAULT NULL,
  `descripcion_refaccion` text,
  PRIMARY KEY (`id`),
  KEY `id_sucursal` (`id_sucursal`),
  KEY `username` (`username`),
  KEY `asignado_a` (`asignado_a`),
  KEY `fk_departamento` (`departamento_id`),
  CONSTRAINT `fk_departamento` FOREIGN KEY (`departamento_id`) REFERENCES `departamentos` (`id`),
  CONSTRAINT `tickets_ibfk_1` FOREIGN KEY (`id_sucursal`) REFERENCES `sucursales` (`id_sucursal`) ON DELETE CASCADE,
  CONSTRAINT `tickets_ibfk_2` FOREIGN KEY (`username`) REFERENCES `users` (`username`) ON DELETE CASCADE,
  CONSTRAINT `tickets_ibfk_3` FOREIGN KEY (`asignado_a`) REFERENCES `users` (`username`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=85 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `tickets_mantenimiento_aparatos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticket_id` int NOT NULL,
  `tipo_aparato` varchar(100) NOT NULL,
  `marca_modelo` varchar(100) DEFAULT NULL,
  `numero_inventario` varchar(50) DEFAULT NULL,
  `problema_detectado` text,
  `necesita_refaccion` tinyint(1) DEFAULT '0',
  `foto_url` varchar(500) DEFAULT NULL,
  `fecha_registro` datetime DEFAULT CURRENT_TIMESTAMP,
  `aparato_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_ticket_aparato` (`ticket_id`),
  KEY `fk_aparato_gimnasio` (`aparato_id`),
  CONSTRAINT `fk_aparato_gimnasio` FOREIGN KEY (`aparato_id`) REFERENCES `aparatos_gimnasio` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_ticket_aparato` FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `tickets_mantenimiento_edificio` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticket_id` int NOT NULL,
  `ubicacion` varchar(255) NOT NULL,
  `tipo_problema` varchar(100) NOT NULL,
  `descripcion_detallada` text,
  `foto_url` varchar(500) DEFAULT NULL,
  `fecha_registro` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_ticket_edificio` (`ticket_id`),
  CONSTRAINT `fk_ticket_edificio` FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `id_sucursal` int NOT NULL,
  `sucursal` varchar(100) NOT NULL,
  `username` varchar(50) NOT NULL,
  `password` varchar(255) NOT NULL,
  `rol` varchar(50) NOT NULL,
  `department_id` varchar(45) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `id_sucursal` (`id_sucursal`),
  CONSTRAINT `users_ibfk_1` FOREIGN KEY (`id_sucursal`) REFERENCES `sucursales` (`id_sucursal`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=54 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `usuarios_permisos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `departamento_id` int NOT NULL,
  `es_admin` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  KEY `departamento_id` (`departamento_id`),
  CONSTRAINT `usuarios_permisos_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `usuarios_permisos_ibfk_2` FOREIGN KEY (`departamento_id`) REFERENCES `departamentos` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `aparatos_gimnasio` (
  `id` int NOT NULL AUTO_INCREMENT,
  `codigo` varchar(50) NOT NULL,
  `id_sucursal` int NOT NULL,
  `descripcion` varchar(255) DEFAULT NULL,
  `marca` varchar(100) DEFAULT NULL,
  `grupo_muscular` varchar(100) DEFAULT NULL,
  `categoria` varchar(100) DEFAULT NULL,
  `numero_equipo` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_aparato_sucursal` (`id_sucursal`),
  CONSTRAINT `fk_aparato_sucursal` FOREIGN KEY (`id_sucursal`) REFERENCES `sucursales` (`id_sucursal`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=137 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")

    cursor.execute("""
CREATE TABLE IF NOT EXISTS `departamentos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nombre` varchar(100) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
""")


    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Todas las tablas han sido creadas correctamente (si no existían).")

if __name__ == "__main__":
    inicializar_base_de_datos()
