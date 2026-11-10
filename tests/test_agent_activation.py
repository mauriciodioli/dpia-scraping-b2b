"""Activation boundary tests: isolated database, no live providers."""
import copy
from unittest.mock import patch, Mock
from sqlalchemy import select, update, event
from sqlalchemy.exc import SQLAlchemyError
import unittest
from flask import Flask
from sqlalchemy import text
from model.usuario import Usuario
from model.codigoPostal import CodigoPostal
from routes.agent_routes import agent_bp
from services.agent_configuration import AgentConfigurationStore, metadata
class TestStore(AgentConfigurationStore):
 def _engine(self):return db.engine
from services.agent_configuration import agentes, tareas, programaciones
from services.agent_activation import translate, provision
from utils.db import db


class AgentActivationTests(unittest.TestCase):
 def setUp(self):
  self.app=Flask(__name__);self.app.config.update(TESTING=True,SECRET_KEY='test',SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
  db.init_app(self.app);self.app.register_blueprint(agent_bp);self.app.extensions['agent_configuration_store']=TestStore()
  self.ctx=self.app.app_context();self.ctx.push();db.create_all();metadata.create_all(db.engine)
  a=Usuario('a@example.test');b=Usuario('b@example.test');db.session.add_all([a,b]);db.session.commit();self.a=a.id;self.b=b.id
  self.client=self.app.test_client();self.login(self.a)
  self.config={'version':1,'tasks':['products'],'country':'Argentina','city':'Córdoba','scopes':[108],'categories':[975],'frequency':'twice','days':[0,1],'time':'09:30','timezone':'Europe/Rome','points':10,'period':'month','notifications':False,'language':'es'}
  self.verify=patch('routes.agent_routes.verify_catalog',side_effect=lambda config:{**config,'categoryLabels':[{'id':975,'name':'Ropa'}]});self.verify.start()
  self.binding={'id':'00000000-0000-0000-0000-000000000123','revision':2}
 def tearDown(self):
  self.verify.stop();db.session.remove();metadata.drop_all(db.engine);db.drop_all();self.ctx.pop()
 def login(self,user):
  with self.client.session_transaction() as session:session['user_id']=user
 def save(self,config=None,revision=0):
  return self.client.put('/api/agente/configuracion',json={'configuration':config or self.config,'expected_revision':revision},headers={'X-DPIA-Action':'configure-agent'})
 def activate(self,body=None,headers=None):
  return self.client.post('/api/agente/activar',json={'expected_revision':1} if body is None else body,
      headers={'X-DPIA-Action':'activate-agent',**(headers or {})})
 def test_activation_and_retry_preserve_owner_and_points(self):
  self.save()
  with patch('services.agent_activation.provision',return_value=self.binding) as remote:
   first=self.activate();self.assertEqual(first.status_code,200,first.json)
   self.assertEqual(first.json['agent']['state'],'active')
   self.assertEqual(self.activate().json,first.json)
   remote.assert_called_once();payload=remote.call_args.args[0]
   self.assertEqual(payload['owner_id'],self.a)
   self.assertEqual(payload['schedule']['weekdays'],[1,7])
   self.assertEqual(payload['schedule']['frequency'],'WEEKLY')
  self.assertEqual(self.client.get('/api/agente/configuracion').json['agent'],first.json['agent'])
  self.assertEqual(self.save(revision=1).status_code,409)
  with db.engine.connect() as conn:
   self.assertFalse(conn.execute(select(programaciones.c.activa)).scalar_one())
   self.assertEqual(conn.execute(select(agentes.c.configuracion)).scalar_one()['engine_binding'],self.binding)
 def test_authorization_and_contract_fail_without_remote_calls(self):
  self.save()
  with patch('services.agent_activation.provision') as remote:
   for headers in [{'Origin':'https://evil.test'},{'Sec-Fetch-Site':'cross-site'},{'X-DPIA-Action':'configure-agent'}]:
    self.assertEqual(self.activate(headers=headers).status_code,403)
   for body in [{'expected_revision':True},{'expected_revision':1,'owner_id':self.a},{}]:
    self.assertEqual(self.activate(body).status_code,400)
   self.assertEqual(self.activate({'expected_revision':2}).status_code,409)
   self.login(self.b);self.assertEqual(self.activate().status_code,409)
   with self.client.session_transaction() as session:session.clear()
   self.assertEqual(self.activate().status_code,401)
   self.login(self.a)
   db.session.execute(update(__import__('model.usuario',fromlist=['Usuario']).Usuario).values(activo=False));db.session.commit()
   self.assertEqual(self.activate().status_code,401)
   remote.assert_not_called()
 def test_unsupported_configuration_has_no_partial_activation(self):
  with patch('services.agent_activation.provision') as remote:
   for changes in [{'tasks':['products','prices']},{'notifications':True},{'scopes':[108,109]}]:
    self.save({**self.config,**changes},revision=0 if changes=={'tasks':['products','prices']} else self.client.get('/api/agente/configuracion').json['agent']['revision'])
    revision=self.client.get('/api/agente/configuracion').json['agent']['revision']
    self.assertEqual(self.activate({'expected_revision':revision}).status_code,422)
   remote.assert_not_called()
 def test_uncertain_response_and_local_commit_failure_can_retry(self):
  self.save()
  from services.query_preparation import PreparationError
  with patch('services.agent_activation.provision',side_effect=PreparationError('Sin confirmación',502)):
   self.assertEqual(self.activate().status_code,502)
  self.assertEqual(self.client.get('/api/agente/configuracion').json['agent']['state'],'inactive')
  def fail(conn,cursor,statement,parameters,context,executemany):
   if statement.startswith('UPDATE agentes'):raise SQLAlchemyError('fixture')
  with patch('services.agent_activation.provision',return_value=self.binding) as remote:
   event.listen(db.engine,'before_cursor_execute',fail)
   try:self.assertEqual(self.activate().status_code,503)
   finally:event.remove(db.engine,'before_cursor_execute',fail)
   self.assertEqual(self.activate().status_code,200)
   self.assertEqual(remote.call_args_list[0],remote.call_args_list[1])
 def test_inconsistent_task_parameters_rejected(self):
  self.save()
  with db.engine.begin() as conn:conn.execute(update(tareas).values(parametros={}))
  with patch('services.agent_activation.provision') as remote:
   self.assertEqual(self.activate().status_code,409);remote.assert_not_called()
 def test_transport_signed_bounded_no_redirects_and_untrusted_confirmation(self):
  self.save();agent=self.client.get('/api/agente/configuracion').json['agent'];payload=translate(agent,self.a)
  self.app.config.update(AGENTS_INTERNAL_URL='http://ms202612agents:8301',PWA_ACTIVATION_SECRET='test-secret')
  response=Mock(status_code=200)
  response.json.return_value={'api_version':'agents.v1','owner_id':self.b,'source_agent_id':agent['id'],'source_revision':1,
      'execution_enabled':False,'agent':{'id':self.binding['id'],'revision':2,'configuration_state':'ENABLED'}}
  from services.query_preparation import PreparationError
  with patch('services.agent_activation.requests.post',return_value=response) as post:
   with self.assertRaises(PreparationError):provision(payload)
   self.assertFalse(post.call_args.kwargs['allow_redirects'])
   self.assertIn('X-DPIA-Signature',post.call_args.kwargs['headers'])
   response.json.return_value['owner_id']=self.a
   self.assertEqual(provision(payload),self.binding)
