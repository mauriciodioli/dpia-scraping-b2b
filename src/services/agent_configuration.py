"""Validated, inactive agent configuration. No scheduler, credits or provider execution."""
from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import (MetaData, Table, Column, Integer, String, Boolean, DateTime,
                        JSON, Time, select, insert, update, UniqueConstraint)
from flask import current_app
from werkzeug.datastructures import MultiDict
from model.usuario import Usuario
from model.codigoPostal import CodigoPostal
from services.locations import postal_ids_for_city
from services.dpia_client import DPIAClient, catalog_filters
from services.query_preparation import PreparationError, COUNTRIES
from utils.db import db

# Independent metadata: importing these tables never creates them through db.create_all().
metadata = MetaData()
agentes = Table('agentes', metadata,
    Column('id', Integer, primary_key=True), Column('usuario_id', Integer, nullable=False),
    Column('nombre', String(120)), Column('estado', String(20)), Column('idioma', String(10)),
    Column('pais_codigo', String(2)), Column('ciudad', String(150)), Column('zona_horaria', String(64)),
    Column('presupuesto_puntos_periodo', Integer), Column('periodo_presupuesto', String(10)),
    Column('notificaciones_activas', Boolean), Column('configuracion', JSON),
    Column('version_config', Integer), Column('creado_en', DateTime), Column('actualizado_en', DateTime),
    Column('activado_en', DateTime), UniqueConstraint('usuario_id'))
tareas = Table('agente_tareas', metadata,
    Column('id', Integer, primary_key=True), Column('agente_id', Integer, nullable=False),
    Column('tipo', String(30)), Column('nombre', String(150)), Column('habilitada', Boolean),
    Column('parametros', JSON), Column('ultima_ejecucion_en', DateTime),
    Column('creado_en', DateTime), Column('actualizado_en', DateTime),
    Column('ae_agent_id', String(36)))
programaciones = Table('agente_programaciones', metadata,
    Column('id', Integer, primary_key=True), Column('agente_id', Integer, nullable=False),
    Column('activa', Boolean), Column('frecuencia', String(20)), Column('dias_semana', JSON),
    Column('hora_local', Time), Column('zona_horaria', String(64)),
    Column('proxima_ejecucion_en', DateTime), Column('ultima_ejecucion_en', DateTime),
    Column('creado_en', DateTime), Column('actualizado_en', DateTime), UniqueConstraint('agente_id'))
TASKS = {'products':'PRODUCTOS_NUEVOS', 'prices':'PRECIOS', 'suppliers':'PROVEEDORES',
         'local':'OPORTUNIDADES_LOCALES', 'jobs':'EMPLEOS', 'trends':'TENDENCIAS'}
FREQUENCIES = {'daily':'DIARIA', 'twice':'DOS_POR_SEMANA', 'weekly':'SEMANAL'}
PERIODS = {'week':'SEMANA', 'month':'MES'}
FIELDS = {'version','tasks','country','city','scopes','categories','frequency','days','time',
          'timezone','points','period','notifications','language'}


def bad(message='Revisá la configuración del agente.', status=400):
    raise PreparationError(message, status)


def positive_ids(value):
    return (isinstance(value,list) and 1 <= len(value) <= 500
            and all(type(v) is int and 1 <= v <= 2147483647 for v in value)
            and len(set(value)) == len(value))


def validate_config(data):
    """Validate before network calls or opening the write transaction. Client labels are not trusted."""
    if not isinstance(data,dict) or set(data) not in (FIELDS, FIELDS | {'query_context'}) or type(data['version']) is not int or data['version'] != 1:
        bad()
    if not isinstance(data['tasks'],list) or not 1<=len(data['tasks'])<=len(TASKS) or any(not isinstance(t,str) or t not in TASKS for t in data['tasks']) or len(set(data['tasks']))!=len(data['tasks']):
        bad('Seleccioná al menos una tarea.')
    if not isinstance(data['country'],str) or data['country'] not in COUNTRIES or not isinstance(data['city'],str) or not 1<=len(data['city'].strip())<=100:
        bad('Elegí ubicación, ámbitos y categorías disponibles.')
    if not positive_ids(data['scopes']) or not positive_ids(data['categories']):
        bad('Elegí ubicación, ámbitos y categorías disponibles.')
    frequency=data['frequency'];days=data['days']
    if not isinstance(frequency,str) or frequency not in FREQUENCIES or not isinstance(days,list) or len(days)>7 or any(type(d) is not int or not 0<=d<=6 for d in days) or len(set(days))!=len(days):
        bad('Revisá el horario y los días seleccionados.')
    if frequency!='daily' and len(days)!=(2 if frequency=='twice' else 1):
        bad('Revisá el horario y los días seleccionados.')
    if not isinstance(data['time'],str) or len(data['time'])!=5 or data['time'][2]!=':':
        bad('Revisá el horario y los días seleccionados.')
    try:
        hour,minute=data['time'].split(':')
        if not hour.isdecimal() or not minute.isdecimal():bad()
        time(int(hour),int(minute))
        if not isinstance(data['timezone'],str) or not 1<=len(data['timezone'])<=64:bad()
        ZoneInfo(data['timezone'])
    except (ValueError,ZoneInfoNotFoundError):
        bad('Revisá el horario y los días seleccionados.')
    if type(data['points']) is not int or not 0<=data['points']<=1000000 or not isinstance(data['period'],str) or data['period'] not in PERIODS:
        bad('Ingresá un límite de puntos entero y no negativo.')
    if type(data['notifications']) is not bool or not isinstance(data['language'],str) or data['language'] not in ('es','en','pl','it'):
        bad()
    if 'query_context' in data:
        context = data['query_context']
        if (not isinstance(context, dict) or set(context) != {'prompt', 'summary', 'mode', 'postal_id', 'currency'}
                or any(not isinstance(context[k], str) or not context[k].strip() or len(context[k]) > 3500 for k in ('prompt', 'summary'))
                or context['mode'] not in ('buscar', 'novedades', 'explorar')
                or type(context['postal_id']) is not int or not 0 <= context['postal_id'] <= 2147483647
                or not isinstance(context['currency'], str) or len(context['currency']) > 10):
            bad('La consulta del agente no es válida.', 422)
    return {**data,'city':data['city'].strip(),'tasks':sorted(data['tasks']),
            'scopes':sorted(data['scopes']),'categories':sorted(data['categories']),
            'days':[] if frequency=='daily' else sorted(days)}


def verify_catalog(config):
    """Use the existing read-only catalog contract and postal associations, never paid providers."""
    ids=postal_ids_for_city(config['country'],config['city'])
    if not ids:bad('Elegí ubicación, ámbitos y categorías disponibles.')
    if config.get('query_context', {}).get('postal_id', 0) not in (0, *ids):
        bad('El código postal de la consulta no corresponde a la ubicación.', 422)
    postal=db.session.get(CodigoPostal,ids[0])
    params=catalog_filters(MultiDict({'idioma':config['language']}),'ambitos')
    client=DPIAClient(current_app.config.get('SCRAPEADOR_SERVICE_KEY',''),timeout=(3.05,10))
    def fetch(task):
        name,postal_id=task
        return name,client.catalog(name,{**params,'codigo_postal_id':postal_id})[name]
    available_scopes={};available_categories={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name,rows in pool.map(fetch,[(name,postal_id) for postal_id in ids for name in ('ambitos','categorias')]):
            for row in rows:
                if name=='ambitos':available_scopes[row['ambito_id']]=row
                elif row['categoria_id'] in available_categories:
                    old=available_categories[row['categoria_id']]
                    old['ambito_ids']=sorted(set(old['ambito_ids']+row['ambito_ids']))
                else:available_categories[row['categoria_id']]=dict(row)
    if any(v not in available_scopes for v in config['scopes']) or any(v not in available_categories or not set(available_categories[v]['ambito_ids']).intersection(config['scopes']) for v in config['categories']):
        bad('Elegí ubicación, ámbitos y categorías disponibles.')
    if postal is None:bad('Elegí ubicación, ámbitos y categorías disponibles.')
    return {**config,'city':postal.ciudad.strip(),'scopeLabels':[{'id':i,'name':available_scopes[i]['nombre']} for i in config['scopes']],
            'categoryLabels':[{'id':i,'name':available_categories[i]['nombre']} for i in config['categories']]}


class AgentConfigurationStore:
    def _engine(self):
        if db.engine.dialect.name!='mysql':
            bad('El guardado del agente requiere MySQL.',503)
        return db.engine

    @staticmethod
    def _user(conn,user_id,lock=False):
        stmt=select(Usuario.id).where(Usuario.id==user_id,Usuario.activo.is_(True))
        if lock:stmt=stmt.with_for_update()
        if conn.execute(stmt).first() is None:bad('Iniciá sesión para guardar tu agente.',401)

    @staticmethod
    def _existing(conn,user_id):
        rows=conn.execute(select(agentes).where(agentes.c.usuario_id==user_id).limit(2)).mappings().all()
        if len(rows)>1:bad('Hay varias configuraciones para esta cuenta. Revisá los datos antes de guardar.',409)
        return rows[0] if rows else None

    @staticmethod
    def _serialize(conn,row,allow_active=False):
        config=row['configuracion']
        if not isinstance(config,dict) or config.get('version')!=1:
            bad('La configuración guardada no es compatible. Revisala antes de guardar.',409)
        try:
            validate_config({key:config[key] for key in FIELDS | ({'query_context'} if 'query_context' in config else set())})
        except (KeyError,PreparationError):
            bad('La configuración guardada no es compatible. Revisala antes de guardar.',409)
        task_rows=conn.execute(select(tareas).where(tareas.c.agente_id==row['id'])).mappings().all()
        enabled=[task['tipo'] for task in task_rows if task['tipo'] in {TASKS[t] for t in config.get('tasks',[]) if t in TASKS}]
        if any({k:v for k,v in (task['parametros'] or {}).items() if k not in ('_deleted_at','_agent_configuration','_configuration_revision')}!={'schema_version':1,'scope_ids':config['scopes'],'category_ids':config['categories']} for task in task_rows if task['tipo'] in enabled):
            bad('Los parámetros de las tareas no coinciden con la configuración guardada.',409)
        schedules=conn.execute(select(programaciones).where(programaciones.c.agente_id==row['id'])).mappings().all()
        if len(schedules)!=1 or len(enabled)!=len(set(enabled)) or set(enabled)!={TASKS[t] for t in config.get('tasks',[]) if t in TASKS}:
            bad('La configuración guardada no es compatible. Revisala antes de guardar.',409)
        # Refuse inconsistent/live configurations instead of presenting them as inactive.
        if (row['estado'] not in (('BORRADOR','INACTIVO','ACTIVO') if allow_active else ('BORRADOR','INACTIVO')) or schedules[0]['activa']):
            bad('Este agente tiene actividad habilitada. No se modificó su configuración.',409)
        schedule=schedules[0]
        iso_days=list(range(1,8)) if config['frequency']=='daily' else sorted(day or 7 for day in config['days'])
        if (row['idioma']!=config['language'] or row['pais_codigo']!=COUNTRIES[config['country']][0]
                or row['ciudad']!=config['city'] or row['zona_horaria']!=config['timezone']
                or row['presupuesto_puntos_periodo']!=config['points'] or row['periodo_presupuesto']!=PERIODS[config['period']]
                or row['notificaciones_activas']!=config['notifications']
                or schedule['frecuencia']!=FREQUENCIES[config['frequency']] or schedule['dias_semana']!=iso_days
                or schedule['hora_local']!=time.fromisoformat(config['time']) or schedule['zona_horaria']!=config['timezone']
                or schedule['proxima_ejecucion_en'] is not None or type(row['version_config']) is not int or row['version_config']<1):
            bad('La configuración guardada no es compatible. Revisala antes de guardar.',409)
        binding=config.get('engine_binding')
        if row['estado']=='ACTIVO' and (not isinstance(binding,dict) or not binding.get('id')):
            bad('El vínculo del agente no es válido.',409)
        return {'id':row['id'],'revision':row['version_config'],'state':'active' if row['estado']=='ACTIVO' else 'inactive','configuration':config}

    def get(self,user_id):
        with self._engine().begin() as conn:
            # A common user lock serializes reads and writes, including first creation.
            self._user(conn,user_id,lock=True)
            row=self._existing(conn,user_id)
            return self._serialize(conn,row,allow_active=True) if row and not (row['configuracion'] or {}).get('_deleted_at') else None

    def save(self,user_id,config,expected_revision):
        now=datetime.now(timezone.utc).replace(tzinfo=None)
        with self._engine().begin() as conn:
            self._user(conn,user_id,lock=True)
            previous=self._existing(conn,user_id)
            if previous and (previous['configuracion'] or {}).get('_deleted_at'):
                if expected_revision!=0:bad('La configuración cambió. Volvé a cargarla.',409)
            elif previous:
                stored=self._serialize(conn,previous)
                # A retry after an uncertain response returns the confirmed same configuration.
                if previous['configuracion']==config:return stored
                if previous['version_config']!=expected_revision:
                    bad('La configuración cambió en otra pestaña. Volvé a cargarla antes de editar.',409)
            elif expected_revision!=0:
                bad('La configuración cambió en otra pestaña. Volvé a cargarla antes de editar.',409)
            from services.scraping_quota import MySQLScrapingQuota
            quota=current_app.extensions.get('scraping_quota') or MySQLScrapingQuota()
            available=quota.credits(user_id)['available']
            if config['points']>available:
                bad(f'El presupuesto no puede superar tus {available} puntos disponibles.',402)
            owner_email=conn.execute(select(Usuario.correo_electronico).where(Usuario.id==user_id)).scalar_one()
            values=dict(nombre=owner_email,estado='INACTIVO',idioma=config['language'],pais_codigo=COUNTRIES[config['country']][0],
                        ciudad=config['city'],zona_horaria=config['timezone'],
                        presupuesto_puntos_periodo=config['points'],periodo_presupuesto=PERIODS[config['period']],
                        notificaciones_activas=config['notifications'],configuracion=config,
                        actualizado_en=now,activado_en=None)
            revision=previous['version_config']+1 if previous else 1
            values['version_config']=revision
            if previous:
                agent_id=previous['id'];conn.execute(update(agentes).where(agentes.c.id==agent_id,agentes.c.usuario_id==user_id).values(**values))
            else:
                agent_id=conn.execute(insert(agentes).values(usuario_id=user_id,creado_en=now,**values)).inserted_primary_key[0]
            task_rows=conn.execute(select(tareas).where(tareas.c.agente_id==agent_id)).mappings().all()
            current={row['tipo']:row for row in task_rows}
            if len(current)!=len(task_rows):bad('La configuración guardada no es compatible. Revisala antes de guardar.',409)
            desired={TASKS[t] for t in config['tasks']}
            for kind,row in current.items():
                if kind not in desired:conn.execute(update(tareas).where(tareas.c.id==row['id']).values(habilitada=False,actualizado_en=now))
            for kind in sorted(desired):
                fields=dict(habilitada=True,parametros={'schema_version':1,'scope_ids':config['scopes'],'category_ids':config['categories']},actualizado_en=now)
                if kind in current:
                    # Keep independent task editor settings when saving agent defaults.
                    previous_params=current[kind]['parametros'] or {}
                    fields['parametros'].update({key:previous_params[key] for key in
                        ('_agent_configuration','_configuration_revision') if key in previous_params})
                    conn.execute(update(tareas).where(tareas.c.id==current[kind]['id']).values(**fields))
                else:conn.execute(insert(tareas).values(agente_id=agent_id,tipo=kind,creado_en=now,**fields))
            schedule=conn.execute(select(programaciones.c.id).where(programaciones.c.agente_id==agent_id)).first()
            fields=dict(activa=False,frecuencia=FREQUENCIES[config['frequency']],
                        dias_semana=list(range(1,8)) if config['frequency']=='daily' else sorted(day or 7 for day in config['days']),
                        hora_local=time.fromisoformat(config['time']),zona_horaria=config['timezone'],
                        proxima_ejecucion_en=None,actualizado_en=now)
            if schedule:conn.execute(update(programaciones).where(programaciones.c.id==schedule.id).values(**fields))
            else:conn.execute(insert(programaciones).values(agente_id=agent_id,creado_en=now,**fields))
            return {'id':agent_id,'revision':revision,'state':'inactive','configuration':config}

    def add_task_to_existing_agent(self, user_id, config):
        """Append one task without changing the existing agent, its budget or other tasks."""
        import hashlib
        import json
        from sqlalchemy import MetaData as SA_MetaData, Table as SA_Table
        from uuid import uuid4
        if len(config['tasks']) != 1:
            bad('Una consulta debe crear una sola tarea.', 422)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        kind = TASKS[config['tasks'][0]]
        context = config.get('query_context')
        if not context:
            bad('La tarea necesita una consulta preparada.', 422)
        identity = {'type': kind, 'prompt': ' '.join(context['prompt'].casefold().split()),
                    'country': config['country'], 'city': config['city'].casefold(),
                    'scopes': config['scopes'], 'categories': config['categories'],
                    'mode': context['mode']}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        from model.agent_tasks import AgentTaskRepository
        repo = AgentTaskRepository()
        with self._engine().begin() as conn:
            self._user(conn, user_id, lock=True)
            agent = self._existing(conn, user_id)
            if not agent or (agent['configuracion'] or {}).get('_deleted_at'):
                bad('Primero creá el agente.', 409)
            task_table = SA_Table('agente_tareas', SA_MetaData(), autoload_with=conn, resolve_fks=False)
            existing = conn.execute(select(task_table).where(task_table.c.agente_id == agent['id']).with_for_update()).mappings().all()
            for task in existing:
                params = task['parametros'] or {}
                if not params.get('_deleted_at') and params.get('identity_hash') == digest:
                    return {'id': task['id'], 'agent_id': agent['id'], 'duplicate': True}
            engine_table = SA_Table('ae_agents', SA_MetaData(), autoload_with=conn, resolve_fks=False)
            engines = conn.execute(select(engine_table).where(engine_table.c.legacy_agent_id == agent['id'],
                                      engine_table.c.owner_id == user_id).with_for_update()).mappings().all()
            if len(engines) > 1:
                bad('Hay más de un vínculo con Agent Engine.', 409)
            engine_id = engines[0]['id'] if engines else None
            params = {'schema_version': 2, 'scope_ids': config['scopes'],
                      'category_ids': config['categories'], 'identity_hash': digest,
                      'query_context': context, 'country': config['country'],
                      'city': config['city'], 'language': config['language'],
                      'schedule': {'frequency': config['frequency'], 'days': config['days'],
                                   'time': config['time'], 'timezone': config['timezone']}}
            values = {'agente_id': agent['id'], 'tipo': kind,
                      'nombre': context['prompt'][:150], 'habilitada': False,
                      'parametros': params, 'creado_en': now, 'actualizado_en': now}
            if 'ae_agent_id' in task_table.c:
                values['ae_agent_id'] = engine_id
            task_id = conn.execute(insert(task_table).values(**values)).inserted_primary_key[0]
            # Never fabricate a remote executable schedule. It needs a verified request
            # snapshot and tool grants; keep this task paused until provisioned explicitly.
            return {'id': task_id, 'agent_id': agent['id'], 'duplicate': False,
                    'schedule_pending': True}

    def activate(self,user_id,expected_revision):
        from services.agent_activation import translate, provision
        with self._engine().begin() as conn:
            self._user(conn,user_id,lock=True)
            row=self._existing(conn,user_id)
            if row is None or (row['configuracion'] or {}).get('_deleted_at'):bad('Guardá la configuración antes de activar el agente.',409)
            agent=self._serialize(conn,row,allow_active=True)
            if agent['revision']!=expected_revision:
                bad('La configuración cambió en otra pestaña. Volvé a cargarla antes de activar.',409)
            if agent['state']=='active':return agent
            from services.scraping_quota import MySQLScrapingQuota
            quota=current_app.extensions.get('scraping_quota') or MySQLScrapingQuota()
            available=quota.credits(user_id)['available']
            if available<1:
                bad('Puntos insuficientes: necesitás al menos 1 punto disponible para activar el agente.',402)
            if agent['configuration']['points']<1:
                bad('El presupuesto del agente es 0. Editá la configuración y asigná al menos 1 punto por período para activarlo.',402)
            if agent['configuration']['points']>available:
                bad(f'El presupuesto no puede superar tus {available} puntos disponibles.',402)
            # Hold the owner lock through confirmation: edits and concurrent clicks cannot race.
            binding=provision(translate(agent,user_id))
            now=datetime.now(timezone.utc).replace(tzinfo=None)
            config={**row['configuracion'],'engine_binding':binding}
            conn.execute(update(agentes).where(agentes.c.id==row['id'],agentes.c.usuario_id==user_id).values(
                estado='ACTIVO',configuracion=config,activado_en=now,actualizado_en=now))
            return {**agent,'state':'active','configuration':config}
