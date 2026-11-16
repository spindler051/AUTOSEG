"""Immutable descriptors for a transport-neutral action menu."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    id: str
    section: str
    label: str
    permission: str
    service: str
    object_action: str
    destructive: bool
    confirm: str
    priority: str
    surfaces: tuple[str, ...]
    surface_reason: str
    gtk_handler: str
    web_href: str
    negative_test: str


def a(id, section, label, permission, service, object_action, gtk_handler,
      web_href, *, priority='secondary', destructive=False, confirm='',
      surfaces=('web', 'gtk'), reason='', negative_test='test_all_denied_actions'):
    return Action(id, section, label, permission, service, object_action,
                  destructive, confirm, priority, tuple(surfaces), reason,
                  gtk_handler, web_href, negative_test)
