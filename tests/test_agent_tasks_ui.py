"""Configured task cards in real Chromium with isolated HTTP responses."""
import unittest
import test_agent_activation_ui as fixture


class TaskUITests(unittest.TestCase):
    setUpClass = classmethod(fixture.ActivationUITests.setUpClass.__func__)
    tearDownClass = classmethod(fixture.ActivationUITests.tearDownClass.__func__)
    tearDown = fixture.ActivationUITests.tearDown

    def setUp(self):
        fixture.ActivationUITests.setUp(self)
        self.items = [dict(id=7, name='<script>task</script>', type='PRECIOS', state='active',
                          schedules=[dict(frequency='DAILY', days=[1], time='09:30', timezone='Europe/Rome',next_run_at=None)],
                          last_run_at=None, points_consumed=2)]
        self.changes = []
        def tasks(route):
            if route.request.method != 'GET':
                self.changes.append(route.request.method)
                if route.request.method == 'DELETE':
                    self.items = []
                else:
                    self.items[0]['state'] = 'paused' if route.request.url.endswith('/pausar') else 'active'
            route.fulfill(json=dict(success=True,tasks=self.items,count=len(self.items),execution_available=False))
        self.page.route('**/api/agentes/1/tareas**', tasks)
        self.page.evaluate('DPIAAgent.open()')

    def test_expand_pause_activate_delete_and_counter(self):
        self.page.locator('.agent-task-list summary').get_by_text('(1)', exact=False).wait_for()
        self.page.locator('.agent-task-list summary').click()
        card = self.page.locator('.agent-task-card')
        self.assertEqual(card.locator('h4').inner_text(), '<script>task</script>')
        card.get_by_role('button', name='Pausar', exact=True).click()
        card.get_by_text('Pausado', exact=True).wait_for()
        card.get_by_role('button', name='Activar', exact=True).click()
        card.get_by_text('Activo', exact=True).wait_for()
        self.page.once('dialog', lambda dialog: dialog.dismiss())
        card.get_by_role('button', name='Eliminar', exact=True).click()
        self.assertEqual(len(self.changes), 2)
        self.page.once('dialog', lambda dialog: dialog.accept())
        card.get_by_role('button', name='Eliminar', exact=True).click()
        self.page.get_by_text('No hay tareas configuradas.', exact=True).wait_for()
        self.assertEqual(self.changes, ['PATCH','PATCH','DELETE'])
        self.assertTrue(self.page.get_by_role('button', name='Eliminar agente', exact=True).is_visible())
