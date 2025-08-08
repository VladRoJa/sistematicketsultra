USE `railway`;
-- MySQL dump 10.13  Distrib 8.0.41, for Win64 (x86_64)
--
-- Host: localhost    Database: sistema_tickets
-- ------------------------------------------------------
-- Server version	8.0.41

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `aparatos_gimnasio`
--

DROP TABLE IF EXISTS `aparatos_gimnasio`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `aparatos_gimnasio` (
  `id` int NOT NULL AUTO_INCREMENT,
  `codigo` varchar(50) NOT NULL,
  `sucursal_id` int NOT NULL,
  `descripcion` varchar(255) DEFAULT NULL,
  `marca` varchar(100) DEFAULT NULL,
  `grupo_muscular` varchar(100) DEFAULT NULL,
  `categoria` varchar(100) DEFAULT NULL,
  `numero_equipo` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_aparato_sucursal` (`sucursal_id`),
  CONSTRAINT `fk_aparato_sucursal` FOREIGN KEY (`sucursal_id`) REFERENCES `sucursales` (`sucursal_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=137 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `aparatos_gimnasio`
--

LOCK TABLES `aparatos_gimnasio` WRITE;
/*!40000 ALTER TABLE `aparatos_gimnasio` DISABLE KEYS */;
INSERT INTO `aparatos_gimnasio` VALUES (1,'01CABRSTSG01',1,'Bicicleta Recumbente','Star Trac','Sin grupo muscular','Cardio','01'),(2,'01CACALFSG01',1,'Caminadora','Life Fitnes','Sin grupo muscular','Cardio','01'),(3,'01CAELPRSG01',1,'Eliptica','Precor','Sin grupo muscular','Cardio','01'),(4,'01CAESMTSG01',1,'Escalera','Matrix','Sin grupo muscular','Cardio','01'),(5,'01CABRSTSG02',1,'Bicicleta Recumbente','Star Trac','Sin grupo muscular','Cardio','02'),(6,'01CACALFSG02',1,'Caminadora','Life Fitnes','Sin grupo muscular','Cardio','02'),(7,'01CAELPRSG02',1,'Eliptica','Precor','Sin grupo muscular','Cardio','02'),(8,'01CABVSTSG03',1,'Bicicleta Vertical','Star Trac','Sin grupo muscular','Cardio','03'),(9,'01CACALFSG03',1,'Caminadora','Life Fitnes','Sin grupo muscular','Cardio','03'),(10,'01CAELPRSG03',1,'Eliptica','Precor','Sin grupo muscular','Cardio','03'),(11,'01CACVSTSG04',1,'Bicicleta Vertical','Star Trac','Sin grupo muscular','Cardio','04'),(12,'01CACALFSG04',1,'Caminadora','Life Fitnes','Sin grupo muscular','Cardio','04'),(13,'01CAECLFSG04',1,'Eliptica Cross','Life Fitnes','Sin grupo muscular','Cardio','04'),(14,'01CACALFSG05',1,'Caminadora','Life Fitnes','Sin grupo muscular','Cardio','05'),(15,'01CAECLFSG05',1,'Eliptica Cross','Life Fitnes','Sin grupo muscular','Cardio','05'),(16,'01CACALFSG06',1,'Caminadora','Life Fitnes','Sin grupo muscular','Cardio','06'),(17,'01CAECLFSG06',1,'Eliptica Cross','Life Fitnes','Sin grupo muscular','Cardio','06'),(18,'01CACALFSG07',1,'Caminadora','Life Fitnes','Sin grupo muscular','Cardio','07'),(19,'01CAECLFSG07',1,'Eliptica Cross','Life Fitnes','Sin grupo muscular','Cardio','07'),(20,'01CACASTSG08',1,'Caminadora','Star Trac','Sin grupo muscular','Cardio','08'),(21,'01CAECLFSG08',1,'Eliptica Cross','Life Fitnes','Sin grupo muscular','Cardio','08'),(22,'01CACASTSG09',1,'Caminadora','Star Trac','Sin grupo muscular','Cardio','09'),(23,'01CAECLFSG09',1,'Eliptica Cross','Life Fitnes','Sin grupo muscular','Cardio','09'),(24,'01CACASTSG10',1,'Caminadora','Star Trac','Sin grupo muscular','Cardio','10'),(25,'01CAECLFSG10',1,'Eliptica Cross','Life Fitnes','Sin grupo muscular','Cardio','10'),(26,'01CACASTSG11',1,'Caminadora','Star Trac','Sin grupo muscular','Cardio','11'),(27,'01CAATCBSG11',1,'Arc Trainer','Cybex','Sin grupo muscular','Cardio','11'),(28,'01CABSKESG01',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','01'),(29,'01CABSKESG02',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','02'),(30,'01CABSKESG03',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','03'),(31,'01CABSKESG04',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','04'),(32,'01CABSKESG05',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','05'),(33,'01CABSKESG06',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','06'),(34,'01CABSKESG07',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','07'),(35,'01CABSKESG08',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','08'),(36,'01CABSKESG09',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','09'),(37,'01CABSKESG10',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','10'),(38,'01CABSKESG11',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','11'),(39,'01CABSKESG12',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','12'),(40,'01CABSKESG13',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','13'),(41,'01CABSKESG14',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','14'),(42,'01CABSKESG15',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','15'),(43,'01CABSKESG16',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','16'),(44,'01CABSKESG17',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','17'),(45,'01CABSKESG18',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','18'),(46,'01CABSKESG19',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','19'),(47,'01CABSKESG20',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','20'),(48,'01CABSKESG21',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','21'),(49,'01CABSKESG23',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','23'),(50,'01CABSKESG24',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','24'),(51,'01CABSKESG25',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','25'),(52,'01CABSKESG26',1,'Bicicleta P/Spinning','Keiser','Sin grupo muscular','Cardio','26'),(53,'01PLJRFLPI40',1,'Jaula Rack Para Sentadilla','Flex','Pierna','Peso Libre','40'),(54,'01PLRTCBES01',1,'Remo T','Cybex','Espalda','Peso Libre','01'),(55,'01PLBIFLPE02',1,'Banca Olimpica Inclinada','Flex','Pecho','Peso Libre','02'),(56,'01PLBIFLPE03',1,'Banca Olimpica Inclinada','Flex','Pecho','Peso Libre','03'),(57,'01PLBDFLPE04',1,'Banca Olimpica Declinada','Flex','Pecho','Peso Libre','04'),(58,'01PLBOFLPE05',1,'Banca Olimpica','Flex','Pecho','Peso Libre','05'),(59,'01PLHEICES05',1,'Hyperextension Espalda','Icarian','Espalda','Peso Libre','05'),(60,'01PLBOFLPE06',1,'Banca Olimpica','Flex','Pecho','Peso Libre','06'),(61,'01PLCOICPE07',1,'Banca Olimpica','Icarian','Pecho','Peso Libre','07'),(62,'01PLPMFLPE08',1,'Press Militar','Flex','Pecho','Peso Libre','08'),(63,'01PLPRICBR09',1,'Predicador','Icarian','Brazo','Peso Libre','09'),(64,'01PLSMICPI10',1,'Smith Machine','Icarian','Pierna','Peso Libre','10'),(65,'01PLSMFLPI11',1,'Smith Machine','Flex','Pierna','Peso Libre','11'),(66,'01PLPPHSPI12',1,'Prensa Pierna','Hammer Strength','Pierna','Peso Libre','12'),(67,'01PLPPHSPI13',1,'Prensa Pierna','Hammer Strength','Pierna','Peso Libre','13'),(68,'01PLHSSTPI14',1,'Prensa Pierna Hack Squat','Star Trac','Pierna','Peso Libre','14'),(69,'01PLPPHSPI15',1,'Prensa P/Pierna Parado','Hammer Strength','Pierna','Peso Libre','15'),(70,'01PLJPICPI16',1,'Jaula P/Pierna Sentadilla','Icarian','Pierna','Peso Libre','16'),(71,'01PLHTULPI17',1,'Hip Thrust','Ultra','Pierna','Peso Libre','17'),(72,'01PLVKSMAB18',1,'Vkr','SIN MARCA','Abdomen','Peso Libre','18'),(73,'01PLVKSMAB19',1,'Vkr','SIN MARCA','Abdomen','Peso Libre','19'),(74,'01PLBACBAB20',1,'Banca Abdominal','Cybex','Abdomen','Peso Libre','20'),(75,'01PLBACBAB21',1,'Banca Abdominal','Cybex','Abdomen','Peso Libre','21'),(76,'01PLRBHSSG22',1,'Rack Barra Integrada','Hammer Strength','Sin grupo muscular','Peso Libre','22'),(77,'01PLBZHSSG23',1,'Rack Barra Integrada Z','Hammer Strength','Sin grupo muscular','Peso Libre','23'),(78,'01PLBMCBSG24',1,'Banca Multiposicion','Cybex','Sin grupo muscular','Peso Libre','24'),(79,'01PLBMCBSG25',1,'Banca Multiposicion','Cybex','Sin grupo muscular','Peso Libre','25'),(80,'01PLBMCBSG26',1,'Banca Multiposicion','Cybex','Sin grupo muscular','Peso Libre','26'),(81,'01PLRDULSG27',1,'Rack Docle P/Mancuernas','Ultra','Sin grupo muscular','Peso Libre','27'),(82,'01PLRDULSG28',1,'Rack Docle P/Mancuernas','Ultra','Sin grupo muscular','Peso Libre','28'),(83,'01PLRDULSG29',1,'Rack Docle P/Mancuernas','Ultra','Sin grupo muscular','Peso Libre','29'),(84,'01PLRDULSG30',1,'Rack Docle P/Mancuernas','Ultra','Sin grupo muscular','Peso Libre','30'),(85,'01PLRDULSG31',1,'Rack Doble P/Mancuernas','Ultra','Sin grupo muscular','Peso Libre','31'),(86,'01PLBPFLSG32',1,'Banca Plana','Flex','Sin grupo muscular','Peso Libre','32'),(87,'01PLBPPASG33',1,'Banca Plana','Paramount','Sin grupo muscular','Peso Libre','33'),(88,'01PLADFLSG34',1,'Arbol P/Discos','Flex','Sin grupo muscular','Peso Libre','34'),(89,'01PLADFLSG35',1,'Arbol P/Discos','Flex','Sin grupo muscular','Peso Libre','35'),(90,'01PLSUCBSG36',1,'Silla Utilitaria','Cybex','Sin grupo muscular','Peso Libre','36'),(91,'01PLSUCBSG37',1,'Silla Utilitaria','Cybex','Sin grupo muscular','Peso Libre','37'),(92,'01CABSKESG38',1,'Bicicleta P/Spinning','keiser','Sin grupo muscular','Cardio','38'),(93,'01PLBAFLSG39',1,'Banca Abdominal ','Flex','Sin grupo muscular','Peso Libre','39'),(94,'01PLVLEXPI45',1,'Vertical Leg Press','Excel','Pierna','Peso Libre','45'),(95,'01PLSSEXPI47',1,'SISSY SQUAT','Excel','Pierna','Peso Libre','47'),(96,'01SEMPFMMU01',1,'Multiestacion Polea Doble','Free Motion','Multiarticular','Selectorizado','01'),(97,'01SEMULFMU02',1,'Multiestacion 8','Life Fitnes','Multiarticular','Selectorizado','02'),(98,'01SEPPLFPE03',1,'Prensa De Pecho','Life Fitnes','Pecho','Selectorizado','03'),(99,'01SEPMLFPE04',1,'Pecho Mariposa','Life Fitnes','Pecho','Selectorizado','04'),(100,'01SEPMLFPE05',1,'Pecho Mariposa','Life Fitnes','Pecho','Selectorizado','05'),(101,'01SEPPLFPE06',1,'Prensa Pecho','Life Fitnes','Pecho','Selectorizado','06'),(102,'01SEEELFES07',1,'Extension Espalda Baja','Life Fitnes','Espalda','Selectorizado','07'),(103,'01SERELFES08',1,'Remo Para Espalda','Life Fitnes','Espalda','Selectorizado','08'),(104,'01SEPDLFES09',1,'Pull Down ','Life Fitnes','Espalda','Selectorizado','09'),(105,'01SEPTLFBR10',1,'Press Triceps','Life Fitnes','Brazo','Selectorizado','10'),(106,'01SEPTICBR11',1,'Predicador Para Biceps','Icarian','Brazo','Selectorizado','11'),(107,'01SEBCLFBR12',1,'Bicep Curl','Life Fitnes','Brazo','Selectorizado','12'),(108,'01SEHLLFBR13',1,'Hombro Lateral','Life Fitnes','Brazo','Selectorizado','13'),(109,'01SEFALFBR14',1,'Fondo Asistido','Life Fitnes','Brazo','Selectorizado','14'),(110,'01SEPHLFBR15',1,'Prensa Hombro','Life Fitnes','Brazo','Selectorizado','15'),(111,'01SETELFBR16',1,'Triceps Extension','Life Fitnes','Brazo','Selectorizado','16'),(112,'01SEPPLFPI17',1,'Prensa P/Pierna','Life Fitnes','Pierna','Selectorizado','17'),(113,'01SEEPLFPI18',1,'Extension P/Pierna','Life Fitnes','Pierna','Selectorizado','18'),(114,'01SEGCLFPI19',1,'Gluteo Cable Motion','Life Fitnes','Pierna','Selectorizado','19'),(115,'01SEFSLFPI20',1,'Femoral Sentado','Life Fitnes','Pierna','Selectorizado','20'),(116,'01SEFALFPI21',1,'Femoral Acostado','Life Fitnes','Pierna','Selectorizado','21'),(117,'01SEPALFPI22',1,'Pantorrilla 45 Grados','Life Fitnes','Pierna','Selectorizado','22'),(118,'01SEGLLTPI23',1,'Gluteo','Leg Tech','Pierna','Selectorizado','23'),(119,'01SEABLFPI24',1,'Abductor','Life Fitnes','Pierna','Selectorizado','24'),(120,'01SEABLFPI25',1,'Adductor','Life Fitnes','Pierna','Selectorizado','25'),(121,'01SEPPLFPI26',1,'Pantorrilla Parado','Life Fitnes','Pierna','Selectorizado','26'),(122,'01SEABICAB27',1,'Abdominal','Icarian','Abdomen','Selectorizado','27'),(123,'01SEABLFAB28',1,'Abdominal','Life Fitnes','Abdomen','Selectorizado','28'),(124,'01SEABLFAB29',1,'Abdominal','Life Fitnes','Abdomen','Selectorizado','29'),(125,'01SEPFSTPE30',1,'Pec Fly','Star Trac','Pecho','Selectorizado','30'),(126,'01SEGLLFPI31',1,'Gluteo','Life Fitnes','Pierna','Selectorizado','31'),(127,'01SEGIEXPI41',1,'Glute Isolator ','Excel','Pierna','Selectorizado','41'),(128,'01SEDAEXMU42',1,'DUAL ADJUSTABLE PULLEY ','Excel','Multiarticular','Selectorizado','42'),(129,'01SELCEXPI43',1,'LEG CURL EXTENSION','Excel','Pierna','Selectorizado','43'),(130,'01SELCEXPI44',1,'LEG CURL EXTENSION','Excel','Pierna','Selectorizado','44'),(131,'01SEHTEXPI46',1,'HIP THRUST ','Excel','Pierna','Selectorizado','46'),(132,'01PLDRJWSG48',1,'2 tier dumbell rack','JW SPORT','Sin grupo muscular','Peso Libre','48'),(133,'01PLDRJWSG49',1,'2 tier dumbell rack','JW SPORT','Sin grupo muscular','Peso Libre','49'),(134,'01PLPTJWSG50',1,'Plate Tree','JW SPORT','Sin grupo muscular','Peso Libre','50'),(135,'01PLPTJWSG51',1,'Plate Tree','JW SPORT','Sin grupo muscular','Peso Libre','51'),(136,'01PLHDJWPI52',1,'Hex Bar/\nDEADLIFT ','JW SPORT','Pierna','Peso Libre','52');
/*!40000 ALTER TABLE `aparatos_gimnasio` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `departamentos`
--

DROP TABLE IF EXISTS `departamentos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `departamentos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nombre` varchar(100) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1001 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `departamentos`
--

LOCK TABLES `departamentos` WRITE;
/*!40000 ALTER TABLE `departamentos` DISABLE KEYS */;
INSERT INTO `departamentos` VALUES (1,'Mantenimiento'),(2,'Finanzas'),(3,'Marketing'),(4,'Gerencia Deportiva'),(5,'Recursos Humanos'),(6,'Compras'),(7,'Sistemas'),(1000,'Administrador');
/*!40000 ALTER TABLE `departamentos` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `detalle_movimiento`
--

DROP TABLE IF EXISTS `detalle_movimiento`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `detalle_movimiento` (
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
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `detalle_movimiento`
--

LOCK TABLES `detalle_movimiento` WRITE;
/*!40000 ALTER TABLE `detalle_movimiento` DISABLE KEYS */;
INSERT INTO `detalle_movimiento` VALUES (1,1,15,15,'Piezas'),(2,2,17,10,'Galon'),(4,4,16,45,'galon'),(6,6,16,10,'galon'),(7,7,17,11,'Galon'),(13,13,15,30,'Piezas'),(14,14,15,10,'Piezas'),(15,15,17,11,'Galon'),(16,16,18,100,'Galon'),(17,17,18,50,'Galon'),(18,18,16,100,'galon'),(19,19,16,45,'galon'),(20,20,15,15,'Piezas'),(21,21,15,15,'Piezas');
/*!40000 ALTER TABLE `detalle_movimiento` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `historial_eliminaciones_movimientos`
--

DROP TABLE IF EXISTS `historial_eliminaciones_movimientos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `historial_eliminaciones_movimientos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `movimiento_id` int NOT NULL,
  `usuario_id` int NOT NULL,
  `fecha_hora` datetime DEFAULT CURRENT_TIMESTAMP,
  `descripcion` text,
  PRIMARY KEY (`id`),
  KEY `movimiento_id` (`movimiento_id`),
  KEY `usuario_id` (`usuario_id`),
  CONSTRAINT `historial_eliminaciones_movimientos_ibfk_1` FOREIGN KEY (`movimiento_id`) REFERENCES `movimientos_inventario` (`id`) ON DELETE CASCADE,
  CONSTRAINT `historial_eliminaciones_movimientos_ibfk_2` FOREIGN KEY (`usuario_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `historial_eliminaciones_movimientos`
--

LOCK TABLES `historial_eliminaciones_movimientos` WRITE;
/*!40000 ALTER TABLE `historial_eliminaciones_movimientos` DISABLE KEYS */;
/*!40000 ALTER TABLE `historial_eliminaciones_movimientos` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `inventario`
--

DROP TABLE IF EXISTS `inventario`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `inventario` (
  `id` int NOT NULL AUTO_INCREMENT,
  `producto_id` int DEFAULT NULL,
  `sucursal_id` int DEFAULT NULL,
  `cantidad` int DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `producto_id` (`producto_id`),
  KEY `inventario_ibfk_2` (`sucursal_id`),
  CONSTRAINT `inventario_ibfk_1` FOREIGN KEY (`producto_id`) REFERENCES `productos` (`id`),
  CONSTRAINT `inventario_ibfk_2` FOREIGN KEY (`sucursal_id`) REFERENCES `sucursales` (`sucursal_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `inventario`
--

LOCK TABLES `inventario` WRITE;
/*!40000 ALTER TABLE `inventario` DISABLE KEYS */;
/*!40000 ALTER TABLE `inventario` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `inventario_sucursal`
--

DROP TABLE IF EXISTS `inventario_sucursal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `inventario_sucursal` (
  `id` int NOT NULL AUTO_INCREMENT,
  `producto_id` int DEFAULT NULL,
  `sucursal_id` int DEFAULT NULL,
  `stock` int DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `producto_id` (`producto_id`),
  KEY `sucursal_id` (`sucursal_id`),
  CONSTRAINT `inventario_sucursal_ibfk_1` FOREIGN KEY (`producto_id`) REFERENCES `productos` (`id`),
  CONSTRAINT `inventario_sucursal_ibfk_2` FOREIGN KEY (`sucursal_id`) REFERENCES `sucursales` (`sucursal_id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `inventario_sucursal`
--

LOCK TABLES `inventario_sucursal` WRITE;
/*!40000 ALTER TABLE `inventario_sucursal` DISABLE KEYS */;
INSERT INTO `inventario_sucursal` VALUES (1,15,1,15),(2,17,1000,10),(3,16,1000,90),(4,15,1000,20),(5,18,1000,50);
/*!40000 ALTER TABLE `inventario_sucursal` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `movimientos`
--

DROP TABLE IF EXISTS `movimientos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movimientos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `producto_id` int DEFAULT NULL,
  `sucursal_id` int DEFAULT NULL,
  `tipo_movimiento` enum('entrada','salida') DEFAULT NULL,
  `cantidad` int DEFAULT NULL,
  `motivo` text,
  `fecha` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `producto_id` (`producto_id`),
  KEY `movimientos_ibfk_2` (`sucursal_id`),
  CONSTRAINT `movimientos_ibfk_1` FOREIGN KEY (`producto_id`) REFERENCES `productos` (`id`),
  CONSTRAINT `movimientos_ibfk_2` FOREIGN KEY (`sucursal_id`) REFERENCES `sucursales` (`sucursal_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `movimientos`
--

LOCK TABLES `movimientos` WRITE;
/*!40000 ALTER TABLE `movimientos` DISABLE KEYS */;
/*!40000 ALTER TABLE `movimientos` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `movimientos_inventario`
--

DROP TABLE IF EXISTS `movimientos_inventario`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `movimientos_inventario` (
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
  CONSTRAINT `movimientos_inventario_ibfk_2` FOREIGN KEY (`sucursal_id`) REFERENCES `sucursales` (`sucursal_id`)
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `movimientos_inventario`
--

LOCK TABLES `movimientos_inventario` WRITE;
/*!40000 ALTER TABLE `movimientos_inventario` DISABLE KEYS */;
INSERT INTO `movimientos_inventario` VALUES (1,'entrada','2025-04-21 11:14:34',1,1,''),(2,'entrada','2025-04-21 12:58:31',49,1000,''),(4,'entrada','2025-04-22 18:00:57',49,1000,''),(6,'salida','2025-04-22 18:09:08',49,1000,''),(7,'entrada','2025-04-22 18:09:58',49,1000,''),(13,'entrada','2025-04-22 19:48:39',49,1000,''),(14,'salida','2025-04-22 19:48:54',49,1000,''),(15,'salida','2025-04-22 19:51:27',49,1000,''),(16,'entrada','2025-04-23 09:46:52',49,1000,'factura 100002'),(17,'salida','2025-04-23 09:47:14',49,1000,''),(18,'entrada','2025-04-24 10:30:15',49,1000,'factura 100002'),(19,'salida','2025-04-24 10:31:01',49,1000,''),(20,'entrada','2025-04-25 07:11:38',49,1000,''),(21,'salida','2025-04-25 07:11:49',49,1000,''),(24,'salida','2025-04-25 07:29:42',49,1000,'');
/*!40000 ALTER TABLE `movimientos_inventario` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `productos`
--

DROP TABLE IF EXISTS `productos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `productos` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nombre` varchar(255) NOT NULL,
  `descripcion` text,
  `unidad_medida` varchar(50) DEFAULT NULL,
  `categoria` varchar(100) DEFAULT NULL,
  `subcategoria` varchar(100) DEFAULT NULL,
  `stock_total` int DEFAULT '0',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=23 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `productos`
--

LOCK TABLES `productos` WRITE;
/*!40000 ALTER TABLE `productos` DISABLE KEYS */;
INSERT INTO `productos` VALUES (15,'Agua 1 L',NULL,'Piezas','Bebidas',NULL,0),(16,'Windex',NULL,'galon','Limpieza',NULL,0),(17,'Cloro','Cloro','Galon','Limpieza','',0),(18,'Fabuloso',NULL,'Galon','Limpieza',NULL,0),(21,'Escoba','','Pieza','Limpieza','',0);
/*!40000 ALTER TABLE `productos` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sucursales`
--

DROP TABLE IF EXISTS `sucursales`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sucursales` (
  `id` int NOT NULL,
  `sucursal_id` int NOT NULL,
  `serie` varchar(10) NOT NULL,
  `sucursal` varchar(100) NOT NULL,
  `estado` varchar(100) NOT NULL,
  `municipio` varchar(100) NOT NULL,
  `direccion` varchar(255) NOT NULL,
  PRIMARY KEY (`sucursal_id`),
  UNIQUE KEY `id_sucursal` (`sucursal_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sucursales`
--

LOCK TABLES `sucursales` WRITE;
/*!40000 ALTER TABLE `sucursales` DISABLE KEYS */;
INSERT INTO `sucursales` VALUES (1,1,'VREY','Villas del rey','Baja California','Mexicali','CALZADA XOCHIMILCO #200'),(2,2,'VVER','Villa verde mexicali','Baja California','Mexicali','BLV. LÁZARO CÁRDENAS COL. DIEZ DIVISIÓN DOS'),(3,3,'INDE','Independencia','Baja California','Mexicali','CALZADA INDEPENDENCIA S/N'),(4,4,'TECN','Tec mexicali','Baja California','Mexicali','BLVD LAZARO CARDENAS #2338 LOTE 7'),(5,5,'SMXL','Sendero mexicali','Baja California','Mexicali','1600 AV, BLVRD LÁZARO CÁRDENAS'),(6,6,'SLUI','San luis','Sonora','San Luis Río Colorado','CALLEJON GUADALUPE VICTORIA #1709'),(7,7,'PABE','Pabellon rosarito','Baja California','Playas de Rosarito','CARRETERA A TIJUANA ENSENADA NO 300'),(8,8,'MISI','Mision ensenada','Baja California','Ensenada','REFORMA Y C ONCE NO 1122'),(9,9,'PASS','Paseo 2000','Baja California','Tijuana','CORREDOR TIJUANA ROSARITO 2000 26135 LOCAL PAD-D'),(10,10,'GIMP','Gimnasio prueba','Sonora','Hermosillo','AV SIEMPRE VIVA #57'),(11,11,'LBON','Loma bonita','Baja California','Tijuana','BLVD AGUA AZUL NUM 7200'),(12,12,'SAFE','Santa fe','Baja California','Tijuana','BLVD EL ROSARIO NUM 10450'),(13,13,'CARR','Carrousel tijuana','Baja California','Tijuana','CIPRÉS 4, LAS BRISAS, 22115 TIJUANA, B.C.'),(14,14,'PAPA','Papalote tijuana','Baja California','Tijuana','INSURGENTES NO 16902'),(15,15,'SCLN','Sendero culiacan','Sinaloa','Culiacán','CUG SENDERO CULIACAN'),(16,16,'SISI','San isidro culiacan','Sinaloa','Culiacán','CUG SAN ISIDRO'),(17,17,'AZAH','Azahares culiacan','Sinaloa','Culiacán','CUG AZAHARES CULIACAN'),(18,18,'SCAT','Santa catarina','Nuevo León','Santa Catarina','CARR MONTERREY SALTILLO 2601'),(19,19,'SSAL','Sendero saltillo','Coahuila de Zaragoza','Saltillo','BLVD. ANTONIO CÁRDENAS 4159, PARQUES DE LA CAÑADA, 25080 SALTILLO, COAH.'),(20,20,'SCHI','Sendero chihuahua','Chihuahua','Chihuahua','ALEJANDRO DUMAS #11337'),(21,21,'LPAZ','Paseo la paz','Baja California Sur','La Paz','LIB DANIEL ROLDAN'),(22,22,'IXTA','Ixtapaluca','México','Ixtapaluca','CARR FEDERAL MEXICO-CUAUTLA 1'),(23,100,'CORP','Corporativo','Baja California','Mexicali','CUAUHTEMOC NORTE 401'),(24,1000,'ADMN','Administrador','Baja California','Mexicali','Corporativo');
/*!40000 ALTER TABLE `sucursales` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tickets`
--

DROP TABLE IF EXISTS `tickets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tickets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `descripcion` text NOT NULL,
  `username` varchar(50) NOT NULL,
  `asignado_a` varchar(50) DEFAULT NULL,
  `sucursal_id` int NOT NULL,
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
  KEY `username` (`username`),
  KEY `asignado_a` (`asignado_a`),
  KEY `fk_departamento` (`departamento_id`),
  KEY `tickets_ibfk_1` (`sucursal_id`),
  CONSTRAINT `fk_departamento` FOREIGN KEY (`departamento_id`) REFERENCES `departamentos` (`id`),
  CONSTRAINT `tickets_ibfk_1` FOREIGN KEY (`sucursal_id`) REFERENCES `sucursales` (`sucursal_id`) ON DELETE CASCADE,
  CONSTRAINT `tickets_ibfk_2` FOREIGN KEY (`username`) REFERENCES `users` (`username`) ON DELETE CASCADE,
  CONSTRAINT `tickets_ibfk_3` FOREIGN KEY (`asignado_a`) REFERENCES `users` (`username`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=97 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tickets`
--

LOCK TABLES `tickets` WRITE;
/*!40000 ALTER TABLE `tickets` DISABLE KEYS */;
INSERT INTO `tickets` VALUES (40,'prueba','ADMICORP',NULL,1000,'abierto','2025-03-06 09:20:02',NULL,1,3,'Tapicería','[]',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(41,'PRUEBA','ADMICORP',NULL,1000,'abierto','2025-03-06 09:38:36',NULL,1,3,'Peso libre','[]',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(42,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-06 09:39:13','2025-03-13 12:01:21',1,3,'Cardio','[]',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(43,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-06 09:39:31','2025-04-30 11:43:11',1,2,'Cardio','null',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(44,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-06 09:41:12','2025-03-06 14:01:16',1,3,'Selectorizado','[]',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(45,'vacante para gerencia','RECEVREY',NULL,1,'finalizado','2025-03-06 13:23:10','2025-03-06 13:33:50',5,2,'Vacantes','[]',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(46,'Test 1','GEREVREY',NULL,1,'finalizado','2025-03-06 13:49:14',NULL,1,3,'Fachada','[{\"fecha\": \"2025-03-01\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-12 13:33:14\"}]',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(47,'test 2','GEREVREY',NULL,1,'finalizado','2025-03-06 13:49:39','2025-04-30 10:37:48',1,2,'Peso libre','null',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(48,'prueba','ADMICORP',NULL,1000,'en progreso','2025-03-07 08:56:14',NULL,1,3,'Cardio','[{\"fecha\": \"2025-03-01\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-12 11:59:47\"}]',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(49,'locker de tal medida','ADMICORP',NULL,1000,'finalizado','2025-03-07 09:10:30','2025-03-12 10:35:40',1,5,'Lockers','[{\"fecha\": \"2025-03-12 10:35:40\", \"cambiadoPor\": \"49\", \"fechaCambio\": \"2025-03-12 10:35:40\"}, {\"fecha\": \"2025-03-01\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-12 11:59:35\"}]',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(50,'lorena montaño','ADMICORP',NULL,1000,'finalizado','2025-03-07 09:12:36','2025-03-07 11:36:22',4,2,'App Ultra','[{\"fecha\": \"2025-03-01\", \"cambiadoPor\": \"49\", \"fechaCambio\": \"2025-03-12 11:29:44\"}, {\"fecha\": \"2025-03-06\", \"cambiadoPor\": \"49\", \"fechaCambio\": \"2025-03-12 11:30:51\"}]',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(51,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-07 10:42:33','2025-03-07 11:27:07',1,3,'Cardio','[{\"fecha\": \"2025-03-01\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-12 14:13:11\"}]',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(52,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-07 11:00:40','2025-03-13 16:08:37',1,4,'Selectorizado','[{\"fecha\": \"2025-03-01\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-12 14:02:03\"}, {\"fecha\": \"2025-03-02\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-13 16:08:37\"}]','2025-03-02 00:00:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(53,'un cable de electricidad esta expuesto','ADMICORP',NULL,1000,'finalizado','2025-03-08 10:27:18','2025-03-13 15:59:37',1,5,'Instalación eléctrica','[{\"fecha\": \"2025-03-01\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-12 13:22:14\"}, {\"fecha\": \"2025-03-02\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-13 15:59:37\"}]','2025-03-02 00:00:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(54,'PRUEBA','ADMICORP',NULL,1000,'finalizado','2025-03-10 11:02:42','2025-03-13 15:27:36',1,3,'Cardio','[{\"fecha\": \"2025-03-11 14:05:09\", \"cambiadoPor\": \"49\", \"fechaCambio\": \"2025-03-11 14:05:09\"}, {\"fecha\": \"2025-03-11 14:05:20\", \"cambiadoPor\": \"49\", \"fechaCambio\": \"2025-03-11 14:05:20\"}, {\"fecha\": \"2025-03-05\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-12 13:06:16\"}, {\"fecha\": \"2025-03-01\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-13 15:27:36\"}]','2025-03-01 00:00:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(55,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-12 14:24:05','2025-03-13 15:27:22',1,5,'Extintores','[{\"fecha\": \"2025-03-01\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-13 15:27:22\"}]','2025-03-01 00:00:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(56,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-13 12:08:15','2025-03-13 16:44:32',3,2,'Landing page','[{\"fecha\": \"2025-03-15\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-13 13:39:32\"}, {\"fecha\": \"2025-03-06\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-13 15:27:09\"}]','2025-03-06 00:00:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(57,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-13 16:44:55','2025-03-14 12:56:27',1,3,'Iluminación',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(58,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-13 16:56:59','2025-03-13 16:57:31',7,3,'Equipo de gerencia',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(59,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-14 08:27:03','2025-03-14 08:48:17',3,4,'Material promocional',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(60,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-14 08:53:10','2025-03-14 12:53:22',6,4,'Bebidas para la venta',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(61,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-14 11:00:50','2025-03-14 11:01:06',2,5,'Facturación',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(62,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-14 11:16:38','2025-03-14 11:47:57',5,3,'Incidencia en nómina','[{\"fecha\": \"2025-03-01\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-14 11:22:50\"}, {\"fecha\": \"2025-03-02\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-14 11:38:03\"}, {\"fecha\": \"2025-03-03 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-14 11:46:32\"}, {\"fecha\": \"2025-03-04 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-14 11:47:40\"}, {\"fecha\": \"2025-03-05 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-14 11:47:49\"}, {\"fecha\": \"2025-03-01 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-14 11:47:57\"}]','2025-03-01 00:01:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(63,'DESC tickets;','ADMICORP',NULL,1000,'finalizado','2025-03-14 12:45:22','2025-03-14 12:46:21',1,1,'Bodega',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(64,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-14 13:10:33','2025-03-14 13:32:52',1,1,'Recepción','[{\"fecha\": \"2025-03-01 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-14 13:32:34\"}, {\"fecha\": \"2025-03-02 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-14 13:32:46\"}, {\"fecha\": \"2025-03-03 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-14 13:32:52\"}]','2025-03-03 00:01:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(65,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-14 13:36:05','2025-03-14 13:36:30',7,1,'Equipo de gerencia','[{\"fecha\": \"2025-03-01 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-14 13:36:30\"}]','2025-03-01 00:01:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(66,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-16 14:18:17','2025-03-20 10:53:09',2,3,'Facturación','[{\"fecha\": \"2025-03-01 01:00:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-20 10:36:51\"}]','2025-03-01 01:00:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(67,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-16 14:21:33','2025-03-16 14:22:22',1,2,'Cancelería','[{\"fecha\": \"2025-03-01 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-16 14:22:10\"}, {\"fecha\": \"2025-03-03 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-16 14:22:22\"}]','2025-03-03 00:01:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(68,'prueba','RECEVREY',NULL,1,'finalizado','2025-03-16 14:22:59','2025-03-20 08:57:39',4,4,'App Ultra',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(69,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-18 10:36:25','2025-03-18 10:37:04',1,3,'Inmueble','[{\"fecha\": \"2025-03-01 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-18 10:36:45\"}, {\"fecha\": \"2025-03-07 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-18 10:36:53\"}, {\"fecha\": \"2025-03-10 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-18 10:37:00\"}]','2025-03-10 00:01:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(70,'prueba','RECEVREY',NULL,1,'finalizado','2025-03-19 08:46:18','2025-03-20 09:35:19',2,4,'Devolución por cobro erróneo en terminal','[{\"fecha\": \"2025-03-01 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-20 09:35:08\"}, {\"fecha\": \"2025-03-08 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-20 09:35:15\"}]','2025-03-08 00:01:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(72,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-20 08:27:04','2025-03-20 09:00:26',1,2,'Bodega','[{\"fecha\": \"2025-03-01 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-20 09:00:17\"}, {\"fecha\": \"2025-03-03 00:01:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-20 09:00:26\"}]','2025-03-03 00:01:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(73,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-20 12:34:51','2025-04-30 15:23:36',4,1,'Accesorios para equipos','null','2025-03-12 01:00:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(74,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-20 12:42:21','2025-04-30 15:35:49',5,3,'Vacantes',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(75,'prueba','RECEVREY',NULL,1,'finalizado','2025-03-20 12:45:27','2025-04-30 14:25:56',6,4,'Bebidas para la venta','null','2025-03-10 01:00:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(76,'prueba desde mantenimiento','MANTCORP',NULL,100,'finalizado','2025-03-21 19:53:34','2025-03-27 11:05:16',4,4,'App Ultra','[{\"fecha\": \"2025-03-01 01:00:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-23 13:56:16\"}, {\"fecha\": \"2025-03-03 01:00:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-23 14:04:49\"}, {\"fecha\": \"2025-03-12 01:00:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-03-24 09:44:27\"}]','2025-03-12 01:00:00',NULL,NULL,NULL,NULL,NULL,NULL,NULL),(77,'prueba','ADMICORP',NULL,1000,'finalizado','2025-03-24 09:41:19','2025-04-03 08:57:25',7,3,'Equipo de gerencia',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL),(78,'Las paredes se ven verdes por la humedad','ADMICORP',NULL,1000,'finalizado','2025-04-04 11:15:05','2025-04-30 15:33:48',1,2,'Inmueble',NULL,NULL,NULL,'paredes','Humedad',NULL,NULL,NULL,NULL),(79,'el extractor del baño de mujeres hace mucho ruido ','ADMICORP',NULL,1000,'finalizado','2025-04-04 11:45:53','2025-04-30 15:26:46',1,1,'AC y ventilación',NULL,NULL,NULL,'Extractores','Hace ruido',NULL,NULL,NULL,NULL),(80,'en sucursal hay un interruptor dañado y debe ser remplazado','ADMICORP',NULL,1000,'finalizado','2025-04-06 17:15:24','2025-04-06 21:08:00',1,4,'Instalación Eléctrica','[{\"fecha\": \"2025-04-10 01:00:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-04-06 21:07:09\"}, {\"fecha\": \"2025-04-14 01:00:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-04-06 21:07:27\"}]','2025-04-14 01:00:00',NULL,'Centro de carga','Interruptores dañados',NULL,NULL,NULL,NULL),(81,'las llaves del baño de hombres estan goteando, se necesita refaccion llave01845','ADMICORP',NULL,1000,'finalizado','2025-04-06 21:09:45','2025-04-30 15:14:14',1,3,'Sanitarios',NULL,NULL,NULL,'llaves','Goteo',NULL,NULL,NULL,NULL),(82,'La maquina se siente floja','ADMICORP',NULL,1000,'finalizado','2025-04-07 10:51:49','2025-04-30 15:10:06',1,3,'Aparatos',NULL,NULL,NULL,NULL,NULL,95,'La maquina se siente floja',1,'Hay que reemplazar la tornilleria'),(83,'En el baño de mujeres una de las tazas presenta fuga','RECEVREY',NULL,1,'finalizado','2025-04-07 11:03:25','2025-04-30 14:54:33',1,4,'Sanitarios',NULL,NULL,NULL,'Muebles Sanitarios','Fuga de agua',NULL,NULL,0,NULL),(84,'La maquina se atora','RECEVREY',NULL,1,'finalizado','2025-04-07 11:04:09','2025-04-30 14:52:20',1,2,'Aparatos',NULL,NULL,NULL,NULL,NULL,3,'La maquina se atora',1,'se le deben cambiar los baleros'),(85,'Pared sucia ','ADMICORP',NULL,1000,'finalizado','2025-04-24 07:11:19','2025-04-30 14:49:39',1,1,'Inmueble',NULL,NULL,NULL,'pintura','Requiere retoque',NULL,NULL,0,NULL),(86,'se le rompio un pedal','ADMICORP',NULL,1000,'finalizado','2025-04-24 07:25:08','2025-04-30 14:47:01',1,2,'Aparatos',NULL,NULL,NULL,NULL,NULL,32,'se le rompio un pedal',1,'pedal 152487'),(87,'hay que cambiar la carga del quimico de los extintores','ADMICORP',NULL,1000,'finalizado','2025-04-28 11:44:42','2025-04-30 14:39:39',1,3,'Inmueble',NULL,NULL,NULL,'extintores','Recarga',NULL,NULL,0,NULL),(88,'la maquina no funciona','ADMICORP',NULL,1000,'finalizado','2025-04-30 08:36:18','2025-04-30 16:36:25',1,3,'Aparatos','null','2025-05-01 01:00:00',NULL,NULL,NULL,4,'la maquina no funciona',0,NULL),(89,'hay que colocarlos bien','ADMICORP',NULL,1000,'finalizado','2025-04-30 09:42:56','2025-04-30 16:54:42',1,2,'Inmueble',NULL,NULL,NULL,'extintores','Mal colocación',NULL,NULL,0,NULL),(90,'la maquina no funciona','ADMICORP',NULL,1000,'finalizado','2025-04-30 10:05:36','2025-04-30 17:05:57',1,3,'Aparatos',NULL,NULL,NULL,NULL,NULL,72,'la maquina no funciona',0,NULL),(91,'no tiene presion suficiente','ADMICORP',NULL,1000,'finalizado','2025-04-30 10:09:52','2025-04-30 10:23:08',1,1,'Sanitarios',NULL,NULL,NULL,'Servicios','Baja presión',NULL,NULL,0,NULL),(92,'foco parpadea','ADMICORP',NULL,1000,'finalizado','2025-04-30 10:13:09','2025-04-30 17:21:06',1,1,'Iluminación',NULL,NULL,NULL,'Iluminación interna','Parpadea',NULL,NULL,0,NULL),(93,'no hay agua','ADMICORP',NULL,1000,'finalizado','2025-04-30 10:29:43','2025-04-30 17:29:59',1,3,'Sanitarios',NULL,NULL,NULL,'Servicios','Sin agua',NULL,NULL,0,NULL),(94,'dejaron de enfriar','ADMICORP',NULL,1000,'finalizado','2025-04-30 11:18:09','2025-04-30 11:18:26',1,2,'AC y ventilación',NULL,NULL,NULL,'equipos','Sin enfriar',NULL,NULL,0,NULL),(95,'se requiere trabajo de albañileria','ADMICORP',NULL,1000,'finalizado','2025-04-30 11:31:21','2025-05-02 09:02:40',1,1,'Inmueble','[{\"fecha\": \"2025-05-03 01:00:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-05-02T16:02:39.680Z\"}]','2025-05-03 08:00:00',NULL,'Albañileria','Reparación menor',NULL,NULL,0,NULL),(96,'Tenemos variacion de voltajes','ADMICORP',NULL,1000,'finalizado','2025-04-30 11:47:22','2025-05-02 09:01:31',1,3,'Instalación Eléctrica','[{\"fecha\": \"2025-05-02 01:00:00\", \"cambiadoPor\": \"ADMICORP\", \"fechaCambio\": \"2025-05-02T16:01:30.919Z\"}]','2025-05-02 08:00:00',NULL,'Servicios','Voltaje inestable',NULL,NULL,0,NULL);
/*!40000 ALTER TABLE `tickets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tickets_mantenimiento_aparatos`
--

DROP TABLE IF EXISTS `tickets_mantenimiento_aparatos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tickets_mantenimiento_aparatos` (
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tickets_mantenimiento_aparatos`
--

LOCK TABLES `tickets_mantenimiento_aparatos` WRITE;
/*!40000 ALTER TABLE `tickets_mantenimiento_aparatos` DISABLE KEYS */;
/*!40000 ALTER TABLE `tickets_mantenimiento_aparatos` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tickets_mantenimiento_edificio`
--

DROP TABLE IF EXISTS `tickets_mantenimiento_edificio`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tickets_mantenimiento_edificio` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticket_id` int NOT NULL,
  `ubicacion` varchar(255) NOT NULL,
  `descripcion_detallada` text,
  `foto_url` varchar(500) DEFAULT NULL,
  `fecha_registro` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_ticket_edificio` (`ticket_id`),
  CONSTRAINT `fk_ticket_edificio` FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tickets_mantenimiento_edificio`
--

LOCK TABLES `tickets_mantenimiento_edificio` WRITE;
/*!40000 ALTER TABLE `tickets_mantenimiento_edificio` DISABLE KEYS */;
/*!40000 ALTER TABLE `tickets_mantenimiento_edificio` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `sucursal_id` int NOT NULL,
  `sucursal` varchar(100) NOT NULL,
  `username` varchar(50) NOT NULL,
  `password` varchar(255) NOT NULL,
  `rol` varchar(50) NOT NULL,
  `department_id` varchar(45) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `users_ibfk_1` (`sucursal_id`),
  CONSTRAINT `users_ibfk_1` FOREIGN KEY (`sucursal_id`) REFERENCES `sucursales` (`sucursal_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=54 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,1,'VILLAS DEL REY','RECEVREY','123','RECEPCIONISTA',''),(2,1,'VILLAS DEL REY','GEREVREY','123','GERENTE',''),(3,2,'VILLA VERDE MEXICALI','RECEVVER','123','RECEPCIONISTA',''),(4,2,'VILLA VERDE MEXICALI','GEREVVER','123','GERENTE',''),(5,3,'INDEPENDENCIA','RECEINDE','123','RECEPCIONISTA',''),(6,3,'INDEPENDENCIA','GEREINDE','123','GERENTE',''),(7,4,'TEC MEXICALI','RECETECN','123','RECEPCIONISTA',''),(8,4,'TEC MEXICALI','GERETECN','123','GERENTE',''),(9,5,'SENDERO MEXICALI','RECESMXL','123','RECEPCIONISTA',''),(10,5,'SENDERO MEXICALI','GERESMXL','123','GERENTE',''),(11,6,'SAN LUIS','RECESLUI','123','RECEPCIONISTA',''),(12,6,'SAN LUIS','GERESLUI','123','GERENTE',''),(13,7,'PABELLON ROSARITO','RECEPABE','123','RECEPCIONISTA',''),(14,7,'PABELLON ROSARITO','GEREPABE','123','GERENTE',''),(15,8,'MISION ENSENADA','RECEMISI','123','RECEPCIONISTA',''),(16,8,'MISION ENSENADA','GEREMISI','123','GERENTE',''),(17,9,'PASEO 2000','RECEPASS','123','RECEPCIONISTA',''),(18,9,'PASEO 2000','GEREPASS','123','GERENTE',''),(21,10,'LOMA BONITA','RECELBON','123','RECEPCIONISTA',''),(22,10,'LOMA BONITA','GERELBON','123','GERENTE',''),(23,11,'SANTA FE','RECESAFE','123','RECEPCIONISTA',''),(24,11,'SANTA FE','GERESAFE','123','GERENTE',''),(25,12,'CARROUSEL TIJUANA','RECECARR','123','RECEPCIONISTA',''),(26,12,'CARROUSEL TIJUANA','GERECARR','123','GERENTE',''),(27,13,'PAPALOTE TIJUANA','RECEPAPA','123','RECEPCIONISTA',''),(28,13,'PAPALOTE TIJUANA','GEREPAPA','123','GERENTE',''),(29,14,'SENDERO CULIACAN','RECESCLN','123','RECEPCIONISTA',''),(30,14,'SENDERO CULIACAN','GERESCLN','123','GERENTE',''),(31,15,'SAN ISIDRO CULIACAN','RECESISI','123','RECEPCIONISTA',''),(32,15,'SAN ISIDRO CULIACAN','GERESISI','123','GERENTE',''),(33,16,'AZAHARES CULIACAN','RECEAZAH','123','RECEPCIONISTA',''),(34,16,'AZAHARES CULIACAN','GEREAZAH','123','GERENTE',''),(35,17,'SANTA CATARINA','RECESCAT','123','RECEPCIONISTA',''),(36,17,'SANTA CATARINA','GERESCAT','123','GERENTE',''),(37,18,'SENDERO SALTILLO','RECESSAL','123','RECEPCIONISTA',''),(38,18,'SENDERO SALTILLO','GERESSAL','123','GERENTE',''),(39,19,'SENDERO CHIHUAHUA','RECESCHI','123','RECEPCIONISTA',''),(40,19,'SENDERO CHIHUAHUA','GERESCHI','123','GERENTE',''),(41,20,'PASEO LA PAZ','RECELPAZ','123','RECEPCIONISTA',''),(42,20,'PASEO LA PAZ','GERELPAZ','123','GERENTE',''),(43,21,'IXTAPALUCA','RECEIXTA','123','RECEPCIONISTA',''),(44,21,'IXTAPALUCA','GEREIXTA','123','GERENTE',''),(45,100,'CORPORATIVO','RHCORP','123','RECURSOS HUMANOS','5'),(46,100,'CORPORATIVO','FINACORP','123','FINANZAS','2'),(47,100,'CORPORATIVO','MANTCORP','123','MANTENIMIENTO','1'),(48,100,'CORPORATIVO','SISTCORP','123','SISTEMAS','7'),(49,1000,'CORPORATIVO','ADMICORP','123','ADMINISTRADOR',''),(50,1000,'CORPORATIVO','TECNCORP','123','TECNICO',''),(51,100,'CORPORATIVO','MARKCORP','123','MARKETING','3'),(52,100,'CORPORATIVO','GERDCORP','123','GERENCIA DEPORTIVA','4'),(53,100,'CORPORATIVO','COMPCORP','123','COMPRAS','6');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `usuarios_permisos`
--

DROP TABLE IF EXISTS `usuarios_permisos`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `usuarios_permisos` (
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
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `usuarios_permisos`
--

LOCK TABLES `usuarios_permisos` WRITE;
/*!40000 ALTER TABLE `usuarios_permisos` DISABLE KEYS */;
INSERT INTO `usuarios_permisos` VALUES (1,3,1,0),(2,3,2,0),(3,5,4,1);
/*!40000 ALTER TABLE `usuarios_permisos` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-05-06  9:14:49
