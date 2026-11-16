"""Narrow HMAC operation adopting an Agents reservation; no new credentials/DDL.

Public B2B generation remains session-only. This adapter cannot create a wallet
or reserve a second point: an owner/job/task-bound reservation must already exist.
"""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from uuid import UUID, uuid5, NAMESPACE_URL
from flask import current_app, request, jsonify
from sqlalchemy import select, update
from services.query_preparation import PreparationError, prepare_context
from services.scraping_quota import MySQLScrapingQuota, operaciones, decode, fingerprint
from services.novel_query import run_novelties
from services.result_generation import generate
from services.query_sources import require_enabled_marketplaces

PATH = '/api/consultas/internal/agents-commercial'


class AdoptedQuota(MySQLScrapingQuota):
    def __init__(self, original, binding, request_hash):
        self.original, self.binding, self.request_hash = original, binding, request_hash

    def _engine(self): return self.original._engine()
    def _lock(self, conn, user_id): return self.original._lock(conn,user_id)

    def reserve_direct(self, operation_id, user_id, prepared):
        # The existing Agents reserve() enforces wallet and agent-period limits.
        # Never call the public reserve_direct(), which could create a new hold.
        with self._engine().begin() as conn:
            row=conn.execute(select(operaciones).where(operaciones.c.operacion_id==operation_id,
                operaciones.c.usuario_id==user_id).with_for_update()).mappings().first()
            metadata=decode(row['contexto_json']) if row else {}
            if (not row or row['origen']!='amazon' or
                any(metadata.get(k)!=v for k,v in self.binding.items()) or
                metadata.get('billing_schema')!='agents.points.v1'):
                raise PreparationError('Reserva de Agents no autorizada.',403)
            previous=metadata.get('commercial_request_hash')
            if previous and previous!=self.request_hash:
                raise PreparationError('La operación pertenece a otra solicitud.',409)
            if not previous:
                if row['estado']!='reserved':
                    raise PreparationError('La reserva no está disponible.',409)
                metadata={**metadata,'commercial_request_hash':self.request_hash,
                    'commercial_prepared':prepared,'commercial_fingerprint':fingerprint(prepared)}
                conn.execute(update(operaciones).where(operaciones.c.operacion_id==operation_id,
                    operaciones.c.usuario_id==user_id).values(contexto_json=json.dumps(metadata,ensure_ascii=False)))

    def operation(self, operation_id, user_id):
        result=super().operation(operation_id,user_id)
        if result:
            metadata=result['prepared']
            if (metadata.get('commercial_request_hash')!=self.request_hash or
                any(metadata.get(k)!=v for k,v in self.binding.items())):
                raise PreparationError('La operación pertenece a otra solicitud.',409)
            result['prepared']=metadata['commercial_prepared']
        return result


def execute():
    if not request.content_length or request.content_length>65536:
        return jsonify(error='invalid_internal_request'),413
    raw=request.get_data(cache=True)
    key=current_app.config.get('PWA_ACTIVATION_SECRET','')
    stamp=request.headers.get('X-DPIA-Timestamp','')
    try: fresh=abs(time.time()-int(stamp))<=60
    except ValueError: fresh=False
    signature=hmac.new(key.encode(),stamp.encode()+b'\n'+PATH.encode()+b'\n'+raw,hashlib.sha256).hexdigest()
    if (not key or not fresh or len(raw)>65536 or request.args or
        not hmac.compare_digest(signature,request.headers.get('X-DPIA-Signature',''))):
        return jsonify(error='invalid_service_credentials'),401
    try:
        body=request.get_json(silent=True)
        required={'owner_id','agent_id','job_id','task_id','operation_id','request','max_output_tokens','model','generation_timeout_seconds','scraping_timeout_seconds'}
        if not isinstance(body,dict) or set(body)-{'research_evidence'}!=required or type(body['owner_id']) is not int or body['owner_id']<1:
            raise PreparationError('Solicitud interna inválida.')
        for k in ('agent_id','job_id','task_id','operation_id'):
            if str(UUID(body[k]))!=body[k]: raise ValueError
        expected=str(uuid5(NAMESPACE_URL,'dpia-agent-scraping:'+body['task_id']))
        if body['operation_id']!=expected: raise PreparationError('Reserva inválida.',403)
        if type(body['max_output_tokens']) is not int or not 16<=body['max_output_tokens']<=12000:
            raise PreparationError('Presupuesto de generación inválido.')
        if (type(body['generation_timeout_seconds']) is not int or not 5<=body['generation_timeout_seconds']<=90
                or type(body['scraping_timeout_seconds']) is not int or not 90<=body['scraping_timeout_seconds']<=180):
            raise PreparationError('Tiempo de proveedor inválido.')
        if body['model']!=current_app.config.get('OPENAI_MODEL','gpt-4o-mini'):
            raise PreparationError('El modelo autorizado no coincide con B2B.',409)
        payload=body['request']
        allowed={'pais','ciudad','codigo_postal_id','ambito_id','categoria_id','idioma','user_message','situation'}
        if not isinstance(payload,dict) or set(payload)!=allowed or payload['situation']=='jobs':
            raise PreparationError('Solicitud comercial inválida.')
        quota=current_app.extensions.get('scraping_quota')
        if quota is None: raise PreparationError('Persistencia no disponible.',503)
        require_enabled_marketplaces(['amazon'])
        prepared=prepare_context({**payload,'sources':['amazon'],'mode':'novedades'},body['owner_id'])
        prepared['image_pipeline']='base44'
        if 'research_evidence' in body:
            evidence=body['research_evidence']
            if not isinstance(evidence,dict) or len(json.dumps(evidence,ensure_ascii=False).encode())>24000:
                raise PreparationError('Evidencia interna inválida.')
            prepared['research_evidence']=evidence
        digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        adopted=AdoptedQuota(quota,{k:body[k] for k in ('agent_id','job_id','task_id')},digest)
        usage={}
        def generate_once(prepared,config):
            return generate(prepared,config,max_output_tokens=body['max_output_tokens'],
                timeout_seconds=body['generation_timeout_seconds'],on_usage=usage.update)
        internal_config={**current_app.config,'_INTERNAL_SCRAPER_TIMEOUT_SECONDS':body['scraping_timeout_seconds']}
        run_novelties(prepared,internal_config,adopted,body['operation_id'],generate_once,
            generation_usage=lambda:dict(usage))
        operation=adopted.operation(body['operation_id'],body['owner_id'])
        outcome=json.loads(operation['outcome']) if operation.get('outcome') else {}
        return jsonify(operation_id=body['operation_id'],generation_result=outcome.get('generation_result'),
            generation_usage=outcome.get('generation_usage'),
            outcome={k:v for k,v in outcome.items() if k not in ('generation_result','generation_usage','generation')},
            retrieved_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'))
    except (ValueError,TypeError,KeyError,AttributeError):
        return jsonify(error='invalid_internal_request'),400
    except PreparationError as error:
        # Provider/catalog free text is never reflected through this boundary.
        return jsonify(error='commercial_operation_rejected'),error.status
