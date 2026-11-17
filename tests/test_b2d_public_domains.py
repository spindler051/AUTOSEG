"""B2d regression assertions; review only, not executed by the author."""
import unittest
from flavors.autoseg.modules.action_sections.public import ACTIONS as PJ
from flavors.autoseg.modules.action_sections.desktop_web import ACTIONS as DEVICE_WEB
from flavors.autoseg.modules.action_sections.desktop_connect import ACTIONS as DEVICE_CONNECT


class B2dSplitTests(unittest.TestCase):
    def test_pj_public_and_v9_are_separate_domains(self):
        web = {a.id: a for a in PJ if 'web' in a.surfaces}
        gtk = {a.id: a for a in PJ if 'gtk' in a.surfaces}
        self.assertEqual(set(web), {'public.request.list',
                                    'public.request.accept',
                                    'public.request.reject'})
        self.assertEqual(set(gtk), {'pj.chamado.list', 'pj.chamado.analyze',
                                    'pj.chamado.confirm', 'pj.chamado.create_work',
                                    'pj.chamado.reject', 'pj.organization.verify',
                                    'pj.organization.merge'})
        self.assertTrue(all(a.permission == '*' for a in PJ))
        self.assertTrue(all(a.web_href == '/pj-publicas' for a in web.values()))
        self.assertTrue(all(a.gtk_handler for a in gtk.values()))
        self.assertTrue(all(a.gtk_handler == '' for a in web.values()))

    def test_device_controls_remain_gtk_only(self):
        self.assertTrue(all(a.surfaces == ('gtk',) for a in
                            (*DEVICE_WEB, *DEVICE_CONNECT)))
        self.assertTrue(all(a.surface_reason for a in
                            (*DEVICE_WEB, *DEVICE_CONNECT)))
