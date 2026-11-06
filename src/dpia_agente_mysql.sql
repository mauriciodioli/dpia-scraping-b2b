-- DPIA | Agentes autonomos | MySQL 8.0+
-- Esquema nuevo: no modifica tablas existentes.
-- Antes de agregar una FK a usuarios, verificar tipo y nombre de PK real.
-- Todas las fechas se almacenan en UTC; programaciones usan zona IANA.
-- Ejecutar en la base DPIA correcta tras respaldo y revision.

CREATE TABLE IF NOT EXISTS agentes (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id BIGINT UNSIGNED NOT NULL COMMENT 'Referencia logica al usuario DPIA existente; validar tipo real',
  nombre VARCHAR(120) NOT NULL DEFAULT 'Mi agente',
  descripcion VARCHAR(500) NULL,
  estado ENUM('BORRADOR','INACTIVO','ACTIVO','PAUSADO','SIN_CREDITOS','ERROR') NOT NULL DEFAULT 'BORRADOR',
  idioma VARCHAR(10) NOT NULL DEFAULT 'es',
  pais_codigo CHAR(2) NULL,
  ciudad VARCHAR(150) NULL,
  zona_horaria VARCHAR(64) NOT NULL DEFAULT 'UTC',
  presupuesto_puntos_periodo DECIMAL(12,3) NOT NULL DEFAULT 0,
  periodo_presupuesto ENUM('DIA','SEMANA','MES') NOT NULL DEFAULT 'SEMANA',
  notificaciones_activas BOOLEAN NOT NULL DEFAULT TRUE,
  configuracion JSON NULL COMMENT 'Preferencias adicionales versionadas; no guardar secretos',
  version_config INT UNSIGNED NOT NULL DEFAULT 1,
  creado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  activado_en DATETIME(6) NULL,
  PRIMARY KEY (id),
  KEY idx_agentes_usuario (usuario_id),
  KEY idx_agentes_estado (estado),
  CONSTRAINT chk_agentes_presupuesto CHECK (presupuesto_puntos_periodo >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agente_tareas (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  agente_id BIGINT UNSIGNED NOT NULL,
  tipo ENUM('PRODUCTOS_NUEVOS','PRECIOS','PROVEEDORES','OPORTUNIDADES_LOCALES','EMPLEOS','TENDENCIAS') NOT NULL,
  nombre VARCHAR(150) NULL,
  habilitada BOOLEAN NOT NULL DEFAULT TRUE,
  parametros JSON NULL COMMENT 'Palabras clave, categorias, filtros, fuentes permitidas',
  ultima_ejecucion_en DATETIME(6) NULL,
  creado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY idx_tareas_agente_habilitada (agente_id, habilitada),
  CONSTRAINT fk_tareas_agente FOREIGN KEY (agente_id) REFERENCES agentes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agente_programaciones (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  agente_id BIGINT UNSIGNED NOT NULL,
  activa BOOLEAN NOT NULL DEFAULT FALSE,
  frecuencia ENUM('DIARIA','DOS_POR_SEMANA','SEMANAL') NOT NULL DEFAULT 'SEMANAL',
  dias_semana JSON NULL COMMENT 'ISO 1=lunes..7=domingo; validar desde aplicacion',
  hora_local TIME NOT NULL DEFAULT '09:00:00',
  zona_horaria VARCHAR(64) NOT NULL DEFAULT 'UTC',
  proxima_ejecucion_en DATETIME(6) NULL COMMENT 'UTC, calculada por planificador',
  ultima_ejecucion_en DATETIME(6) NULL,
  creado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_programacion_agente (agente_id),
  KEY idx_programaciones_pendientes (activa, proxima_ejecucion_en),
  CONSTRAINT fk_programaciones_agente FOREIGN KEY (agente_id) REFERENCES agentes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agente_ejecuciones (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  agente_id BIGINT UNSIGNED NOT NULL,
  programacion_id BIGINT UNSIGNED NULL,
  clave_idempotencia VARCHAR(128) NOT NULL,
  origen ENUM('PROGRAMADA','MANUAL','REINTENTO') NOT NULL DEFAULT 'PROGRAMADA',
  estado ENUM('PENDIENTE','EN_CURSO','COMPLETADA','PARCIAL','FALLIDA','CANCELADA') NOT NULL DEFAULT 'PENDIENTE',
  bloqueo_token CHAR(36) NULL,
  bloqueo_hasta DATETIME(6) NULL,
  config_version INT UNSIGNED NOT NULL,
  puntos_reservados DECIMAL(12,3) NOT NULL DEFAULT 0,
  puntos_consumidos DECIMAL(12,3) NOT NULL DEFAULT 0,
  resumen JSON NULL,
  codigo_error VARCHAR(80) NULL,
  detalle_error TEXT NULL,
  programada_para DATETIME(6) NULL,
  iniciada_en DATETIME(6) NULL,
  finalizada_en DATETIME(6) NULL,
  creada_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_ejecucion_idempotencia (agente_id, clave_idempotencia),
  KEY idx_ejecuciones_agente_fecha (agente_id, creada_en),
  KEY idx_ejecuciones_estado_bloqueo (estado, bloqueo_hasta),
  CONSTRAINT fk_ejecuciones_agente FOREIGN KEY (agente_id) REFERENCES agentes(id) ON DELETE RESTRICT,
  CONSTRAINT fk_ejecuciones_programacion FOREIGN KEY (programacion_id) REFERENCES agente_programaciones(id) ON DELETE SET NULL,
  CONSTRAINT chk_ejecuciones_puntos CHECK (puntos_reservados >= 0 AND puntos_consumidos >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agente_ejecucion_tareas (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ejecucion_id BIGINT UNSIGNED NOT NULL,
  tarea_id BIGINT UNSIGNED NULL,
  tipo_tarea VARCHAR(60) NOT NULL COMMENT 'Snapshot para conservar historial',
  estado ENUM('PENDIENTE','EN_CURSO','COMPLETADA','FALLIDA','OMITIDA') NOT NULL DEFAULT 'PENDIENTE',
  parametros_snapshot JSON NULL,
  resultados_total INT UNSIGNED NOT NULL DEFAULT 0,
  puntos_consumidos DECIMAL(12,3) NOT NULL DEFAULT 0,
  codigo_error VARCHAR(80) NULL,
  detalle_error TEXT NULL,
  iniciada_en DATETIME(6) NULL,
  finalizada_en DATETIME(6) NULL,
  PRIMARY KEY (id),
  KEY idx_ejecucion_tareas_ejecucion (ejecucion_id),
  KEY idx_ejecucion_tareas_tarea (tarea_id),
  CONSTRAINT fk_ejecucion_tareas_ejecucion FOREIGN KEY (ejecucion_id) REFERENCES agente_ejecuciones(id) ON DELETE CASCADE,
  CONSTRAINT fk_ejecucion_tareas_tarea FOREIGN KEY (tarea_id) REFERENCES agente_tareas(id) ON DELETE SET NULL,
  CONSTRAINT chk_ejecucion_tareas_puntos CHECK (puntos_consumidos >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agente_observaciones (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  agente_id BIGINT UNSIGNED NOT NULL,
  ejecucion_tarea_id BIGINT UNSIGNED NULL,
  tipo ENUM('PRODUCTO','PROVEEDOR','PUBLICACION_LOCAL','EMPLEO','TENDENCIA') NOT NULL,
  fuente VARCHAR(80) NOT NULL COMMENT 'amazon, mercadolibre, dpia_local, etc.',
  referencia_externa VARCHAR(255) NULL,
  clave_entidad CHAR(64) NOT NULL COMMENT 'SHA-256 de identidad canonica estable por fuente',
  titulo VARCHAR(500) NOT NULL,
  url TEXT NULL,
  precio DECIMAL(16,4) NULL,
  moneda CHAR(3) NULL,
  vendedor VARCHAR(255) NULL,
  ubicacion VARCHAR(255) NULL,
  datos JSON NULL COMMENT 'Payload normalizado y metadatos; evitar PII innecesaria',
  observado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY idx_observaciones_historial (agente_id, clave_entidad, observado_en),
  KEY idx_observaciones_tarea (ejecucion_tarea_id),
  KEY idx_observaciones_tipo_fecha (tipo, observado_en),
  CONSTRAINT fk_observaciones_agente FOREIGN KEY (agente_id) REFERENCES agentes(id) ON DELETE RESTRICT,
  CONSTRAINT fk_observaciones_ejecucion_tarea FOREIGN KEY (ejecucion_tarea_id) REFERENCES agente_ejecucion_tareas(id) ON DELETE SET NULL,
  CONSTRAINT chk_observaciones_precio CHECK (precio IS NULL OR precio >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agente_cambios (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  agente_id BIGINT UNSIGNED NOT NULL,
  observacion_anterior_id BIGINT UNSIGNED NULL,
  observacion_actual_id BIGINT UNSIGNED NOT NULL,
  tipo ENUM('NUEVO','PRECIO_BAJO','PRECIO_SUBIO','DATOS_CAMBIARON','NO_DISPONIBLE','REAPARECIO') NOT NULL,
  relevancia ENUM('BAJA','MEDIA','ALTA') NOT NULL DEFAULT 'MEDIA',
  detalle JSON NULL COMMENT 'Valores anteriores/actuales y razones',
  detectado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_cambio_actual_tipo (agente_id, observacion_actual_id, tipo),
  KEY idx_cambios_agente_fecha (agente_id, detectado_en),
  CONSTRAINT fk_cambios_agente FOREIGN KEY (agente_id) REFERENCES agentes(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cambios_anterior FOREIGN KEY (observacion_anterior_id) REFERENCES agente_observaciones(id) ON DELETE SET NULL,
  CONSTRAINT fk_cambios_actual FOREIGN KEY (observacion_actual_id) REFERENCES agente_observaciones(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agente_notificaciones (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  agente_id BIGINT UNSIGNED NOT NULL,
  ejecucion_id BIGINT UNSIGNED NULL,
  cambio_id BIGINT UNSIGNED NULL,
  tipo ENUM('RESUMEN','NOVEDAD','ALERTA','ERROR','CREDITOS') NOT NULL,
  canal ENUM('APP','EMAIL','PUSH') NOT NULL DEFAULT 'APP',
  estado ENUM('PENDIENTE','ENVIANDO','ENVIADA','FALLIDA','CANCELADA') NOT NULL DEFAULT 'PENDIENTE',
  clave_idempotencia VARCHAR(128) NOT NULL,
  titulo VARCHAR(255) NOT NULL,
  mensaje TEXT NULL,
  datos JSON NULL,
  intentos INT UNSIGNED NOT NULL DEFAULT 0,
  proximo_intento_en DATETIME(6) NULL,
  enviada_en DATETIME(6) NULL,
  leida_en DATETIME(6) NULL,
  creada_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_notificacion_idempotencia (agente_id, canal, clave_idempotencia),
  KEY idx_notificaciones_pendientes (estado, proximo_intento_en),
  KEY idx_notificaciones_agente (agente_id, creada_en),
  CONSTRAINT fk_notificaciones_agente FOREIGN KEY (agente_id) REFERENCES agentes(id) ON DELETE RESTRICT,
  CONSTRAINT fk_notificaciones_ejecucion FOREIGN KEY (ejecucion_id) REFERENCES agente_ejecuciones(id) ON DELETE SET NULL,
  CONSTRAINT fk_notificaciones_cambio FOREIGN KEY (cambio_id) REFERENCES agente_cambios(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- IMPORTANTE:
-- 1. Validar tipo de usuarios.id antes de crear FK externa.
-- 2. Reutilizar ledger/transacciones de puntos existente: no debitar directamente desde estas tablas.
-- 3. Reservar y confirmar cargos de modo atomico/idempotente en servicio de puntos.
-- 4. El planificador debe reclamar trabajos con bloqueo transaccional y lease, no solo SELECT.
-- 5. Comparar precios solo con moneda/unidad/variante equivalentes.
-- 6. Ausencia en una busqueda NO prueba falta de disponibilidad: exigir reglas de verificacion.
-- 7. Definir politicas de retencion y borrado antes de produccion.
