import tempfile
from pathlib import Path
import prestadores_ext as ext
import fluxo_os as fluxo
from test_portal_v4 import schema

def testar():
    with tempfile.TemporaryDirectory() as tmp:
        base=Path(tmp)
        ext.RELATORIOS=base/'relatorios_pdf';ext.RELATORIOS.mkdir()
        db=str(base/'dados.db');schema(db);ext.instalar(db);fluxo.instalar(db)
        with ext.db(db) as c:
            c.execute("UPDATE ordens_servico SET status='Cancelada' WHERE id=1")
        legado=ext.RELATORIOS/'OS_OS-001_1.pdf'
        legado.write_bytes(b'%PDF-1.4\n'+b'X'*150)
        # A second document with a mismatched id should not be imported.
        (ext.RELATORIOS/'OS_OS-0001_99.pdf').write_bytes(legado.read_bytes())
        achados=fluxo.recuperar_relatorios_antigos(db)
        assert len(achados)==1,achados
        doc=fluxo.ultimo_documento(db,1)
        assert doc and Path(fluxo.validar_pdf_publicado(doc)).exists()
        assert len(fluxo.recuperar_relatorios_antigos(db))==0
        assert legado.read_bytes()==b'%PDF-1.4\n'+b'X'*150
        assert not fluxo.ultimo_documento(db,99)
        print('PASSOU: recuperação de PDF antigo, correspondência de OS, integridade e não duplicação.')
if __name__=='__main__':testar()
