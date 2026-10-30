import tempfile
import unittest
from pathlib import Path
from workaholic.domain.schema import AppSchema
from workaholic.domain.errors import ValidationError, ConflictError
from workaholic.application.service import RecordService
from workaholic.infrastructure.repositories import YamlRepository, SQLiteRepository

SCHEMA = AppSchema.from_dict({"name":"test", "entities": {
    "client": {"fields":{"name":{"type":"string","required":True}},"deletion":"archive"},
    "job": {"fields":{"title":{"type":"string","required":True},"client_id":"string","done":"boolean"},
            "workflow":{"states":["queued","doing","finished"],"transitions":{"queued":["doing"],"doing":["finished"]}},
            "deletion":"delete"}},
    "relations":{"job_client":{"from":"job","to":"client","field":"client_id"}}})

class RepositoryContractTest(unittest.TestCase):
    def run_backend(self, backend):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ("data.yaml" if backend is YamlRepository else "data.db")
            s = RecordService(SCHEMA, backend(path))
            with self.assertRaises(ValidationError):
                s.create("client", {})
            c = s.create("client", {"name":"A"})
            job = s.create("job", {"title":"Work","client_id":c["id"],"done":False})
            self.assertEqual(job["state"], "queued")
            self.assertEqual(len(s.list("job")), 1)
            with self.assertRaises(ValidationError):
                s.transition("job", job["id"], "finished", expected_version=1)
            with self.assertRaises(ValidationError):
                s.remove("client", c["id"], expected_version=1)
            job = s.transition("job", job["id"], "doing", expected_version=1)
            self.assertEqual(job["version"], 2)
            with self.assertRaises(ConflictError):
                s.update("job", job["id"], {"title":"Oops"}, expected_version=1)
            job = s.update("job", job["id"], {"title":"New"}, expected_version=2)
            self.assertEqual(job["fields"]["title"], "New")
            job = s.transition("job", job["id"], "finished", expected_version=3)
            self.assertIsNone(s.remove("job", job["id"], expected_version=4))
            self.assertEqual(s.list("job"), [])
            c = s.remove("client", c["id"], expected_version=1)
            self.assertTrue(c["archived"])
            self.assertEqual(s.list("client"), [])
            self.assertEqual(len(s.list("client", include_archived=True)), 1)

    def test_yaml(self): self.run_backend(YamlRepository)
    def test_sqlite(self): self.run_backend(SQLiteRepository)

if __name__ == "__main__": unittest.main()
