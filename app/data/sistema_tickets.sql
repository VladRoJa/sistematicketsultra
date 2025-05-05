-- Tabla de usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100),
    correo VARCHAR(100) UNIQUE,
    contrasena VARCHAR(255),
    sucursal_id INT,
    departamento_id INT,
    es_admin BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (sucursal_id) REFERENCES sucursales(id),
    FOREIGN KEY (departamento_id) REFERENCES departamentos(id)
);

-- Tabla de sucursales
CREATE TABLE IF NOT EXISTS sucursales (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL
);

-- Tabla de departamentos
CREATE TABLE IF NOT EXISTS departamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL
);

-- Tabla de tickets
CREATE TABLE IF NOT EXISTS tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(255),
    descripcion TEXT,
    estado VARCHAR(50) DEFAULT 'Pendiente',
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    fecha_solucion DATETIME,
    usuario_id INT,
    sucursal_id INT,
    departamento_id INT,
    tipo_mantenimiento VARCHAR(50),
    categoria VARCHAR(100),
    subcategoria VARCHAR(100),
    subsubcategoria VARCHAR(100),
    criticidad VARCHAR(50),
    aparato_id INT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    FOREIGN KEY (sucursal_id) REFERENCES sucursales(id),
    FOREIGN KEY (departamento_id) REFERENCES departamentos(id),
    FOREIGN KEY (aparato_id) REFERENCES aparatos_gimnasio(id)
);

-- Tabla de aparatos de gimnasio
CREATE TABLE IF NOT EXISTS aparatos_gimnasio (
    id INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(50) UNIQUE,
    nombre VARCHAR(100),
    marca VARCHAR(100)
);

-- Subformulario: tickets mantenimiento de edificio
CREATE TABLE IF NOT EXISTS tickets_mantenimiento_edificio (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id INT,
    categoria VARCHAR(100),
    subcategoria VARCHAR(100),
    subsubcategoria VARCHAR(100),
    FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
);

-- Subformulario: tickets mantenimiento de aparatos
CREATE TABLE IF NOT EXISTS tickets_mantenimiento_aparatos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id INT,
    aparato_id INT,
    problema_detectado TEXT,
    requiere_refaccion BOOLEAN DEFAULT FALSE,
    descripcion_refaccion TEXT,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
    FOREIGN KEY (aparato_id) REFERENCES aparatos_gimnasio(id)
);

-- Tabla de productos (Inventario)
CREATE TABLE IF NOT EXISTS productos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100),
    descripcion TEXT,
    categoria VARCHAR(100),
    unidad_medida VARCHAR(50)
);

-- Tabla de inventario por sucursal
CREATE TABLE IF NOT EXISTS inventario (
    id INT AUTO_INCREMENT PRIMARY KEY,
    producto_id INT,
    sucursal_id INT,
    cantidad INT DEFAULT 0,
    FOREIGN KEY (producto_id) REFERENCES productos(id),
    FOREIGN KEY (sucursal_id) REFERENCES sucursales(id)
);

-- Tabla de movimientos (entradas y salidas)
CREATE TABLE IF NOT EXISTS movimientos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    producto_id INT,
    sucursal_id INT,
    tipo_movimiento ENUM('entrada', 'salida'),
    cantidad INT,
    motivo TEXT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (producto_id) REFERENCES productos(id),
    FOREIGN KEY (sucursal_id) REFERENCES sucursales(id)
);

-- Insertar sucursales únicas
INSERT INTO sucursales (id, nombre) VALUES
(1, 'VILLAS DEL REY'),
(2, 'VILLA VERDE MEXICALI'),
(3, 'INDEPENDENCIA'),
(4, 'TEC MEXICALI'),
(5, 'SENDERO MEXICALI'),
(6, 'SAN LUIS'),
(7, 'PABELLON ROSARITO'),
(8, 'MISION ENSENADA'),
(9, 'PASEO 2000'),
(10, 'LOMA BONITA'),
(11, 'SANTA FE'),
(12, 'CARROUSEL TIJUANA'),
(13, 'PAPALOTE TIJUANA'),
(14, 'SENDERO CULIACAN'),
(15, 'SAN ISIDRO CULIACAN'),
(16, 'AZAHARES CULIACAN'),
(17, 'SANTA CATARINA'),
(18, 'SENDERO SALTILLO'),
(19, 'SENDERO CHIHUAHUA'),
(20, 'PASEO LA PAZ'),
(21, 'IXTAPALUCA'),
(100, 'CORPORATIVO'),
(1000, 'CORPORATIVO');

-- Insertar departamentos base (IDs según mapeo real)
INSERT INTO departamentos (id, nombre) VALUES
(1, 'MANTENIMIENTO'),
(2, 'FINANZAS'),
(3, 'MARKETING'),
(4, 'GERENCIA DEPORTIVA'),
(5, 'RECURSOS HUMANOS'),
(6, 'COMPRAS'),
(7, 'SISTEMAS');    
(1000, 'SISTEMAS');


-- Insertar usuarios
INSERT INTO usuarios (id, sucursal_id, nombre, correo, contrasena, departamento_id, es_admin) VALUES
(1, 1, 'RECEVREY', 'recevrey', '123', NULL, FALSE),
(2, 1, 'GEREVREY', 'gerevrey', '123', NULL, FALSE),
(3, 2, 'RECEVVER', 'recevver', '123', NULL, FALSE),
(4, 2, 'GEREVVER', 'gerevver', '123', NULL, FALSE),
(5, 3, 'RECEINDE', 'receinde', '123', NULL, FALSE),
(6, 3, 'GEREINDE', 'gereinde', '123', NULL, FALSE),
(7, 4, 'RECETECN', 'recetecn', '123', NULL, FALSE),
(8, 4, 'GERETECN', 'geretecn', '123', NULL, FALSE),
(9, 5, 'RECESMXL', 'recesmxl', '123', NULL, FALSE),
(10, 5, 'GERESMXL', 'geresmxl', '123', NULL, FALSE),
(11, 6, 'RECESLUI', 'receslui', '123', NULL, FALSE),
(12, 6, 'GERESLUI', 'gereslui', '123', NULL, FALSE),
(13, 7, 'RECEPABE', 'recepabe', '123', NULL, FALSE),
(14, 7, 'GEREPABE', 'gerepabe', '123', NULL, FALSE),
(15, 8, 'RECEMISI', 'recemisi', '123', NULL, FALSE),
(16, 8, 'GEREMISI', 'geremisi', '123', NULL, FALSE),
(17, 9, 'RECEPASS', 'recepass', '123', NULL, FALSE),
(18, 9, 'GEREPASS', 'gerepass', '123', NULL, FALSE),
(19, 11, 'RECELBON', 'recelbon', '123', NULL, FALSE),
(20, 11, 'GERELBON', 'gerelbon', '123', NULL, FALSE),
(21, 12, 'RECESAFE', 'recesafe', '123', NULL, FALSE),
(22, 12, 'GERESAFE', 'geresafe', '123', NULL, FALSE),
(23, 13, 'RECECARR', 'rececarr', '123', NULL, FALSE),
(24, 13, 'GERECARR', 'gerecarr', '123', NULL, FALSE),
(25, 14, 'RECEPAPA', 'recepapa', '123', NULL, FALSE),
(26, 14, 'GEREPAPA', 'gerepapa', '123', NULL, FALSE),
(27, 15, 'RECESCLN', 'recescln', '123', NULL, FALSE),
(28, 15, 'GERESCLN', 'gerescln', '123', NULL, FALSE),
(29, 16, 'RECESISI', 'recesisi', '123', NULL, FALSE),
(30, 16, 'GERESISI', 'geresisi', '123', NULL, FALSE),
(31, 17, 'RECEAZAH', 'receazah', '123', NULL, FALSE),
(32, 17, 'GEREAZAH', 'gereazah', '123', NULL, FALSE),
(33, 18, 'RECESCAT', 'recescat', '123', NULL, FALSE),
(34, 18, 'GERESCAT', 'gerescat', '123', NULL, FALSE),
(35, 19, 'RECESSAL', 'recessal', '123', NULL, FALSE),
(36, 19, 'GERESSAL', 'geressal', '123', NULL, FALSE),
(37, 20, 'RECESCHI', 'receschi', '123', NULL, FALSE),
(38, 20, 'GERESCHI', 'gereschi', '123', NULL, FALSE),
(39, 21, 'RECELPAZ', 'recelpaz', '123', NULL, FALSE),
(40, 21, 'GERELPAZ', 'gerelpaz', '123', NULL, FALSE),
(41, 22, 'RECEIXTA', 'receixta', '123', NULL, FALSE),
(42, 22, 'GEREIXTA', 'gereixta', '123', NULL, FALSE),
(43, 100, 'RHCORP', 'rhcorp', '123', 5, FALSE),
(44, 100, 'FINACORP', 'finacorp', '123', 2, FALSE),
(45, 100, 'MANTCORP', 'mantcorp', '123', 1, FALSE),
(46, 100, 'SISTCORP', 'sistcorp', '123', 7, FALSE),
(47, 1000, 'ADMICORP', 'admicorp', '123', 1000, TRUE),
(48, 1000, 'TECNCORP', 'tecncorp', '123', 1000, TRUE),
(49, 100, 'MARKCORP', 'markcorp', '123', 3, FALSE),
(50, 100, 'GERDCORP', 'gerdcorp', '123', 4, FALSE),
(51, 100, 'COMPCORP', 'compcorp', '123', 6, FALSE);
