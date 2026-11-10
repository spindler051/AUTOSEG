"""Unit tests for the object-level permission skeleton."""
import unittest

from officina.application.object_policy import (
    ObjectPolicy,
    PermissionDenied,
    Principal,
    Resource,
)
from officina.application.policy import load_policy


class ObjectPolicyTest(unittest.TestCase):
    def setUp(self):
        self.policy = ObjectPolicy(load_policy())

    def _os(self, owner=11, client=500, participants=(), org="org-a"):
        return Resource(
            "work_item", id=10, organization_id=org, owner_id=owner,
            client_id=client, participant_ids=frozenset(participants))

    def test_admin_has_full_permission_inside_tenant(self):
        admin = Principal(1, "admin", organization_id="org-a")
        self.assertTrue(self.policy.can(admin, "edit", self._os()).allowed)
        other = Principal(2, "admin", organization_id="org-b")
        decision = self.policy.can(other, "edit", self._os())
        self.assertFalse(decision.allowed)
        self.assertIn("outra organização", decision.reason)

    def test_provider_only_edits_own_or_involved(self):
        provider = Principal(10, "employee", organization_id="org-a",
                             provider_id=10)
        own = self._os(owner=10, participants=(10,))
        self.assertTrue(self.policy.can(provider, "edit", own).allowed)
        involved = self._os(owner=11, participants=(10,))
        self.assertTrue(self.policy.can(provider, "edit", involved).allowed)
        other = self._os(owner=11, participants=(12,))
        self.assertFalse(self.policy.can(provider, "edit", other).allowed)
        self.assertFalse(self.policy.can(provider, "view", other).allowed)

    def test_provider_finance_scope_and_explicit_grant(self):
        provider = Principal(10, "employee", organization_id="org-a",
                             provider_id=10)
        own_finance = Resource("finance", organization_id="org-a", owner_id=10)
        company = Resource("finance", organization_id="org-a")
        self.assertTrue(self.policy.can(provider, "view", own_finance).allowed)
        self.assertFalse(self.policy.can(provider, "view", company).allowed)
        granted = Principal(10, "employee", organization_id="org-a",
                            provider_id=10,
                            grants=frozenset({"finance.view.all"}))
        self.assertTrue(self.policy.can(granted, "view", company).allowed)

    def test_deny_overrides_grant(self):
        provider = Principal(
            10, "employee", organization_id="org-a", provider_id=10,
            grants=frozenset({"work_item.edit.involved"}),
            denies=frozenset({"work_item.edit.involved"}))
        self.assertFalse(
            self.policy.can(provider, "edit", self._os(owner=11,
                                                       participants=(10,))).allowed)

    def test_client_only_sees_own_work(self):
        client = Principal(20, "customer", organization_id="org-a",
                           client_id=500)
        own = self._os(owner=11, client=500, participants=(11,))
        other = self._os(owner=11, client=501, participants=(11,))
        self.assertTrue(self.policy.can(client, "view", own).allowed)
        self.assertFalse(self.policy.can(client, "view", other).allowed)
        draft = Resource("work_item", organization_id="org-a", client_id=500)
        self.assertTrue(self.policy.can(client, "create", draft).allowed)

    def test_customer_field_scope(self):
        client = Principal(20, "customer", organization_id="org-a",
                           client_id=500)
        own = Resource("customer", organization_id="org-a", client_id=500)
        other = Resource("customer", organization_id="org-a", client_id=501)
        self.assertTrue(self.policy.can_view_field(
            client, own, "customer.documento").allowed)
        self.assertFalse(self.policy.can_view_field(
            client, other, "customer.documento").allowed)
        provider = Principal(10, "employee", organization_id="org-a",
                             provider_id=10)
        involved = Resource("customer", organization_id="org-a",
                            client_id=500, participant_ids=frozenset({10}))
        self.assertTrue(self.policy.can_view_field(
            provider, involved, "customer.documento").allowed)

    def test_inactive_account_and_require(self):
        inactive = Principal(10, "employee", organization_id="org-a",
                             provider_id=10, active=False)
        self.assertFalse(self.policy.can(inactive, "view", self._os()).allowed)
        client = Principal(20, "customer", organization_id="org-a",
                           client_id=501)
        with self.assertRaises(PermissionDenied):
            self.policy.require(client, "edit", self._os())


if __name__ == "__main__":
    unittest.main()
