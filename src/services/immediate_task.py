"""Persist a user task before asking Agents to schedule one immediate run."""
from sqlalchemy import select, update, MetaData, Table
from services.agent_configuration import AgentConfigurationStore, bad, TASKS
from services.agent_activation import schedule_immediate_task
from services.query_preparation import PreparationError


class ImmediateTaskService:
    def __init__(self, store=None):
        self.store=store or AgentConfigurationStore()

    def submit(self, owner, config, request_id):
        agent=self.store.get(owner)
        if agent is None:
            from flask import current_app
            from services.scraping_quota import MySQLScrapingQuota
            quota=current_app.extensions.get('scraping_quota') or MySQLScrapingQuota()
            available=quota.credits(owner)['available']
            if available<1:bad('No tenés puntos disponibles para ejecutar la tarea.',402)
            config={**config,'points':min(3,available)}
            # The regular validated creation transaction also persists the first task.
            try:
                agent=self.store.save(owner,config,0,initial_request_id=request_id)
            except PreparationError as exc:
                if exc.status!=409:raise
                agent=self.store.get(owner)
                if agent is None:raise
        with self.store._engine().begin() as conn:
            self.store._user(conn,owner,lock=True)
            row=self.store._existing(conn,owner)
            table=Table('agente_tareas',MetaData(),autoload_with=conn,resolve_fks=False)
            previous=conn.execute(select(table).where(table.c.agente_id==row['id'])).mappings().all()
            matches=[task for task in previous if (task['parametros'] or {}).get('immediate_request_id')==request_id]
            if matches:
                params=matches[0]['parametros'] or {}
                if params.get('_deleted_at'):bad('Este envío pertenece a una tarea eliminada. Prepará un pedido nuevo.',409)
                # An idempotency key can never be reused for another request.
                if (params.get('query_context')!=config['query_context'] or params.get('country')!=config['country']
                        or params.get('city')!=config['city'] or params.get('language')!=config['language']
                        or params.get('execution_sources')!=config.get('execution_sources')
                        or params.get('scope_ids')!=config['scopes'] or params.get('category_ids')!=config['categories']
                        or matches[0]['tipo']!=TASKS[config['tasks'][0]]):
                    bad('El identificador del envío ya pertenece a otro pedido.',409)
                task={'id':matches[0]['id'],'agent_id':row['id'],'duplicate':True}
            else:task=None
        if task is None:
            task=self.store.add_task_to_existing_agent(owner,config,immediate_request_id=request_id)
        # The local agent and task have committed before this authenticated HTTP call.
        remote=schedule_immediate_task(owner,task['agent_id'],task['id'],request_id)
        with self.store._engine().begin() as conn:
            self.store._user(conn,owner,lock=True)
            row=self.store._existing(conn,owner)
            configuration=dict(row['configuracion'])
            binding=configuration.get('engine_binding')
            if binding and binding['id']!=remote['agent']['id']:
                bad('El vínculo del agente requiere revisión.',409)
            expected_binding={'id':remote['agent']['id'],'revision':remote['agent']['revision']}
            if binding!=expected_binding or row['estado']!='ACTIVO':
                configuration['engine_binding']=expected_binding
                from services.agent_configuration import agentes
                conn.execute(update(agentes).where(agentes.c.id==task['agent_id'],agentes.c.usuario_id==owner)
                             .values(configuracion=configuration,estado='ACTIVO',version_config=row['version_config']+1))
        return {'task_id':task['id'],'agent_id':task['agent_id'],'schedule':remote['schedule'],
                'request_id':request_id,'state':'SCHEDULED','replayed':remote['replayed']}
